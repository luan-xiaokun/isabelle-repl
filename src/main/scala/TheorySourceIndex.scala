package isa.repl

final case class TheorySourceIndex(
    sessionFilesMap: Map[String, List[os.Path]]
) {

  def resolveImport(currentSessionName: String, name: String): String = {
    val sanitisedName = name.stripPrefix("\"").stripSuffix("\"")
    if (sanitisedName.startsWith("~~/src/")) {
      if (!sanitisedName.startsWith("~~/src/HOL/Library/"))
        throw new Exception(s"Unsupported import $name")
      return s"HOL-Library.${sanitisedName.stripPrefix("~~/src/HOL/Library/")}"
    }

    val thyName = sanitisedName.split("/").last
    val sessionFiles = sessionFilesMap.getOrElse(currentSessionName, Nil)
    if (sessionFiles.exists(_.last == s"$thyName.thy"))
      s"$currentSessionName.$thyName"
    else sanitisedName
  }
}

object TheorySourceIndex {

  private def parseWorkDirRootFile(rootFile: os.Path): Map[String, List[os.Path]] = {
    val projectPath = rootFile / os.up
    val cleaned = os.read(rootFile).replaceAll("""\(\*[\s\S]*?\*\)""", "")

    val sessionPat =
      """session\s+([\w_"+-]+)\s*(?:\(.*?\)\s*)?(?:in\s*("?[^"=\n]+"?)\s*)?=.*?""".r
    case class SessionEntry(name: String, mainDir: os.Path, startIdx: Int)
    val entries = sessionPat
      .findAllMatchIn(cleaned)
      .map { m =>
        val name = m.group(1).stripPrefix("\"").stripSuffix("\"")
        val dirStr = Option(m.group(2))
          .map(_.trim.stripPrefix("\"").stripSuffix("\""))
          .getOrElse("")
        val mainDir = projectPath / os.RelPath(dirStr)
        SessionEntry(name, mainDir, m.start)
      }
      .toList

    val dirToSession = collection.mutable.Map[os.Path, String]()
    val offsets = entries.map(_.startIdx) :+ cleaned.length
    entries.zip(offsets.tail).foreach { case (entry, nextOffset) =>
      dirToSession(entry.mainDir) = entry.name
      val block = cleaned.slice(entry.startIdx, nextOffset)
      val dirBlockPat = """directories\s*\n([\s\S]*?)(?:theories|options|$)""".r
      dirBlockPat.findFirstMatchIn(block).foreach { m =>
        m.group(1).trim.split("\\s+").filter(_.nonEmpty).foreach { rel =>
          val subDir = entry.mainDir.toNIO
            .resolve(rel.stripPrefix("\"").stripSuffix("\""))
            .normalize()
          dirToSession(os.Path(subDir)) = entry.name
        }
      }
    }

    def collectThyFiles(dir: os.Path): List[os.Path] =
      if (!os.isDir(dir)) Nil
      else
        os.list(dir).toList.flatMap { p =>
          if (os.isFile(p) && p.ext == "thy") List(p)
          else if (os.isDir(p)) collectThyFiles(p)
          else Nil
        }

    val sessionFiles =
      entries.map(e => e.name -> collection.mutable.ListBuffer[os.Path]()).toMap
    collectThyFiles(projectPath).foreach { thyFile =>
      var dir = thyFile.toNIO.getParent
      var found = false
      while (dir != null && !found) {
        dirToSession.get(os.Path(dir)) match {
          case Some(sessionName) if sessionFiles.contains(sessionName) =>
            sessionFiles(sessionName) += thyFile
            found = true
          case _ =>
            dir = dir.getParent
        }
      }
    }

    sessionFiles.view.mapValues(_.toList).toMap
  }

  def build(
      workDir: os.Path,
      workDirSessionName: String
  ): TheorySourceIndex = {
    val rootFile = workDir / "ROOT"
    val sessionFilesMap =
      if (os.exists(rootFile)) parseWorkDirRootFile(rootFile)
      else
        Map(
          workDirSessionName -> os
            .list(workDir)
            .filter(p => os.isFile(p) && p.ext == "thy")
            .toList
        )
    TheorySourceIndex(sessionFilesMap)
  }
}
