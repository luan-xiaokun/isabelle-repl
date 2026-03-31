package isa.repl

import org.scalatest.funsuite.AnyFunSuite

import isa.repl.{ExecStatus, IntegrationTags}

/** Regression tests for AFP-backed sessions and workspace catalog semantics.
  *
  * Run with: sbt "testOnly isa.repl.LoadCompletenessTest"
  */
class LoadCompletenessTest extends AnyFunSuite {

  private val envEither = TestEnv.load()
  private val SESSION_LOGIC = "HOL"
  private val missingEnvReason =
    envEither.left.toOption.map(_.mkString("; ")).getOrElse("")

  private def requireEnv(): IntegrationEnv = {
    assume(
      envEither.isRight,
      s"Skipping AFP integration test; prerequisites missing: $missingEnvReason"
    )
    envEither.toOption.get
  }

  private def newSession(
      sessionId: String,
      workDir: os.Path
  ): IsabelleSession = {
    val env = requireEnv()
    val sessionRoots = List(env.holSrc, env.afpThys)
    val workspaceCatalog = WorkspaceCatalog
      .build(SESSION_LOGIC, workDir, sessionRoots)
      .fold(error => fail(error.message), identity)

    new IsabelleSession(
      sessionId = sessionId,
      isaPath = env.isaPath,
      logic = SESSION_LOGIC,
      workDir = workDir,
      sessionRoots = sessionRoots,
      workspaceCatalog = workspaceCatalog
    )
  }

  test(
    "WorkspaceCatalog finds AFP and Isabelle layout variants",
    IntegrationTags.AfpHeavyIntegration
  ) {
    val env = requireEnv()
    val sessionRoots = List(env.holSrc, env.afpThys)
    val catalog = WorkspaceCatalog
      .build(SESSION_LOGIC, env.completenessDir, sessionRoots)
      .fold(error => fail(error.message), identity)
    val dirs = catalog.registeredSessionDirectories.toMap

    assert(catalog.workDirSessionName == "Completeness")
    assert(dirs.contains("Completeness"))
    assert(dirs.contains("Lazy-Lists-II"))
    assert(dirs.contains("HOL-Library"))
  }

  test(
    "WorkspaceCatalog resolves local, qualified, and HOL-Library imports",
    IntegrationTags.AfpHeavyIntegration
  ) {
    val env = requireEnv()
    val completenessCatalog = WorkspaceCatalog
      .build(SESSION_LOGIC, env.completenessDir, List(env.holSrc, env.afpThys))
      .fold(error => fail(error.message), identity)
    assert(
      completenessCatalog.resolveImport("Completeness", "Tree") ==
        Right("Completeness.Tree")
    )
    assert(
      completenessCatalog.resolveImport(
        "Completeness",
        "~~/src/HOL/Library/FuncSet"
      ) == Right("HOL-Library.FuncSet")
    )

    val topologyCatalog = WorkspaceCatalog
      .build(SESSION_LOGIC, env.topologyDir, List(env.holSrc, env.afpThys))
      .fold(error => fail(error.message), identity)
    assert(
      topologyCatalog.resolveImport("Topology", "Lazy-Lists-II.LList2") ==
        Right("Lazy-Lists-II.LList2")
    )
  }

  test(
    "loadTheory(Completeness.thy) returns positive count",
    IntegrationTags.AfpHeavyIntegration
  ) {
    val env = requireEnv()
    val session = newSession("test-load", env.completenessDir)
    try {
      val count = session.loadTheory(env.completenessThy)
      assert(count > 0, s"Expected positive count, got $count")
    } finally {
      session.close()
    }
  }

  test(
    "listTheoryCommands finds fansSubs at line 134",
    IntegrationTags.AfpHeavyIntegration
  ) {
    val env = requireEnv()
    val session = newSession("test-list", env.completenessDir)
    try {
      val cmds =
        session.listTheoryCommands(env.completenessThy, onlyProofStmts = true)
      val fans = cmds.find { case (text, _, _) => text.contains("fansSubs") }
      assert(fans.isDefined, "fansSubs lemma not found")
      val (_, _, line) = fans.get
      assert(line == 134, s"Expected line 134, got $line")
    } finally {
      session.close()
    }
  }

  test(
    "computeInitState + computeExecute proves fansSubs",
    IntegrationTags.AfpHeavyIntegration
  ) {
    val env = requireEnv()
    val session = newSession("test-exec", env.completenessDir)
    try {
      session.loadTheory(env.completenessThy)
      session.computeInitState(env.completenessThy, Left(134), 60000) match {
        case ComputedInitSuccess(state, _) =>
          session.storeStateLocal("source", state)
          val execResult = session.computeExecute(
            "source",
            "by (simp add: fans_def finite_subs)",
            30000
          )
          assert(
            execResult.status == ExecStatus.PROOF_COMPLETE,
            s"Expected PROOF_COMPLETE, got ${execResult.status}: ${execResult.errorMsg}"
          )
        case ComputedInitFailure(failedLine, errorMsg, _, _, _) =>
          fail(s"computeInitState failed at line $failedLine: $errorMsg")
      }
    } finally {
      session.close()
    }
  }
}
