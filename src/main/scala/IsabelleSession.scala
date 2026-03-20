package isa.repl

import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.logging.Logger
import scala.concurrent.{Await, Future}
import scala.concurrent.duration.Duration

import de.unruh.isabelle.control.{
  Isabelle,
  IsabelleControllerException,
  IsabelleMLException,
  OperationCollection
}
import de.unruh.isabelle.pure.{Theory, ToplevelState, Transition}
import de.unruh.isabelle.pure.ToplevelState.Modes
import de.unruh.isabelle.mlvalue.Implicits._
import de.unruh.isabelle.pure.Implicits._
import de.unruh.isabelle.mlvalue.MLValue.compileFunction
import de.unruh.isabelle.control.Isabelle.executionContext

import IsabelleSession.Ops
import isa.repl.{
  ExecStatus,
  InitStateError => ProtoInitStateError,
  InitStateResponse,
  StateMode,
  StateResult => ProtoStateResult
}

/** Server-side cache for a parsed theory file.
  *
  * Only stores the parsed transitions; execution state is managed separately
  * via [[IsabelleSession.initCache]].
  */
case class CachedTheory(
    transitions: List[(Transition, String)] // all non-ignored transitions
)

/** Wraps a single Isabelle process (one logic/heap image).
  *
  * @param sessionId
  *   UUID assigned at CreateSession
  * @param isaPath
  *   path to Isabelle installation
  * @param logic
  *   logic image name (e.g. "HOL", "HOL-Analysis")
  * @param workDir
  *   working directory (contains .thy files)
  * @param sessionRoots
  *   extra session root directories (e.g. AFP thys/)
  */
