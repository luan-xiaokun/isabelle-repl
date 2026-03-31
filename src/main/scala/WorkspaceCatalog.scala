package io.github.luanxiaokun.isabellerepl

import java.nio.file.Path
import scala.util.control.NonFatal

sealed trait WorkspaceCatalogError {
  def message: String
}

final case class UnsupportedImport(importText: String)
    extends WorkspaceCatalogError {
  override def message: String = s"Unsupported import: $importText"
}

final case class AmbiguousTheory(
    sessionName: String,
    theoryName: String,
    candidatePaths: List[String]
) extends WorkspaceCatalogError {
  override def message: String =
    s"Ambiguous theory '$theoryName' in session '$sessionName': ${candidatePaths.mkString(", ")}"
}

final case class MalformedRoot(
    rootFile: os.Path,
    reason: String
) extends WorkspaceCatalogError {
  override def message: String =
    s"Malformed ROOT file at $rootFile: $reason"
}

final case class WorkspaceCatalog(
    registeredSessionDirectories: List[(String, Path)],
    workDirSessionName: String,
    sessionFilesMap: Map[String, List[os.Path]]
) {
  def resolveImport(
      currentSessionName: String,
      importText: String
  ): Either[WorkspaceCatalogError, String] = {
    val normalized = importText.stripPrefix("\"").stripSuffix("\"")
    if (normalized.startsWith("~~/src/")) {
      if (!normalized.startsWith("~~/src/HOL/Library/"))
        return Left(UnsupportedImport(importText))
      return Right(
        s"HOL-Library.${normalized.stripPrefix("~~/src/HOL/Library/")}"
      )
    }

    val sessionFiles = sessionFilesMap.getOrElse(currentSessionName, Nil)
    val targetName = s"${normalized.split("/").last}.thy"
    val matches = sessionFiles.filter(_.last == targetName)
    matches.distinct match {
      case Nil =>
        Right(normalized)
      case _ :: Nil =>
        Right(s"$currentSessionName.${targetName.stripSuffix(".thy")}")
      case many =>
        Left(
          AmbiguousTheory(
            currentSessionName,
            targetName.stripSuffix(".thy"),
            many.map(_.toString).sorted
          )
        )
    }
  }

  def resolveImportOrThrow(
      currentSessionName: String,
      importText: String
  ): String =
    resolveImport(currentSessionName, importText) match {
      case Right(v) => v
      case Left(e)  => throw new IllegalArgumentException(e.message)
    }

  def resolveHeaderImports(
      currentSessionName: String,
      imports: Seq[String]
  ): Either[WorkspaceCatalogError, List[String]] =
    imports.foldLeft[Either[WorkspaceCatalogError, List[String]]](Right(Nil)) {
      case (Right(acc), importText) =>
        resolveImport(currentSessionName, importText).map(acc :+ _)
      case (left @ Left(_), _) =>
        left
    }
}

object WorkspaceCatalog {
  private def stripComments(content: String): String =
    content.replaceAll("""\(\*[\s\S]*?\*\)""", "")

  private def collectFromRootFile(
      baseDir: os.Path,
      content: String
  ): List[(String, Path)] = {
    val cleaned = stripComments(content)
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

  private def collectSessionRoot(
      root: os.Path
  ): Either[WorkspaceCatalogError, List[(String, Path)]] = {
    val buf = collection.mutable.ListBuffer[(String, Path)]()
    val topRootFile = root / "ROOT"
    if (os.exists(topRootFile)) {
      try buf ++= collectFromRootFile(root, os.read(topRootFile))
      catch {
        case NonFatal(e) =>
          return Left(MalformedRoot(topRootFile, e.getMessage))
      }
    }
    if (os.isDir(root)) {
      os.list(root).filter(os.isDir).foreach { subDir =>
        val subRootFile = subDir / "ROOT"
        if (os.exists(subRootFile)) {
          try buf ++= collectFromRootFile(subDir, os.read(subRootFile))
          catch {
            case NonFatal(e) =>
              return Left(MalformedRoot(subRootFile, e.getMessage))
          }
        }
      }
    }
    Right(buf.toList)
  }

  private def deriveWorkDirSessionName(
      logic: String,
      workDir: os.Path,
      sessionRoots: List[os.Path]
  ): String = {
    val rootFile = workDir / "ROOT"
    if (os.exists(rootFile)) {
      val cleaned = stripComments(os.read(rootFile))
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

  private def parseSessionFilesMap(
      workDir: os.Path,
      workDirSessionName: String
  ): Either[WorkspaceCatalogError, Map[String, List[os.Path]]] = {
    val rootFile = workDir / "ROOT"
    if (!os.exists(rootFile))
      return Right(
        Map(
          workDirSessionName -> os
            .list(workDir)
            .filter(p => os.isFile(p) && p.ext == "thy")
            .toList
        )
      )

    try {
      val projectPath = rootFile / os.up
      val cleaned = stripComments(os.read(rootFile))

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
        val dirBlockPat =
          """directories\s*\n([\s\S]*?)(?:theories|options|$)""".r
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
        entries
          .map(e => e.name -> collection.mutable.ListBuffer[os.Path]())
          .toMap
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

      Right(sessionFiles.view.mapValues(_.toList).toMap)
    } catch {
      case NonFatal(e) =>
        Left(MalformedRoot(rootFile, e.getMessage))
    }
  }

  def build(
      logic: String,
      workDir: os.Path,
      sessionRoots: List[os.Path]
  ): Either[WorkspaceCatalogError, WorkspaceCatalog] = {
    val registeredSessionDirectoriesEither =
      sessionRoots
        .foldLeft[Either[WorkspaceCatalogError, List[(String, Path)]]](
          Right(Nil)
        ) { case (accEither, root) =>
          for {
            acc <- accEither
            entries <- collectSessionRoot(root)
          } yield acc ++ entries
        }

    registeredSessionDirectoriesEither.flatMap { entries =>
      val registeredSessionDirectories = entries.distinct
      val workDirSessionName =
        deriveWorkDirSessionName(logic, workDir, sessionRoots)
      parseSessionFilesMap(workDir, workDirSessionName).map { sessionFilesMap =>
        WorkspaceCatalog(
          registeredSessionDirectories = registeredSessionDirectories,
          workDirSessionName = workDirSessionName,
          sessionFilesMap = sessionFilesMap
        )
      }
    }
  }
}
