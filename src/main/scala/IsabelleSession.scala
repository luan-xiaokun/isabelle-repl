package isa.repl

import java.util.concurrent.ConcurrentHashMap
import java.util.logging.Logger

import scala.jdk.CollectionConverters._

import de.unruh.isabelle.control.{
  Isabelle,
  IsabelleControllerException,
  IsabelleMLException,
  OperationCollection
}
import de.unruh.isabelle.control.Isabelle.executionContext
import de.unruh.isabelle.mlvalue.Implicits._
import de.unruh.isabelle.mlvalue.MLValue.compileFunction
import de.unruh.isabelle.pure.Implicits._
import de.unruh.isabelle.pure.ToplevelState.Modes
import de.unruh.isabelle.pure.{Theory, ToplevelState, Transition}

import IsabelleSession.Ops
import isa.repl.{ExecStatus, StateMode, StateResult => ProtoStateResult}

case class CachedTheory(
    transitions: List[(Transition, String)]
)

sealed trait ComputedInitState

final case class ComputedInitSuccess(
    state: ToplevelState,
    cacheKey: (os.Path, Int)
) extends ComputedInitState

final case class ComputedInitFailure(
    failedLine: Int,
    errorMsg: String,
    lastSuccessState: Option[ToplevelState],
    code: InitStateErrorCode,
    candidateLines: List[Int] = Nil
) extends ComputedInitState

final case class ComputedState(
    state: ToplevelState,
    status: ExecStatus,
    errorMsg: String = ""
)

final case class ComputedSledgehammer(
    found: Boolean,
    tactic: String,
    result: Option[ComputedState]
)

/** Wraps a single Isabelle process (one logic/heap image).
  *
  * Lifecycle orchestration lives in [[IsaReplService]]. This class only owns
  * local caches/state and executes Isabelle operations.
  */
