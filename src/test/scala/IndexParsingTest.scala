package isa.repl

import org.scalatest.funsuite.AnyFunSuite

class IndexParsingTest extends AnyFunSuite {

  private def withTempDir(prefix: String)(f: os.Path => Unit): Unit = {
    val dir = os.temp.dir(prefix = prefix)
    try f(dir)
    finally os.remove.all(dir)
  }

  test("SessionRootIndex.build collects top-level and nested ROOT sessions once") {
    withTempDir("session-root-index-") { root =>
      os.write(
        root / "ROOT",
        """session "Base" = HOL +
          |  options [document = false]
          |
          |(* ignored duplicate with comment *)
          |session "Nested" in "Nested" = HOL +
          |""".stripMargin
      )
      os.makeDir(root / "Nested")
      os.write(
        root / "Nested" / "ROOT",
        """session "Nested" = HOL +""".stripMargin
      )

      val index = SessionRootIndex.build("HOL", root / "Nested", List(root))
      val dirs = index.registeredSessionDirectories.groupMap(_._1)(_._2)

      assert(index.workDirSessionName == "Nested")
      assert(dirs("Base").size == 1)
      assert(dirs("Nested").distinct.size == 1)
    }
  }

  test("SessionRootIndex.build strips ROOT comments when deriving workdir session") {
    withTempDir("session-root-comments-") { workDir =>
      os.write(
        workDir / "ROOT",
        """(* session "Ignored" = HOL + *)
          |session "Visible" = HOL +
          |""".stripMargin
      )

      val index = SessionRootIndex.build("HOL", workDir, List(workDir))

      assert(index.workDirSessionName == "Visible")
      assert(index.registeredSessionDirectories.map(_._1) == List("Visible"))
    }
  }

  test("SessionRootIndex.build falls back to directory name without ROOT file") {
    withTempDir("session-root-fallback-") { root =>
      os.makeDir(root / "Query_Optimization")

      val index =
        SessionRootIndex.build("HOL", root / "Query_Optimization", List(root))

      assert(index.workDirSessionName == "Query_Optimization")
    }
  }

  test("TheorySourceIndex.build maps directories blocks to the owning session") {
    withTempDir("theory-source-directories-") { workDir =>
      os.makeDir.all(workDir / "Subdir" / "Nested")
      os.write(
        workDir / "ROOT",
        """session Demo = HOL +
          |  directories
          |    Subdir
          |""".stripMargin
      )
      os.write(workDir / "Top.thy", "theory Top imports Main begin end")
      os.write(workDir / "Subdir" / "Inner.thy", "theory Inner imports Main begin end")
      os.write(
        workDir / "Subdir" / "Nested" / "Deep.thy",
        "theory Deep imports Main begin end"
      )

      val index = TheorySourceIndex.build(workDir, "Demo")

      assert(index.resolveImport("Demo", "Top") == "Demo.Top")
      assert(index.resolveImport("Demo", "Inner") == "Demo.Inner")
      assert(index.resolveImport("Demo", "Deep") == "Demo.Deep")
    }
  }

  test("TheorySourceIndex.resolveImport keeps qualified imports and rewrites HOL-Library") {
    val index = TheorySourceIndex(Map("Demo" -> Nil))

    assert(index.resolveImport("Demo", "Other.Session") == "Other.Session")
    assert(
      index.resolveImport("Demo", "~~/src/HOL/Library/FuncSet") ==
        "HOL-Library.FuncSet"
    )
    assertThrows[Exception] {
      index.resolveImport("Demo", "~~/src/HOL/Main")
    }
  }

  test("TheorySourceIndex.build falls back to direct .thy files without ROOT") {
    withTempDir("theory-source-fallback-") { workDir =>
      os.write(workDir / "Local.thy", "theory Local imports Main begin end")
      os.write(workDir / "README.txt", "ignored")
      os.makeDir(workDir / "Nested")
      os.write(workDir / "Nested" / "Hidden.thy", "theory Hidden imports Main begin end")

      val index = TheorySourceIndex.build(workDir, "Scratch")

      assert(index.resolveImport("Scratch", "Local") == "Scratch.Local")
      assert(index.resolveImport("Scratch", "Hidden") == "Hidden")
    }
  }
}
