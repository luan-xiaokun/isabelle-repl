package io.github.luanxiaokun.isabellerepl

import org.scalatest.funsuite.AnyFunSuite

class IndexParsingTest extends AnyFunSuite {

  private def withTempDir(prefix: String)(f: os.Path => Unit): Unit = {
    val dir = os.temp.dir(prefix = prefix)
    try f(dir)
    finally os.remove.all(dir)
  }

  test(
    "WorkspaceCatalog.build collects top-level and nested ROOT sessions once"
  ) {
    withTempDir("workspace-catalog-root-index-") { root =>
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

      val catalog = WorkspaceCatalog
        .build("HOL", root / "Nested", List(root))
        .fold(error => fail(error.message), identity)
      val dirs = catalog.registeredSessionDirectories.groupMap(_._1)(_._2)

      assert(catalog.workDirSessionName == "Nested")
      assert(dirs("Base").size == 1)
      assert(dirs("Nested").distinct.size == 1)
    }
  }

  test(
    "WorkspaceCatalog.build strips ROOT comments when deriving workdir session"
  ) {
    withTempDir("workspace-catalog-root-comments-") { workDir =>
      os.write(
        workDir / "ROOT",
        """(* session "Ignored" = HOL + *)
          |session "Visible" = HOL +
          |""".stripMargin
      )

      val catalog = WorkspaceCatalog
        .build("HOL", workDir, List(workDir))
        .fold(error => fail(error.message), identity)

      assert(catalog.workDirSessionName == "Visible")
      assert(catalog.registeredSessionDirectories.map(_._1) == List("Visible"))
    }
  }

  test(
    "WorkspaceCatalog.build falls back to directory name without ROOT file"
  ) {
    withTempDir("workspace-catalog-root-fallback-") { root =>
      os.makeDir(root / "Query_Optimization")

      val catalog = WorkspaceCatalog
        .build("HOL", root / "Query_Optimization", List(root))
        .fold(error => fail(error.message), identity)

      assert(catalog.workDirSessionName == "Query_Optimization")
    }
  }

  test("WorkspaceCatalog.build maps directories blocks to the owning session") {
    withTempDir("workspace-catalog-directories-") { workDir =>
      os.makeDir.all(workDir / "Subdir" / "Nested")
      os.write(
        workDir / "ROOT",
        """session Demo = HOL +
          |  directories
          |    Subdir
          |""".stripMargin
      )
      os.write(workDir / "Top.thy", "theory Top imports Main begin end")
      os.write(
        workDir / "Subdir" / "Inner.thy",
        "theory Inner imports Main begin end"
      )
      os.write(
        workDir / "Subdir" / "Nested" / "Deep.thy",
        "theory Deep imports Main begin end"
      )

      val catalog = WorkspaceCatalog
        .build("HOL", workDir, List(workDir))
        .fold(error => fail(error.message), identity)

      assert(catalog.resolveImport("Demo", "Top") == Right("Demo.Top"))
      assert(catalog.resolveImport("Demo", "Inner") == Right("Demo.Inner"))
      assert(catalog.resolveImport("Demo", "Deep") == Right("Demo.Deep"))
    }
  }

  test(
    "WorkspaceCatalog.resolveImport keeps qualified imports and rewrites HOL-Library"
  ) {
    val catalog = WorkspaceCatalog(
      registeredSessionDirectories = Nil,
      workDirSessionName = "Demo",
      sessionFilesMap = Map("Demo" -> Nil)
    )

    assert(
      catalog.resolveImport("Demo", "Other.Session") == Right("Other.Session")
    )
    assert(
      catalog.resolveImport("Demo", "~~/src/HOL/Library/FuncSet") ==
        Right("HOL-Library.FuncSet")
    )
    assert(
      catalog.resolveImport("Demo", "~~/src/HOL/Main") ==
        Left(UnsupportedImport("~~/src/HOL/Main"))
    )
  }

  test("WorkspaceCatalog.build falls back to direct .thy files without ROOT") {
    withTempDir("workspace-catalog-fallback-") { workDir =>
      os.write(workDir / "Local.thy", "theory Local imports Main begin end")
      os.write(workDir / "README.txt", "ignored")
      os.makeDir(workDir / "Nested")
      os.write(
        workDir / "Nested" / "Hidden.thy",
        "theory Hidden imports Main begin end"
      )

      val catalog = WorkspaceCatalog
        .build("HOL", workDir, List(workDir))
        .fold(error => fail(error.message), identity)
      val sessionName = catalog.workDirSessionName

      assert(
        catalog.resolveImport(sessionName, "Local") == Right(
          s"$sessionName.Local"
        )
      )
      assert(catalog.resolveImport(sessionName, "Hidden") == Right("Hidden"))
    }
  }

  test("WorkspaceCatalog.resolveImport returns structured ambiguity errors") {
    val thyA = os.Path("/tmp/A/Foo.thy")
    val thyB = os.Path("/tmp/B/Foo.thy")
    val catalog = WorkspaceCatalog(
      registeredSessionDirectories = Nil,
      workDirSessionName = "Demo",
      sessionFilesMap = Map("Demo" -> List(thyA, thyB))
    )

    val result = catalog.resolveImport("Demo", "Foo")
    result match {
      case Left(err: AmbiguousTheory) =>
        assert(err.sessionName == "Demo")
        assert(err.theoryName == "Foo")
      case other =>
        fail(s"Expected AmbiguousTheory, got: $other")
    }
  }
}
