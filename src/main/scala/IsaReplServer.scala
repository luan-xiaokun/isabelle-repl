package isa.repl

import java.util.UUID
import java.util.concurrent.{ConcurrentHashMap, Executors}
import scala.concurrent.{ExecutionContext, Future}
import scala.jdk.CollectionConverters._

import de.unruh.isabelle.control.{
  IsabelleControllerException,
  IsabelleMLException
}
import de.unruh.isabelle.pure.ToplevelState
import io.grpc.{Server, Status, StatusRuntimeException}
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder
import java.util.logging.Logger

import isa.repl._

class IsaReplService(implicit ec: ExecutionContext)
    extends IsabelleREPLGrpc.IsabelleREPL {

  private val log = Logger.getLogger(classOf[IsaReplService].getName)
  private val sessionMap = new ConcurrentHashMap[String, IsabelleSession]()

  // ── Error handling ────────────────────────────────────────────────────────

  private def tryWrapper[T](f: => T): T =
    try {
      f
    } catch {
      case e: IsabelleMLException =>
        log.warning(s"Isabelle ML error: ${e.getMessage}")
        throw new StatusRuntimeException(
          Status.INTERNAL.withDescription(e.getMessage)
        )
      case e: IsabelleControllerException =>
        log.warning(s"Isabelle controller error: ${e.getMessage}")
        throw new StatusRuntimeException(
          Status.INTERNAL.withDescription(e.getMessage)
        )
    }

  private def futureWrapper[T](f: => T): Future[T] =
    Future(tryWrapper(f))

  private def getSession(sessionId: String): IsabelleSession = {
    val s = sessionMap.get(sessionId)
    if (s == null)
      throw new StatusRuntimeException(
        Status.NOT_FOUND.withDescription(s"Session not found: $sessionId")
      )
    s
  }

  /** Find the session that owns a given state ID. */
  private def findStateOwner(
      stateId: String
  ): (IsabelleSession, ToplevelState) =
    sessionMap
      .values()
      .asScala
      .flatMap { s => Option(s.stateMap.get(stateId)).map(st => (s, st)) }
      .headOption
      .getOrElse(
        throw new StatusRuntimeException(
          Status.NOT_FOUND.withDescription(s"State not found: $stateId")
        )
      )

  // ── Session ───────────────────────────────────────────────────────────────

  def createSession(
      request: CreateSessionRequest
  ): Future[CreateSessionResponse] =
    futureWrapper {
      val sessionId = UUID.randomUUID().toString
      val session = new IsabelleSession(
        sessionId = sessionId,
        isaPath = os.Path(request.isaPath),
        logic = request.logic,
        workDir = os.Path(request.workingDirectory),
        sessionRoots = request.sessionRoots.map(os.Path(_)).toList
      )
      sessionMap.put(sessionId, session)
      CreateSessionResponse(sessionId = sessionId)
    }

  def destroySession(
      request: SessionRef
  ): Future[Empty] =
    futureWrapper {
      val session = getSession(request.sessionId)
      session.close()
      sessionMap.remove(request.sessionId)
      Empty()
    }

  // ── Theory ────────────────────────────────────────────────────────────────

  def loadTheory(
      request: LoadTheoryRequest
  ): Future[LoadTheoryResponse] =
    futureWrapper {
      val session = getSession(request.sessionId)
      val commandCount = session.loadTheory(os.Path(request.theoryPath))
      LoadTheoryResponse(
        theoryPath = request.theoryPath,
        commandCount = commandCount
      )
    }

  def listTheoryCommands(
      request: ListCommandsRequest
  ): Future[ListCommandsResponse] =
    futureWrapper {
      val session = getSession(request.sessionId)
      val commands = session.listTheoryCommands(
        os.Path(request.theoryPath),
        request.onlyProofStmts
      )
      ListCommandsResponse(
        commands = commands.map { case (text, kind, line) =>
          TheoryCommand(text = text, kind = kind, line = line)
        }
      )
    }

  // ── ProofState lifecycle ──────────────────────────────────────────────────

  def initState(
      request: InitStateRequest
  ): Future[InitStateResponse] =
    futureWrapper {
      val session = getSession(request.sessionId)
      val position = request.position match {
        case InitStateRequest.Position.AfterLine(n)    => Left(n)
        case InitStateRequest.Position.AfterCommand(s) => Right(s)
        case InitStateRequest.Position.Empty           => Left(Int.MaxValue)
      }
      val timeoutMs = if (request.timeoutMs > 0) request.timeoutMs else 60000
      session.initState(
        os.Path(request.theoryPath),
        position,
        timeoutMs,
        request.includeText
      )
    }

  def dropState(
      request: DropStateRequest
  ): Future[Empty] =
    futureWrapper {
      // Best-effort drop across all sessions (state IDs are globally unique UUIDs)
      sessionMap.values().asScala.foreach(_.dropState(request.stateIds))
      Empty()
    }

  def dropAllStates(
      request: SessionRef
  ): Future[Empty] =
    futureWrapper {
      val session = getSession(request.sessionId)
      session.dropAllStates()
      Empty()
    }

  // ── Execution ─────────────────────────────────────────────────────────────

  def execute(
      request: ExecuteRequest
  ): Future[StateResult] =
    futureWrapper {
      val (session, _) = findStateOwner(request.sourceStateId)
      val timeoutMs = if (request.timeoutMs > 0) request.timeoutMs else 30000
      session.execute(
        request.sourceStateId,
        request.tactic,
        timeoutMs,
        request.includeText
      )
    }

  def executeBatch(
      request: ExecuteBatchRequest
  ): Future[ExecuteBatchResponse] =
    futureWrapper {
      val (session, _) = findStateOwner(request.sourceStateId)
      val timeoutMs = if (request.timeoutMs > 0) request.timeoutMs else 30000
      val results = session.executeBatch(
        request.sourceStateId,
        request.tactics.toList,
        timeoutMs,
        request.dropFailed
      )
      ExecuteBatchResponse(results = results)
    }

  // ── Sledgehammer ──────────────────────────────────────────────────────────

  def runSledgehammer(
      request: SledgehammerRequest
  ): Future[SledgehammerResponse] =
    futureWrapper {
      val (session, _) = findStateOwner(request.sourceStateId)
      val timeoutMs = if (request.timeoutMs > 0) request.timeoutMs else 30000
      val sledgehammerTimeoutMs =
        if (request.sledgehammerTimeoutMs > 0) request.sledgehammerTimeoutMs
        else 30000
      val (found, tactic, resultOpt) =
        session.runSledgehammer(
          request.sourceStateId,
          timeoutMs,
          sledgehammerTimeoutMs
        )
      SledgehammerResponse(found = found, tactic = tactic, result = resultOpt)
    }

  // ── Query ─────────────────────────────────────────────────────────────────

  def getStateInfo(
      request: GetStateInfoRequest
  ): Future[StateInfo] =
    futureWrapper {
      val (session, _) = findStateOwner(request.stateId)
      val (mode, proofLevel, text) =
        session.getStateInfo(request.stateId, request.includeText)
      StateInfo(
        stateId = request.stateId,
        mode = mode,
        proofLevel = proofLevel,
        proofStateText = text
      )
    }
}