class IsabelleSession(
    val sessionId: String,
    val isaPath: os.Path,
    val logic: String,
    val workDir: os.Path,
    val sessionRoots: List[os.Path]
) {
  private val log = Logger.getLogger(classOf[IsabelleSession].getName)

  log.info(
    s"Session $sessionId: starting Isabelle (logic=$logic, workDir=$workDir)"
  )
  implicit val isabelle: Isabelle = new Isabelle(
    Isabelle.Setup(
      isabelleHome = isaPath.toNIO,
      logic = logic,
      workingDirectory = workDir.toNIO,
      sessionRoots = sessionRoots.map(_.toNIO),
      build = false
    )
  )
  log.info(s"Session $sessionId: Isabelle process ready")

  // ── Session directory registration ───────────────────────────────────────
  //
  // Two ROOT file layouts exist:
  //   (A) root/ROOT defines sessions with "in SubDir" — e.g. Isabelle src/HOL/ROOT
  //       where "session HOL-Library in Library = ..." means dir is root/Library/
  //   (B) root/subDir/ROOT defines a single session with no "in" clause — AFP style
  //       where each AFP entry lives in its own subdirectory
  //
  // We handle both by calling registerFromRootFile for every ROOT file found.

  /** Collect (sessionName → dir) pairs from a ROOT file without registering. */
  private def collectFromRootFile(
      baseDir: os.Path,
      content: String
  ): List[(String, java.nio.file.Path)] = {
    val cleaned = content.replaceAll("""\(\*[\s\S]*?\*\)""", "")
    val withDirPat =
      """(?m)session\s+"?([^"(\s]+)"?[^=\n]*\bin\s+"?([^"\s=\n]+)"?""".r
    val noDirPat = """(?m)^session\s+"?([^"(\s]+)"?""".r

    val buf = collection.mutable.ListBuffer[(String, java.nio.file.Path)]()
    val withDirNames = collection.mutable.Set[String]()
    for (m <- withDirPat.findAllMatchIn(cleaned)) {
      val name = m.group(1)
      val dirStr = m.group(2).stripPrefix("\"").stripSuffix("\"")
      val dir = baseDir / os.RelPath(dirStr)
      if (os.isDir(dir)) {
        buf += name -> dir.toNIO
        withDirNames += name
      }
    }
    for (m <- noDirPat.findAllMatchIn(cleaned)) {
      val name = m.group(1)
      if (!withDirNames.contains(name))
        buf += name -> baseDir.toNIO
    }
    buf.toList
  }

  /** Collect all (sessionName → dir) pairs under a session root directory. */
  private def collectSessionRoot(
      root: os.Path
  ): List[(String, java.nio.file.Path)] = {
    val buf = collection.mutable.ListBuffer[(String, java.nio.file.Path)]()
    // Layout (A): root itself has a ROOT file (e.g. src/HOL/ROOT)
    val topRootFile = root / "ROOT"
    if (os.exists(topRootFile))
      buf ++= collectFromRootFile(root, os.read(topRootFile))
    // Layout (B): each subdirectory has its own ROOT file (AFP style)
    if (os.isDir(root)) {
      os.list(root).filter(os.isDir).foreach { subDir =>
        val subRootFile = subDir / "ROOT"
        if (os.exists(subRootFile))
          buf ++= collectFromRootFile(subDir, os.read(subRootFile))
      }
    }
    buf.toList
  }

  // Collect all pairs first, then register in a single ML round-trip
  locally {
    val allPairs = sessionRoots.flatMap(collectSessionRoot)
    if (allPairs.nonEmpty)
      Theory.registerSessionDirectoriesNow(allPairs: _*)(isabelle)
  }

  // ── sessionFilesMap for import resolution (getTheorySource) ──────────────
  //
  // Maps session name → list of .thy files in that session's directories.
  // Built from the workDir's ROOT file when present (isa-eval approach),
  // otherwise falls back to a simple listing under the derived session name.

  private def parseWorkDirRootFile(
      rootFile: os.Path
  ): Map[String, List[os.Path]] = {
    val projectPath = rootFile / os.up
    val cleaned = os.read(rootFile).replaceAll("""\(\*[\s\S]*?\*\)""", "")

    // Collect (sessionName, mainDir) pairs and their character offsets
    val sessionPat =
      """session\s+([\w_"+-]+)\s*(?:\(.*?\)\s*)?(?:in\s*("?[^"=\n]+"?)\s*)?=.*?""".r
    case class SessionEntry(
        name: String,
        mainDir: os.Path,
        startIdx: Int
    )
    val entries = sessionPat
      .findAllMatchIn(cleaned)
      .map { m =>
        val name = m.group(1).stripPrefix("\"").stripSuffix("\"")
        val dirStr = Option(m.group(2))
          .map(_.trim.stripPrefix("\"").stripSuffix("\""))
          .getOrElse("")
        val mainDir = projectPath / os.RelPath(dirStr)
        SessionEntry(name, mainDir, m.start)
      }
      .toList

    // Build mainDir → sessionName map; also handle "directories" sub-blocks
    val dirToSession = collection.mutable.Map[os.Path, String]()
    val offsets = entries.map(_.startIdx) :+ cleaned.length
    entries.zip(offsets.tail).foreach { case (entry, nextOffset) =>
      dirToSession(entry.mainDir) = entry.name
      // "directories" block within this session range
      val block = cleaned.slice(entry.startIdx, nextOffset)
      val dirBlockPat = """directories\s*\n([\s\S]*?)(?:theories|options|$)""".r
      dirBlockPat.findFirstMatchIn(block).foreach { m =>
        m.group(1).trim.split("\\s+").foreach { rel =>
          val subDir = entry.mainDir.toNIO
            .resolve(rel.stripPrefix("\"").stripSuffix("\""))
            .normalize()
          dirToSession(os.Path(subDir)) = entry.name
        }
      }
    }

    // Recursively find all .thy files under projectPath and assign to sessions
    def collectThyFiles(dir: os.Path): List[os.Path] =
      if (!os.isDir(dir)) Nil
      else
        os.list(dir).toList.flatMap { p =>
          if (os.isFile(p) && p.ext == "thy") List(p)
          else if (os.isDir(p)) collectThyFiles(p)
          else Nil
        }

    val sessionFiles =
      entries.map(e => e.name -> collection.mutable.ListBuffer[os.Path]()).toMap
    collectThyFiles(projectPath).foreach { thyFile =>
      var dir = thyFile.toNIO.getParent
      var found = false
      while (dir != null && !found) {
        dirToSession.get(os.Path(dir)) match {
          case Some(sname) if sessionFiles.contains(sname) =>
            sessionFiles(sname) += thyFile
            found = true
          case _ => dir = dir.getParent
        }
      }
    }
    sessionFiles.transform((_, v) => v.toList)
  }

  // Derive the primary session name for the working directory.
  // If workDir has a ROOT file, take the first session name from it.
  // Otherwise, try to match workDir against a known AFP entry directory.
  // Fallback: use logic name.
  private val workDirSessionName: String = {
    val rootFile = workDir / "ROOT"
    if (os.exists(rootFile)) {
      val cleaned = os.read(rootFile).replaceAll("""\(\*[\s\S]*?\*\)""", "")
      val pat = """(?m)^session\s+"?([^"(\s]+)"?""".r
      pat.findFirstMatchIn(cleaned).map(_.group(1)).getOrElse(logic)
    } else {
      // Check whether workDir is a direct child of one of the session roots
      sessionRoots
        .flatMap(root => os.list(root).filter(os.isDir))
        .find(_ == workDir)
        .map(_.last)
        .getOrElse(logic)
    }
  }

  private val sessionFilesMap: Map[String, List[os.Path]] = {
    val rootFile = workDir / "ROOT"
    if (os.exists(rootFile)) parseWorkDirRootFile(rootFile)
    else
      Map(workDirSessionName -> os.list(workDir).filter(_.ext == "thy").toList)
  }

  private val theoryManager: TheoryManager = new TheoryManager(
    workDirSessionName
  )

  // Parsed theory cache: thyPath → CachedTheory
  val theoryCache = new ConcurrentHashMap[os.Path, CachedTheory]()

  // Proof state store: stateId → ToplevelState (immutable ML value)
  val stateMap = new ConcurrentHashMap[String, ToplevelState]()

  // init_state result cache: (thyPath, afterLine) → stateId
  // Populated on every successful initState call for fast replay.
  // Entries are invalidated when the corresponding state is dropped.
  private val initCache =
    new ConcurrentHashMap[(os.Path, Int), String]()
  private val initCacheKeys =
    new ConcurrentHashMap[String, (os.Path, Int)]()

  // ─── Private helpers ─────────────────────────────────────────────────────

  /** Execute a list of transitions against a state using ML-level timeout.
    * Reused from old IsabelleServer.scala:318–332.
    */
  private def asyncExecute(
      trs: List[Transition],
      state: ToplevelState,
      timeoutMs: Int
  ): ToplevelState =
    Ops
      .commandExceptionWithTimeout(
        timeoutMs.toLong * trs.length,
        true,
        trs,
        state
      )
      .retrieveNow
      .force

  private def proofStateText(
      state: ToplevelState,
      includeText: Boolean
  ): String =
    if (includeText) state.proofStateDescription else ""

  private def modeOf(state: ToplevelState): StateMode = state.mode match {
    case Modes.Toplevel     => StateMode.TOPLEVEL
    case Modes.Theory       => StateMode.THEORY
    case Modes.LocalTheory  => StateMode.LOCAL_THEORY
    case Modes.Proof        => StateMode.PROOF
    case Modes.SkippedProof => StateMode.SKIPPED_PROOF
  }

  private def buildResult(
      stateId: String,
      state: ToplevelState,
      status: ExecStatus,
      errorMsg: String = "",
      includeText: Boolean = false
  ): ProtoStateResult =
    ProtoStateResult(
      stateId = stateId,
      status = status,
      errorMsg = errorMsg,
      proofLevel = state.proofLevel,
      mode = modeOf(state),
      proofStateText = proofStateText(state, includeText)
    )

  /** Parse a theory file into transitions and cache the result.
    *
    * Only parses — does not execute anything. Execution is deferred to
    * [[initState]], which replays lazily and caches its results.
    */
  private def loadAndCacheImpl(thyPath: os.Path): CachedTheory = {
    val t0 = System.currentTimeMillis()
    log.info(s"Session $sessionId: parsing theory ${thyPath.last}")
    val thyText = os.read(thyPath)
    val thy = theoryManager.beginTheory(thyText, thyPath, sessionFilesMap)
    val allTrs: List[(Transition, String)] =
      theoryManager
        .getThyTransitions(thy, thyText, removeComments = false)
        .filterNot { case (tr, _) => tr.isIgnored }
    val elapsed = System.currentTimeMillis() - t0
    log.info(
      s"Session $sessionId: theory ${thyPath.last} parsed" +
        s" (${allTrs.length} transitions, ${elapsed}ms)"
    )
    CachedTheory(allTrs)
  }

  // ─── Public API ──────────────────────────────────────────────────────────

  /** Load (or retrieve cached) theory. Returns number of transitions. */
  def loadTheory(thyPath: os.Path): Int = {
    val cached = theoryCache.computeIfAbsent(thyPath, p => loadAndCacheImpl(p))
    cached.transitions.length
  }

  /** List commands from a theory file (loads/caches if needed). */
  def listTheoryCommands(
      thyPath: os.Path,
      onlyProofStmts: Boolean
  ): List[(String, String, Int)] = {
    val cached = theoryCache.computeIfAbsent(thyPath, p => loadAndCacheImpl(p))
    cached.transitions
      .filter { case (tr, _) =>
        if (onlyProofStmts) ProofCommands.list.contains(tr.name) else true
      }
      .map { case (tr, cmd) => (cmd, tr.name, tr.position.line.getOrElse(0)) }
  }

  /** Create a proof state by replaying transitions from TOPLEVEL up to the
    * requested position.
    *
    * Uses a transparent cache keyed by (thyPath, afterLine): repeated calls for
    * the same position are O(1); nearby positions reuse the closest cached
    * state below the target.
    *
    * @param position
    *   Left(afterLine) — execute all transitions with source line ≤ afterLine.
    *   Right(cmdText) — execute up to and including the first transition whose
    *   text contains cmdText.
    * @return
    *   [[InitStateResponse]] with either a [[ProtoStateResult]] on success, or
    *   an [[ProtoInitStateError]] containing the failing line, error message,
    *   and the last successfully reached state (absent if the first transition
    *   already failed).
    */
  def initState(
      thyPath: os.Path,
      position: Either[Int, String],
      timeoutMs: Int,
      includeText: Boolean = false
  ): InitStateResponse = {
    val cached = theoryCache.computeIfAbsent(thyPath, p => loadAndCacheImpl(p))

    // Resolve position to a target line number
    val targetLine: Int = position match {
      case Left(n)        => n
      case Right(cmdText) =>
        cached.transitions
          .find { case (_, cmd) => cmd.contains(cmdText) }
          .flatMap { case (tr, _) => tr.position.line }
          .getOrElse(Int.MaxValue)
    }

    // Find the best cached starting point: highest cached line ≤ targetLine
    // whose state is still alive in stateMap.
    import scala.jdk.CollectionConverters._
    val bestCache: Option[(Int, ToplevelState)] =
      initCache
        .entrySet()
        .asScala
        .collect {
          case e if e.getKey._1 == thyPath && e.getKey._2 <= targetLine =>
            val st = stateMap.get(e.getValue)
            if (st != null) Some((e.getKey._2, st)) else None
        }
        .flatten
        .maxByOption(_._1)

    val (startLine, startState) = bestCache.getOrElse {
      (0, theoryManager.initToplevel())
    }

    // Collect transitions to replay: line > startLine AND line <= targetLine
    val toExecute: List[(Transition, String)] =
      cached.transitions.filter { case (tr, _) =>
        val line = tr.position.line.getOrElse(0)
        line > startLine && line <= targetLine
      }

    var currentState = startState
    var lastSuccessState = startState
    var lastSuccessLine = startLine

    for ((tr, _) <- toExecute) {
      val line = tr.position.line.getOrElse(0)
      try {
        currentState = asyncExecute(List(tr), currentState, timeoutMs)
        lastSuccessState = currentState
        lastSuccessLine = line
      } catch {
        case e: Exception =>
          val errMsg = e.getMessage
          val errStatus =
            if (errMsg.contains("Timeout after")) ExecStatus.TIMEOUT
            else ExecStatus.ERROR
          log.warning(
            s"Session $sessionId: initState failed at line $line — $errMsg"
          )
          // Store last-success state only if we made at least one step
          val lastSuccessOpt: Option[ProtoStateResult] =
            if (lastSuccessLine > 0) {
              val id = UUID.randomUUID().toString
              stateMap.put(id, lastSuccessState)
              Some(
                buildResult(
                  id,
                  lastSuccessState,
                  ExecStatus.SUCCESS,
                  includeText = includeText
                )
              )
            } else None

          return InitStateResponse(
            InitStateResponse.Result.Error(
              ProtoInitStateError(
                failedLine = line,
                errorMsg = errMsg,
                lastSuccess = lastSuccessOpt
              )
            )
          )
      }
    }

    // Success: register in stateMap and cache
    val newId = UUID.randomUUID().toString
    stateMap.put(newId, currentState)
    val cacheKey = (thyPath, targetLine)
    initCache.put(cacheKey, newId)
    initCacheKeys.put(newId, cacheKey)

    InitStateResponse(
      InitStateResponse.Result.Success(
        buildResult(
          newId,
          currentState,
          ExecStatus.SUCCESS,
          includeText = includeText
        )
      )
    )
  }

  /** Execute a tactic against a source state, always producing a fresh state
    * ID. The source state is never modified.
    */
  def execute(
      sourceStateId: String,
      tactic: String,
      timeoutMs: Int,
      includeText: Boolean = false
  ): ProtoStateResult = {
    val sourceState = stateMap.get(sourceStateId)
    val trs = Transition.parseOuterSyntax(sourceState.theory, tactic).map(_._1)

    val (newState, status, errorMsg): (ToplevelState, ExecStatus, String) =
      try {
        val s = asyncExecute(trs, sourceState, timeoutMs)
        val st =
          if (sourceState.proofLevel > 0 && s.proofLevel == 0)
            ExecStatus.PROOF_COMPLETE
          else ExecStatus.SUCCESS
        (s, st, "")
      } catch {
        case e: IsabelleMLException =>
          val errStatus =
            if (e.getMessage.contains("Timeout after")) ExecStatus.TIMEOUT
            else ExecStatus.ERROR
          (sourceState, errStatus, e.getMessage)
        case e: IsabelleControllerException =>
          (sourceState, ExecStatus.ERROR, e.getMessage)
      }

    val newId = UUID.randomUUID().toString
    stateMap.put(newId, newState)
    if (status == ExecStatus.ERROR || status == ExecStatus.TIMEOUT)
      log.warning(s"Session $sessionId: execute $status — $errorMsg")
    buildResult(newId, newState, status, errorMsg, includeText)
  }

  /** Execute multiple tactics in parallel from the same (immutable) source
    * state. ToplevelState is an immutable ML value so no cloning is needed.
    */
  def executeBatch(
      sourceStateId: String,
      tactics: List[String],
      timeoutMs: Int,
      dropFailed: Boolean
  ): List[ProtoStateResult] = {
    val futures = Future.traverse(tactics) { tactic =>
      Future(execute(sourceStateId, tactic, timeoutMs))
    }
    val results = Await.result(futures, Duration.Inf)
    if (dropFailed) {
      results.foreach { r =>
        if (r.status == ExecStatus.ERROR || r.status == ExecStatus.TIMEOUT)
          stateMap.remove(r.stateId)
      }
    }
    results
  }

  /** Run Sledgehammer on the given proof state. */
  def runSledgehammer(
      sourceStateId: String,
      timeoutMs: Int,
      sledgehammerTimeoutMs: Int
  ): (Boolean, String, Option[ProtoStateResult]) = {
    val sourceState = stateMap.get(sourceStateId)
    val sledgehammerTimeoutSec = (sledgehammerTimeoutMs / 1000).max(1)
    val (found, _, commands) =
      theoryManager.applySledgehammer(
        sourceState,
        sourceState.theory,
        sledgehammerTimeoutSec
      )
    if (!found || commands.isEmpty) {
      log.fine(s"Session $sessionId: Sledgehammer found no proof")
      (false, "", None)
    } else {
      val tactic = commands.head
      log.info(s"Session $sessionId: Sledgehammer succeeded — $tactic")
      val result = execute(sourceStateId, tactic, timeoutMs)
      (true, tactic, Some(result))
    }
  }

  /** Return state metadata, optionally including the full proof state text. */
  def getStateInfo(
      stateId: String,
      includeText: Boolean
  ): (StateMode, Int, String) = {
    val state = stateMap.get(stateId)
    (modeOf(state), state.proofLevel, proofStateText(state, includeText))
  }

  def dropState(stateIds: Seq[String]): Unit =
    stateIds.foreach { id =>
      stateMap.remove(id)
      // Also evict any initCache entry pointing to this state so a future
      // initState call re-executes rather than returning a dead reference.
      Option(initCacheKeys.remove(id)).foreach(initCache.remove)
    }

  def dropAllStates(): Unit = {
    stateMap.clear()
    initCache.clear()
    initCacheKeys.clear()
  }

  def close(): Unit = {
    log.info(s"Session $sessionId: closing Isabelle process")
    isabelle.destroy()
  }
}

object IsabelleSession extends OperationCollection {
  protected final class Ops(implicit isabelle: Isabelle) {
    // Reused verbatim from old IsabelleServer.scala:318–332
    lazy val commandExceptionWithTimeout =
      compileFunction[Long, Boolean, List[
        Transition
      ], ToplevelState, ToplevelState](
        """fn (timeout, int, trs, st) =>
          |  Timeout.apply (Time.fromMilliseconds timeout) (fold (Toplevel.command_exception int) trs) st
        """.stripMargin
      )
  }

  override protected def newOps(implicit isabelle: Isabelle) = new Ops
}
