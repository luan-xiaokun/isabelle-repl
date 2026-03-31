package isa.repl

import org.scalatest.funsuite.AnyFunSuite

import isa.repl.{ExecStatus, InitStateResponse}

/** Regression tests for AFP-backed sessions and pure ROOT/import indexes.
  *
  * Run with:
  *   sbt "testOnly isa.repl.LoadCompletenessTest"
  */
class LoadCompletenessTest extends AnyFunSuite {

  val ISA_PATH = os.Path("/home/lxk/Isabelle2025")
  val HOL_SRC = ISA_PATH / "src" / "HOL"
  val AFP_THYS = os.Path("/home/lxk/repositories/afp-2025/thys")
  val SESSION_ROOTS = List(HOL_SRC, AFP_THYS)

  val COMP_DIR = AFP_THYS / "Completeness"
  val COMP_THY = COMP_DIR / "Completeness.thy"

  val TOPOLOGY_DIR = AFP_THYS / "Topology"

  private def newSession(sessionId: String, workDir: os.Path): IsabelleSession = {
    val sessionRootIndex = SessionRootIndex.build("HOL", workDir, SESSION_ROOTS)
    val theorySourceIndex =
      TheorySourceIndex.build(workDir, sessionRootIndex.workDirSessionName)
    new IsabelleSession(
      sessionId = sessionId,
      isaPath = ISA_PATH,
      logic = "HOL",
      workDir = workDir,
      sessionRoots = SESSION_ROOTS,
      registeredSessionDirectories = sessionRootIndex.registeredSessionDirectories,
      workDirSessionName = sessionRootIndex.workDirSessionName,
      theorySourceIndex = theorySourceIndex
    )
  }

  test("SessionRootIndex finds AFP and Isabelle layout variants") {
    val index = SessionRootIndex.build("HOL", COMP_DIR, SESSION_ROOTS)
    val dirs = index.registeredSessionDirectories.toMap

    assert(index.workDirSessionName == "Completeness")
    assert(dirs.contains("Completeness"))
    assert(dirs.contains("Lazy-Lists-II"))
    assert(dirs.contains("HOL-Library"))
  }

  test("TheorySourceIndex resolves local, qualified, and HOL-Library imports") {
    val completenessIndex = TheorySourceIndex.build(COMP_DIR, "Completeness")
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

    val topologyIndex = TheorySourceIndex.build(TOPOLOGY_DIR, "Topology")
    assert(
      topologyIndex.resolveImport("Topology", "Lazy-Lists-II.LList2") ==
        "Lazy-Lists-II.LList2"
    )
  }

  test("loadTheory(Completeness.thy) returns positive count") {
    val session = newSession("test-load", COMP_DIR)
    try {
      val count = session.loadTheory(COMP_THY)
      assert(count > 0, s"Expected positive count, got $count")
    } finally {
      session.close()
    }
  }

  test("listTheoryCommands finds fansSubs at line 134") {
    val session = newSession("test-list", COMP_DIR)
    try {
      val cmds = session.listTheoryCommands(COMP_THY, onlyProofStmts = true)
      val fans = cmds.find { case (text, _, _) => text.contains("fansSubs") }
      assert(fans.isDefined, "fansSubs lemma not found")
      val (_, _, line) = fans.get
      assert(line == 134, s"Expected line 134, got $line")
    } finally {
      session.close()
    }
  }

  test("computeInitState + computeExecute proves fansSubs") {
    val session = newSession("test-exec", COMP_DIR)
    try {
      session.loadTheory(COMP_THY)
      session.computeInitState(COMP_THY, Left(134), 60000) match {
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
