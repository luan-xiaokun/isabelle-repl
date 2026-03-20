package isa.repl

import org.scalatest.funsuite.AnyFunSuite

import de.unruh.isabelle.control.Isabelle
import de.unruh.isabelle.pure.Theory
import de.unruh.isabelle.mlvalue.Implicits._
import de.unruh.isabelle.pure.Implicits._
import isa.repl.{ExecStatus, InitStateResponse}

/** Diagnostic / regression test for loading AFP Completeness.thy via
  * IsabelleSession.
  *
  * Mirrors exactly what the Python AFP integration tests do: session_roots =
  * [src/HOL, afp-2025/thys] working_directory = afp-2025/thys/Completeness/
  * logic = HOL
  *
  * Run with: sbt "testOnly isa.repl.LoadCompletenessTest"
  */
class LoadCompletenessTest extends AnyFunSuite {

  val ISA_PATH = os.Path("/home/lxk/Isabelle2025")
  val HOL_SRC = ISA_PATH / "src" / "HOL"
  val AFP_THYS = os.Path("/home/lxk/repositories/afp-2025/thys")
  val COMP_DIR = AFP_THYS / "Completeness"
  val COMP_THY = COMP_DIR / "Completeness.thy"

  // Session roots matching conftest.py: [src/HOL, afp-2025/thys]
  // val SESSION_ROOTS = List(HOL_SRC, AFP_THYS)
  val SESSION_ROOTS = Nil

  // ── Test 1: IsabelleSession starts without error ─────────────────────────

  test("IsabelleSession creates successfully") {
    val session = new IsabelleSession(
      sessionId = "test-create",
      isaPath = ISA_PATH,
      logic = "HOL",
      workDir = COMP_DIR,
      sessionRoots = SESSION_ROOTS
    )
    try {
      println("[Test1] IsabelleSession created OK")
    } finally {
      session.close()
    }
  }

  // ── Test 2: loadTheory returns a positive transition count ────────────────

  test("loadTheory(Completeness.thy) returns positive count") {
    val session = new IsabelleSession(
      sessionId = "test-load",
      isaPath = ISA_PATH,
      logic = "HOL",
      workDir = COMP_DIR,
      sessionRoots = SESSION_ROOTS
    )
    try {
      val count = session.loadTheory(COMP_THY)
      println(s"[Test2] transition count = $count")
      assert(count > 0, s"Expected positive count, got $count")
    } finally {
      session.close()
    }
  }

  // ── Test 3: listTheoryCommands finds fansSubs at line 134 ─────────────────

  test("listTheoryCommands finds fansSubs at line 134") {
    val session = new IsabelleSession(
      sessionId = "test-list",
      isaPath = ISA_PATH,
      logic = "HOL",
      workDir = COMP_DIR,
      sessionRoots = SESSION_ROOTS
    )
    try {
      val cmds = session.listTheoryCommands(COMP_THY, onlyProofStmts = true)
      val fans = cmds.find { case (text, _, _) => text.contains("fansSubs") }
      assert(fans.isDefined, "fansSubs lemma not found")
      val (_, _, line) = fans.get
      println(s"[Test3] fansSubs at line $line")
      assert(line == 134, s"Expected line 134, got $line")
    } finally {
      session.close()
    }
  }

  // ── Test 4: initState + execute proves fansSubs ───────────────────────────

  test("execute 'by (simp add: fans_def finite_subs)' proves fansSubs") {
    val session = new IsabelleSession(
      sessionId = "test-exec",
      isaPath = ISA_PATH,
      logic = "HOL",
      workDir = COMP_DIR,
      sessionRoots = SESSION_ROOTS
    )
    try {
      session.loadTheory(COMP_THY)
      val initResp = session.initState(COMP_THY, Left(134), 60000)
      val initResult = initResp.result match {
        case InitStateResponse.Result.Success(sr) =>
          println(s"[Test4] initState: mode=${sr.mode}")
          sr
        case InitStateResponse.Result.Error(e) =>
          fail(s"initState failed at line ${e.failedLine}: ${e.errorMsg}")
        case InitStateResponse.Result.Empty =>
          fail("initState returned empty result")
      }

      val execResult = session.execute(
        initResult.stateId,
        "by (simp add: fans_def finite_subs)",
        30000
      )
      println(
        s"[Test4] execute: status=${execResult.status} level=${execResult.proofLevel}"
      )
      assert(
        execResult.status == ExecStatus.PROOF_COMPLETE,
        s"Expected PROOF_COMPLETE, got ${execResult.status}: ${execResult.errorMsg}"
      )
    } finally {
      session.close()
    }
  }
}