object IsaReplServer {
  val Port = 50051
  private val log = Logger.getLogger(IsaReplServer.getClass.getName)

  def main(args: Array[String]): Unit = {
    // Single-line log format: "2026-03-20 10:24:28 INFO    isa.repl.Foo — message"
    System.setProperty(
      "java.util.logging.SimpleFormatter.format",
      "%1$tY-%1$tm-%1$td %1$tH:%1$tM:%1$tS %4$-7s %3$s — %5$s%6$s%n"
    )
    val rootLogger = java.util.logging.Logger.getLogger("")
    rootLogger.getHandlers.foreach(
      _.setFormatter(new java.util.logging.SimpleFormatter())
    )

    val isabelleExecutor = Executors.newCachedThreadPool()
    implicit val ec: ExecutionContext =
      ExecutionContext.fromExecutor(isabelleExecutor)
    val server: Server = NettyServerBuilder
      .forPort(Port)
      .addService(IsabelleREPLGrpc.bindService(new IsaReplService, ec))
      .build()
      .start()
    log.info(s"IsaReplServer ready — listening on port $Port")

    Runtime.getRuntime.addShutdownHook(new Thread(() => {
      log.info("Shutdown signal received, stopping server")
      server.shutdown()
      isabelleExecutor.shutdown()
    }))
    server.awaitTermination()
  }
}
