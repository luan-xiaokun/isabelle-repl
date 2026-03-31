package io.github.luanxiaokun.isabellerepl

sealed trait SessionBootstrapError {
  def message: String
}

final case class MissingPath(
    label: String,
    path: os.Path
) extends SessionBootstrapError {
  override def message: String = s"Missing $label: $path"
}

final case class NotDirectory(
    label: String,
    path: os.Path
) extends SessionBootstrapError {
  override def message: String = s"Expected directory for $label: $path"
}

final case class WorkspaceBootstrapFailure(
    error: WorkspaceCatalogError
) extends SessionBootstrapError {
  override def message: String = error.message
}

final case class SessionBootstrapPlan(
    sessionId: String,
    isaPath: os.Path,
    logic: String,
    workDir: os.Path,
    sessionRoots: List[os.Path],
    workspaceCatalog: WorkspaceCatalog
) {
  def createSession(): IsabelleSession =
    new IsabelleSession(
      sessionId = sessionId,
      isaPath = isaPath,
      logic = logic,
      workDir = workDir,
      sessionRoots = sessionRoots,
      workspaceCatalog = workspaceCatalog
    )
}

object SessionBootstrap {
  private def requireDirectory(
      label: String,
      path: os.Path
  ): Either[SessionBootstrapError, Unit] =
    if (!os.exists(path)) Left(MissingPath(label, path))
    else if (!os.isDir(path)) Left(NotDirectory(label, path))
    else Right(())

  def build(
      sessionId: String,
      isaPath: os.Path,
      logic: String,
      workDir: os.Path,
      sessionRoots: List[os.Path]
  ): Either[SessionBootstrapError, SessionBootstrapPlan] = {
    val checks = List(
      requireDirectory("isabelle home", isaPath),
      requireDirectory("working directory", workDir)
    ) ++ sessionRoots.map(path => requireDirectory("session root", path))

    checks.collectFirst { case Left(error) => error } match {
      case Some(error) =>
        Left(error)
      case None =>
        WorkspaceCatalog
          .build(logic, workDir, sessionRoots)
          .left
          .map(WorkspaceBootstrapFailure.apply)
          .map { workspaceCatalog =>
            SessionBootstrapPlan(
              sessionId = sessionId,
              isaPath = isaPath,
              logic = logic,
              workDir = workDir,
              sessionRoots = sessionRoots,
              workspaceCatalog = workspaceCatalog
            )
          }
    }
  }
}
