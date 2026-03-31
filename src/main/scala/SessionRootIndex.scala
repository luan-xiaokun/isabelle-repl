package isa.repl

import java.nio.file.Path

final case class SessionRootIndex(
    registeredSessionDirectories: List[(String, Path)],
    workDirSessionName: String
)

object SessionRootIndex {

  private def collectFromRootFile(
      baseDir: os.Path,
      content: String
  ): List[(String, Path)] = {
    val cleaned = content.replaceAll("""\(\*[\s\S]*?\*\)""", "")
    val withDirPat =
      """(?m)session\s+"?([^"(\s]+)"?[^=\n]*\bin\s+"?([^"\s=\n]+)"?""".r
    val noDirPat = """(?m)^session\s+"?([^"(\s]+)"?""".r

    val buf = collection.mutable.ListBuffer[(String, Path)]()
    val withDirNames = collection.mutable.Set[String]()
    for (m <- withDirPat.findAllMatchIn(cleaned)) {
      val name = m.group(1)
      val dirStr = m.group(2).stripPrefix("\"").stripSuffix("\"")
      val dir = baseDir / os.RelPath(dirStr)
      if (os.isDir(dir)) {
        buf += name -> dir.toNIO
        withDirNames += name
      }
    }
    for (m <- noDirPat.findAllMatchIn(cleaned)) {
      val name = m.group(1)
      if (!withDirNames.contains(name))
        buf += name -> baseDir.toNIO
    }
    buf.toList
  }

  private def collectSessionRoot(root: os.Path): List[(String, Path)] = {
    val buf = collection.mutable.ListBuffer[(String, Path)]()
    val topRootFile = root / "ROOT"
    if (os.exists(topRootFile))
      buf ++= collectFromRootFile(root, os.read(topRootFile))
    if (os.isDir(root)) {
      os.list(root).filter(os.isDir).foreach { subDir =>
        val subRootFile = subDir / "ROOT"
        if (os.exists(subRootFile))
          buf ++= collectFromRootFile(subDir, os.read(subRootFile))
      }
    }
    buf.toList
  }

  private def deriveWorkDirSessionName(
      logic: String,
      workDir: os.Path,
      sessionRoots: List[os.Path]
  ): String = {
    val rootFile = workDir / "ROOT"
    if (os.exists(rootFile)) {
      val cleaned = os.read(rootFile).replaceAll("""\(\*[\s\S]*?\*\)""", "")
      val pat = """(?m)^session\s+"?([^"(\s]+)"?""".r
      pat.findFirstMatchIn(cleaned).map(_.group(1)).getOrElse(logic)
    } else {
      sessionRoots
        .filter(os.isDir)
        .flatMap(root => os.list(root).filter(os.isDir))
        .find(_ == workDir)
        .map(_.last)
        .getOrElse(logic)
    }
  }

  def build(
      logic: String,
      workDir: os.Path,
      sessionRoots: List[os.Path]
  ): SessionRootIndex = {
    val registeredSessionDirectories =
      sessionRoots.flatMap(collectSessionRoot).distinct
    val workDirSessionName = deriveWorkDirSessionName(logic, workDir, sessionRoots)
    SessionRootIndex(registeredSessionDirectories, workDirSessionName)
  }
}
