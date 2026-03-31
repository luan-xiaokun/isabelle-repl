package isa.repl

import java.util.UUID
import java.util.concurrent.{ConcurrentHashMap, Executors}
import java.util.logging.Logger

import scala.concurrent.{ExecutionContext, Future}

import de.unruh.isabelle.control.{
  IsabelleControllerException,
  IsabelleMLException
}
import de.unruh.isabelle.pure.ToplevelState
import io.grpc.{Server, Status, StatusRuntimeException}
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder

import isa.repl._

final class ManagedSession(
    val sessionId: String,
    val session: IsabelleSession,
    val sessionRootIndex: SessionRootIndex,
    val theorySourceIndex: TheorySourceIndex
) {
  val lock: AnyRef = new AnyRef
  private var closing = false

  def isClosingLocked: Boolean = closing

  def startClosingLocked(): Unit =
    closing = true
}

class IsaReplService(implicit ec: ExecutionContext)
    extends IsabelleREPLGrpc.IsabelleREPL {

  private val log = Logger.getLogger(classOf[IsaReplService].getName)
  private val sessionMap = new ConcurrentHashMap[String, ManagedSession]()
  private val stateRegistry = new StateRegistry()

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

  private def getManagedSession(sessionId: String): ManagedSession = {
    val managed = sessionMap.get(sessionId)
    if (managed == null)
      throw new StatusRuntimeException(
        Status.NOT_FOUND.withDescription(s"Session not found: $sessionId")
      )
    managed
  }

  private def sessionClosing(sessionId: String): Nothing =
    throw new StatusRuntimeException(
      Status.FAILED_PRECONDITION.withDescription(
        s"Session is closing: $sessionId"
      )
    )

  private def stateNotFound(stateId: String): Nothing =
    throw new StatusRuntimeException(
      Status.NOT_FOUND.withDescription(s"State not found: $stateId")
    )

  private def withActiveManagedSession[T](
      sessionId: String
  )(f: ManagedSession => T): T = {
    val managed = getManagedSession(sessionId)
    managed.lock.synchronized {
      if (managed.isClosingLocked) sessionClosing(sessionId)
      f(managed)
    }
  }

  private def ensureLiveStateLocked(
      managed: ManagedSession,
      stateId: String
  ): Unit = {
    if (
      !stateRegistry.isLiveStateInSession(
        managed.sessionId,
        stateId,
        managed.session
      )
    )
      stateNotFound(stateId)
  }

  private def withManagedState[T](stateId: String)(f: ManagedSession => T): T = {
    val ownerSessionId = stateRegistry.ownerOf(stateId).getOrElse {
      stateNotFound(stateId)
    }
    val managed =
      Option(sessionMap.get(ownerSessionId)).getOrElse(stateNotFound(stateId))
    managed.lock.synchronized {
      if (managed.isClosingLocked) sessionClosing(managed.sessionId)
      ensureLiveStateLocked(managed, stateId)
      f(managed)
    }
  }

  private def registerStateLocked(
      managed: ManagedSession,
      stateId: String,
      state: ToplevelState,
      cacheKey: Option[(os.Path, Int)] = None
  ): Unit =
    stateRegistry.registerState(
      managed.sessionId,
      stateId,
      managed.session,
      state,
      cacheKey
    )

  private def dropStateLocked(managed: ManagedSession, stateId: String): Unit =
    stateRegistry.dropStateIfOwned(managed.sessionId, stateId, managed.session)

  private def dropAllStatesLocked(managed: ManagedSession): Unit =
    stateRegistry.dropAllStatesForSession(managed.sessionId, managed.session)

  def createSession(
      request: CreateSessionRequest
  ): Future[CreateSessionResponse] =
    futureWrapper {
      val sessionId = UUID.randomUUID().toString
      val workDir = os.Path(request.workingDirectory)
      val sessionRoots = request.sessionRoots.map(os.Path(_)).toList
      val sessionRootIndex =
        SessionRootIndex.build(request.logic, workDir, sessionRoots)
      val theorySourceIndex =
        TheorySourceIndex.build(workDir, sessionRootIndex.workDirSessionName)
      val session = new IsabelleSession(
        sessionId = sessionId,
        isaPath = os.Path(request.isaPath),
        logic = request.logic,
        workDir = workDir,
        sessionRoots = sessionRoots,
        registeredSessionDirectories =
          sessionRootIndex.registeredSessionDirectories,
        workDirSessionName = sessionRootIndex.workDirSessionName,
        theorySourceIndex = theorySourceIndex
      )
      sessionMap.put(
        sessionId,
        new ManagedSession(sessionId, session, sessionRootIndex, theorySourceIndex)
      )
      CreateSessionResponse(sessionId = sessionId)
    }

  def destroySession(
      request: SessionRef
  ): Future[Empty] =
    futureWrapper {
      val managed = getManagedSession(request.sessionId)
      managed.lock.synchronized {
        if (managed.isClosingLocked) sessionClosing(request.sessionId)
        managed.startClosingLocked()
        dropAllStatesLocked(managed)
        managed.session.close()
        sessionMap.remove(request.sessionId, managed)
      }
      Empty()
    }

  def loadTheory(
      request: LoadTheoryRequest
  ): Future[LoadTheoryResponse] =
    futureWrapper {
      withActiveManagedSession(request.sessionId) { managed =>
        val commandCount = managed.session.loadTheory(os.Path(request.theoryPath))
        LoadTheoryResponse(
          theoryPath = request.theoryPath,
          commandCount = commandCount
        )
      }
    }

  def listTheoryCommands(
      request: ListCommandsRequest
  ): Future[ListCommandsResponse] =
    futureWrapper {
      withActiveManagedSession(request.sessionId) { managed =>
        val commands = managed.session.listTheoryCommands(
          os.Path(request.theoryPath),
          request.onlyProofStmts
        )
        ListCommandsResponse(
          commands = commands.map { case (text, kind, line) =>
            TheoryCommand(text = text, kind = kind, line = line)
          }
        )
      }
    }

  def initState(
      request: InitStateRequest
  ): Future[InitStateResponse] =
    futureWrapper {
      withActiveManagedSession(request.sessionId) { managed =>
        val position = request.position match {
          case InitStateRequest.Position.AfterLine(n)    => Left(n)
          case InitStateRequest.Position.AfterCommand(s) => Right(s)
          case InitStateRequest.Position.Empty           => Left(Int.MaxValue)
        }
        val timeoutMs = if (request.timeoutMs > 0) request.timeoutMs else 60000
        managed.session.computeInitState(
          os.Path(request.theoryPath),
          position,
          timeoutMs
        ) match {
          case ComputedInitSuccess(state, cacheKey) =>
            val stateId = UUID.randomUUID().toString
            registerStateLocked(managed, stateId, state, Some(cacheKey))
            InitStateResponse(
              InitStateResponse.Result.Success(
                managed.session.buildStateResult(
                  stateId,
                  state,
                  ExecStatus.SUCCESS,
                  includeText = request.includeText
                )
              )
            )
          case ComputedInitFailure(
                failedLine,
                errorMsg,
                lastSuccessState,
                code,
                candidateLines
              ) =>
            val lastSuccess =
              lastSuccessState.map { state =>
                val stateId = UUID.randomUUID().toString
                registerStateLocked(managed, stateId, state)
                managed.session.buildStateResult(
                  stateId,
                  state,
                  ExecStatus.SUCCESS,
                  includeText = request.includeText
                )
              }
            InitStateResponse(
              InitStateResponse.Result.Error(
                InitStateError(
                  failedLine = failedLine,
                  errorMsg = errorMsg,
                  lastSuccess = lastSuccess,
                  code = code,
                  candidateLines = candidateLines
                )
              )
            )
        }
      }
    }

  def dropState(
      request: DropStateRequest
  ): Future[Empty] =
    futureWrapper {
      val uniqueStateIds = request.stateIds.distinct
      val stateIdsBySession = stateRegistry.groupStateIdsByOwner(uniqueStateIds)

      uniqueStateIds.foreach { stateId =>
        if (stateRegistry.ownerOf(stateId).isEmpty)
          log.fine(s"DropState ignored unknown state_id=$stateId")
      }

      stateIdsBySession.foreach { case (sessionId, stateIds) =>
        Option(sessionMap.get(sessionId)).foreach { managed =>
          managed.lock.synchronized {
            stateIds.foreach(stateId => dropStateLocked(managed, stateId))
          }
        }
      }
      Empty()
    }

  def dropAllStates(
      request: SessionRef
  ): Future[Empty] =
    futureWrapper {
      withActiveManagedSession(request.sessionId) { managed =>
        dropAllStatesLocked(managed)
        Empty()
      }
    }

  def execute(
      request: ExecuteRequest
  ): Future[StateResult] =
    futureWrapper {
      withManagedState(request.sourceStateId) { managed =>
        val timeoutMs = if (request.timeoutMs > 0) request.timeoutMs else 30000
        val computed = managed.session.computeExecute(
          request.sourceStateId,
          request.tactic,
          timeoutMs
        )
        val stateId = UUID.randomUUID().toString
        registerStateLocked(managed, stateId, computed.state)
        managed.session.buildStateResult(
          stateId,
          computed.state,
          computed.status,
          computed.errorMsg,
          request.includeText
        )
      }
    }

  def executeBatch(
      request: ExecuteBatchRequest
  ): Future[ExecuteBatchResponse] =
    futureWrapper {
      withManagedState(request.sourceStateId) { managed =>
        val timeoutMs = if (request.timeoutMs > 0) request.timeoutMs else 30000
        val computedResults = managed.session.computeExecuteBatch(
          request.sourceStateId,
          request.tactics.toList,
          timeoutMs
        )
        val resultsWithIds = computedResults.map { computed =>
          val stateId = UUID.randomUUID().toString
          registerStateLocked(managed, stateId, computed.state)
          (
            stateId,
            managed.session.buildStateResult(
              stateId,
              computed.state,
              computed.status,
              computed.errorMsg
            )
          )
        }
        if (request.dropFailed) {
          resultsWithIds.foreach { case (stateId, result) =>
            if (
              result.status == ExecStatus.ERROR ||
              result.status == ExecStatus.TIMEOUT
            )
              dropStateLocked(managed, stateId)
          }
        }
        ExecuteBatchResponse(results = resultsWithIds.map(_._2))
      }
    }

  def runSledgehammer(
      request: SledgehammerRequest
  ): Future[SledgehammerResponse] =
    futureWrapper {
      withManagedState(request.sourceStateId) { managed =>
        val timeoutMs = if (request.timeoutMs > 0) request.timeoutMs else 30000
        val sledgehammerTimeoutMs =
          if (request.sledgehammerTimeoutMs > 0) request.sledgehammerTimeoutMs
          else 30000
        val computed = managed.session.computeRunSledgehammer(
          request.sourceStateId,
          timeoutMs,
          sledgehammerTimeoutMs
        )
        val resultOpt = computed.result.map { result =>
          val stateId = UUID.randomUUID().toString
          registerStateLocked(managed, stateId, result.state)
          managed.session.buildStateResult(
            stateId,
            result.state,
            result.status,
            result.errorMsg
          )
        }
        SledgehammerResponse(
          found = computed.found,
          tactic = computed.tactic,
          result = resultOpt
        )
      }
    }

  def getStateInfo(
      request: GetStateInfoRequest
  ): Future[StateInfo] =
    futureWrapper {
      withManagedState(request.stateId) { managed =>
        val (mode, proofLevel, text) =
          managed.session.getStateInfoLocal(request.stateId, request.includeText)
        StateInfo(
          stateId = request.stateId,
          mode = mode,
          proofLevel = proofLevel,
          proofStateText = text,
          localTheoryDesc = ""
        )
      }
    }
}

object IsaReplServer {
  val Port = 50051
  private val log = Logger.getLogger(IsaReplServer.getClass.getName)

  def main(args: Array[String]): Unit = {
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
