package io.github.luanxiaokun.isabellerepl

import io.grpc.Status
import org.scalatest.funsuite.AnyFunSuite

class SessionBootstrapTest extends AnyFunSuite {

  private def withTempDir(prefix: String)(f: os.Path => Unit): Unit = {
    val dir = os.temp.dir(prefix = prefix)
    try f(dir)
    finally os.remove.all(dir)
  }

  test("SessionBootstrap.build returns complete plan for valid workspace") {
    withTempDir("session-bootstrap-valid-") { root =>
      val isaHome = root / "Isabelle2025"
      os.makeDir.all(isaHome / "src" / "HOL")

      val workDir = root / "Work"
      os.makeDir(workDir)
      os.write(
        workDir / "ROOT",
        """session Demo = HOL +""".stripMargin
      )
      os.write(workDir / "Demo.thy", "theory Demo imports Main begin end")

      val result = SessionBootstrap.build(
        sessionId = "bootstrap-ok",
        isaPath = isaHome,
        logic = "HOL",
        workDir = workDir,
        sessionRoots = List(isaHome / "src" / "HOL", workDir)
      )

      assert(result.isRight)
      val plan = result.toOption.get
      assert(plan.sessionId == "bootstrap-ok")
      assert(plan.logic == "HOL")
      assert(plan.workspaceCatalog.workDirSessionName == "Demo")
    }
  }

  test("SessionBootstrap.build returns structured missing-path failures") {
    withTempDir("session-bootstrap-missing-") { root =>
      val workDir = root / "Work"
      os.makeDir(workDir)

      val result = SessionBootstrap.build(
        sessionId = "bootstrap-missing",
        isaPath = root / "NoSuchIsabelle",
        logic = "HOL",
        workDir = workDir,
        sessionRoots = List(workDir)
      )

      assert(result.left.toOption.exists(_.isInstanceOf[MissingPath]))
    }
  }

  test("SessionBootstrap.build surfaces malformed ROOT as structured failure") {
    withTempDir("session-bootstrap-malformed-") { root =>
      val isaHome = root / "Isabelle2025"
      os.makeDir.all(isaHome / "src" / "HOL")

      val workDir = root / "Work"
      os.makeDir(workDir)
      os.write(
        workDir / "ROOT",
        """session Demo in "/absolute/path/not/rel" = HOL +""".stripMargin
      )

      val result = SessionBootstrap.build(
        sessionId = "bootstrap-bad-root",
        isaPath = isaHome,
        logic = "HOL",
        workDir = workDir,
        sessionRoots = List(isaHome / "src" / "HOL", workDir)
      )

      result match {
        case Left(WorkspaceBootstrapFailure(_: MalformedRoot)) =>
        case other                                             =>
          fail(s"Expected WorkspaceBootstrapFailure(MalformedRoot), got $other")
      }
    }
  }

  test("bootstrap errors map to INVALID_ARGUMENT for gRPC layer") {
    val status = IsabelleReplServiceImpl
      .bootstrapErrorToStatus(
        MissingPath("working directory", os.Path("/tmp/none"))
      )
      .getStatus

    assert(status.getCode == Status.INVALID_ARGUMENT.getCode)
  }
}