class IsabelleSession(
    val sessionId: String,
    val isaPath: os.Path,
    val logic: String,
    val workDir: os.Path,
    sessionRoots: List[os.Path],
    workspaceCatalog: WorkspaceCatalog
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

  locally {
    if (workspaceCatalog.registeredSessionDirectories.nonEmpty)
      Theory.registerSessionDirectoriesNow(
        workspaceCatalog.registeredSessionDirectories: _*
      )(isabelle)
  }

  private val theoryManager =
    new TheoryManager(workspaceCatalog.workDirSessionName, workspaceCatalog)

  val theoryCache = new ConcurrentHashMap[os.Path, CachedTheory]()
  val stateMap = new ConcurrentHashMap[String, ToplevelState]()
  private val initCache = new ConcurrentHashMap[(os.Path, Int), String]()
  private val initCacheKeys = new ConcurrentHashMap[String, (os.Path, Int)]()

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

  private def requireStateLocal(stateId: String): ToplevelState =
    Option(stateMap.get(stateId))
      .getOrElse(throw new IllegalStateException(s"State not found: $stateId"))

  private def loadAndCacheImpl(thyPath: os.Path): CachedTheory = {
    val t0 = System.currentTimeMillis()
    log.info(s"Session $sessionId: parsing theory ${thyPath.last}")
    val thyText = os.read(thyPath)
    val thy = theoryManager.beginTheory(thyText, thyPath)
    val transitions =
      theoryManager
        .getThyTransitions(thy, thyText, removeComments = false)
        .filterNot { case (tr, _) => tr.isIgnored }
    val elapsed = System.currentTimeMillis() - t0
    log.info(
      s"Session $sessionId: theory ${thyPath.last} parsed" +
        s" (${transitions.length} transitions, ${elapsed}ms)"
    )
    CachedTheory(transitions)
  }

  def loadTheory(thyPath: os.Path): Int = {
    val cached = theoryCache.computeIfAbsent(thyPath, p => loadAndCacheImpl(p))
    cached.transitions.length
  }

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

  def hasStateLocal(stateId: String): Boolean = stateMap.containsKey(stateId)

  /** Local invariant: init-cache entries only point at still-live local states.
    */
  def storeStateLocal(
      stateId: String,
      state: ToplevelState,
      cacheKey: Option[(os.Path, Int)] = None
  ): Unit = {
    stateMap.put(stateId, state)
    cacheKey.foreach { key =>
      initCache.put(key, stateId)
      initCacheKeys.put(stateId, key)
    }
  }

  def dropStateLocal(stateIds: Seq[String]): Unit =
    stateIds.foreach { stateId =>
      stateMap.remove(stateId)
      Option(initCacheKeys.remove(stateId)).foreach(initCache.remove)
    }

  def dropAllStatesLocal(): Unit = {
    stateMap.clear()
    initCache.clear()
    initCacheKeys.clear()
  }

  def computeInitState(
      thyPath: os.Path,
      position: Either[Int, String],
      timeoutMs: Int
  ): ComputedInitState = {
    val cached = theoryCache.computeIfAbsent(thyPath, p => loadAndCacheImpl(p))
    val transitionsWithLines = cached.transitions.map { case (tr, cmd) =>
      (tr.position.line.getOrElse(0), (tr, cmd))
    }
    val commandsWithLines = transitionsWithLines.map { case (line, (_, cmd)) =>
      (line, cmd)
    }

    val targetLine =
      ReplayPlanner.resolveTargetLine(commandsWithLines, position) match {
        case Right(line)         => line
        case Left(selectorError) =>
          return ComputedInitFailure(
            failedLine = 0,
            errorMsg = selectorError.message,
            lastSuccessState = None,
            code = selectorError.code,
            candidateLines = selectorError.candidateLines
          )
      }

    val bestCache =
      initCache
        .entrySet()
        .asScala
        .collect {
          case e if e.getKey._1 == thyPath && e.getKey._2 <= targetLine =>
            Option(stateMap.get(e.getValue)).map(st => (e.getKey._2, st))
        }
        .flatten
        .maxByOption(_._1)

    val (startLine, startState) =
      bestCache.getOrElse((0, theoryManager.initToplevel()))

    val toExecute =
      ReplayPlanner.transitionsBetweenLines(
        transitionsWithLines,
        startLine,
        targetLine
      )

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
          log.warning(
            s"Session $sessionId: initState failed at line $line — $errMsg"
          )
          val lastSuccessOpt =
            if (lastSuccessLine > 0) Some(lastSuccessState) else None
          val code =
            e match {
              case ml: IsabelleMLException
                  if Option(ml.getMessage).exists(
                    _.contains("Timeout after")
                  ) =>
                InitStateErrorCode.INIT_STATE_TIMEOUT
              case _ =>
                InitStateErrorCode.INIT_STATE_EXECUTION_FAILED
            }
          return ComputedInitFailure(
            line,
            errMsg,
            lastSuccessOpt,
            code = code
          )
      }
    }

    ComputedInitSuccess(currentState, (thyPath, targetLine))
  }

  def computeExecute(
      sourceStateId: String,
      tactic: String,
      timeoutMs: Int
  ): ComputedState = {
    val sourceState = requireStateLocal(sourceStateId)
    val trs = Transition.parseOuterSyntax(sourceState.theory, tactic).map(_._1)

    try {
      val newState = asyncExecute(trs, sourceState, timeoutMs)
      val status =
        if (sourceState.proofLevel > 0 && newState.proofLevel == 0)
          ExecStatus.PROOF_COMPLETE
        else ExecStatus.SUCCESS
      ComputedState(newState, status)
    } catch {
      case e: IsabelleMLException =>
        val status =
          if (e.getMessage.contains("Timeout after")) ExecStatus.TIMEOUT
          else ExecStatus.ERROR
        log.warning(s"Session $sessionId: execute $status — ${e.getMessage}")
        ComputedState(sourceState, status, e.getMessage)
      case e: IsabelleControllerException =>
        log.warning(s"Session $sessionId: execute ERROR — ${e.getMessage}")
        ComputedState(sourceState, ExecStatus.ERROR, e.getMessage)
    }
  }

  def computeExecuteBatch(
      sourceStateId: String,
      tactics: List[String],
      timeoutMs: Int
  ): List[ComputedState] =
    tactics.map(tactic => computeExecute(sourceStateId, tactic, timeoutMs))

  def computeRunSledgehammer(
      sourceStateId: String,
      timeoutMs: Int,
      sledgehammerTimeoutMs: Int
  ): ComputedSledgehammer = {
    val sourceState = requireStateLocal(sourceStateId)
    val sledgehammerTimeoutSec = (sledgehammerTimeoutMs / 1000).max(1)
    val (found, _, commands) =
      theoryManager.applySledgehammer(
        sourceState,
        sourceState.theory,
        sledgehammerTimeoutSec
      )
    if (!found || commands.isEmpty) {
      log.fine(s"Session $sessionId: Sledgehammer found no proof")
      ComputedSledgehammer(found = false, tactic = "", result = None)
    } else {
      val tactic = commands.head
      log.info(s"Session $sessionId: Sledgehammer succeeded — $tactic")
      ComputedSledgehammer(
        found = true,
        tactic = tactic,
        result = Some(computeExecute(sourceStateId, tactic, timeoutMs))
      )
    }
  }

  def buildStateResult(
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

  def getStateInfoLocal(
      stateId: String,
      includeText: Boolean
  ): (StateMode, Int, String) = {
    val state = requireStateLocal(stateId)
    (modeOf(state), state.proofLevel, proofStateText(state, includeText))
  }

  def close(): Unit = {
    log.info(s"Session $sessionId: closing Isabelle process")
    isabelle.destroy()
  }
}

object IsabelleSession extends OperationCollection {
  protected final class Ops(implicit isabelle: Isabelle) {
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
