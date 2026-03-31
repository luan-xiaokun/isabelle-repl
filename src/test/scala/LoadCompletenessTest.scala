package isa.repl

import org.scalatest.funsuite.AnyFunSuite

import isa.repl.{ExecStatus, IntegrationTags}

/** Regression tests for AFP-backed sessions and pure ROOT/import indexes.
  *
  * Run with:
  *   sbt "testOnly isa.repl.LoadCompletenessTest"
  */
class LoadCompletenessTest extends AnyFunSuite {

  private val envEither = TestEnv.load()
  private val SESSION_LOGIC = "HOL"
  private val missingEnvReason = envEither.left.toOption.map(_.mkString("; ")).getOrElse("")

  private def requireEnv(): IntegrationEnv = {
    assume(
      envEither.isRight,
      s"Skipping AFP integration test; prerequisites missing: $missingEnvReason"
    )
    envEither.toOption.get
  }

  private def newSession(sessionId: String, workDir: os.Path): IsabelleSession = {
    val env = requireEnv()
    val sessionRoots = List(env.holSrc, env.afpThys)
    val sessionRootIndex = SessionRootIndex.build(SESSION_LOGIC, workDir, sessionRoots)
    val theorySourceIndex =
      TheorySourceIndex.build(workDir, sessionRootIndex.workDirSessionName)
    new IsabelleSession(
      sessionId = sessionId,
      isaPath = env.isaPath,
      logic = SESSION_LOGIC,
      workDir = workDir,
      sessionRoots = sessionRoots,
      registeredSessionDirectories = sessionRootIndex.registeredSessionDirectories,
      workDirSessionName = sessionRootIndex.workDirSessionName,
      theorySourceIndex = theorySourceIndex
    )
  }

  test(
    "SessionRootIndex finds AFP and Isabelle layout variants",
    IntegrationTags.AfpHeavyIntegration
  ) {
    val env = requireEnv()
    val sessionRoots = List(env.holSrc, env.afpThys)
    val index = SessionRootIndex.build(SESSION_LOGIC, env.completenessDir, sessionRoots)
    val dirs = index.registeredSessionDirectories.toMap

    assert(index.workDirSessionName == "Completeness")
    assert(dirs.contains("Completeness"))
    assert(dirs.contains("Lazy-Lists-II"))
    assert(dirs.contains("HOL-Library"))
  }

  test(
    "TheorySourceIndex resolves local, qualified, and HOL-Library imports",
    IntegrationTags.AfpHeavyIntegration
  ) {
    val env = requireEnv()
    val completenessIndex = TheorySourceIndex.build(env.completenessDir, "Completeness")
    assert(
      completenessIndex.resolveImport("Completeness", "Tree") ==
        "Completeness.Tree"
    )
    assert(
      completenessIndex.resolveImport(
        "Completeness",
        "~~/src/HOL/Library/FuncSet"
      ) == "HOL-Library.FuncSet"
    )

    val topologyIndex = TheorySourceIndex.build(env.topologyDir, "Topology")
    assert(
      topologyIndex.resolveImport("Topology", "Lazy-Lists-II.LList2") ==
        "Lazy-Lists-II.LList2"
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
      val cmds = session.listTheoryCommands(env.completenessThy, onlyProofStmts = true)
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
        case ComputedInitFailure(failedLine, errorMsg, _) =>
          fail(s"computeInitState failed at line $failedLine: $errorMsg")
      }
    } finally {
      session.close()
    }
  }
}
