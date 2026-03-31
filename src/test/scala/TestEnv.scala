package isa.repl

object IntegrationTags {
  object LocalIntegration
      extends org.scalatest.Tag("isa.repl.tags.LocalIntegration")
  object AfpHeavyIntegration
      extends org.scalatest.Tag("isa.repl.tags.AfpHeavyIntegration")
}

final case class IntegrationEnv(
    isaPath: os.Path,
    holSrc: os.Path,
    afpThys: os.Path,
    completenessDir: os.Path,
    completenessThy: os.Path,
    topologyDir: os.Path
)

object TestEnv {
  private def envPath(name: String): Option[os.Path] =
    sys.env.get(name).filter(_.nonEmpty).map(v => os.Path(v, os.pwd))

  private def fallbackPath(v: String): os.Path = os.Path(v, os.pwd)

  def load(): Either[List[String], IntegrationEnv] = {
    val isaPath =
      envPath("ISABELLE_PATH").getOrElse(fallbackPath("/home/lxk/Isabelle2025"))
    val afpThys = envPath("AFP_PATH")
      .getOrElse(fallbackPath("/home/lxk/repositories/afp-2025/thys"))

    val holSrc = isaPath / "src" / "HOL"
    val completenessDir = afpThys / "Completeness"
    val completenessThy = completenessDir / "Completeness.thy"
    val topologyDir = afpThys / "Topology"

    val checks = List(
      ("ISABELLE_PATH", isaPath, os.isDir(isaPath)),
      ("HOL source", holSrc, os.isDir(holSrc)),
      ("AFP_PATH", afpThys, os.isDir(afpThys)),
      ("Completeness dir", completenessDir, os.isDir(completenessDir)),
      ("Completeness.thy", completenessThy, os.isFile(completenessThy)),
      ("Topology dir", topologyDir, os.isDir(topologyDir))
    )

    val missing = checks.collect { case (label, p, false) =>
      s"Missing $label: $p"
    }

    if (missing.nonEmpty) Left(missing)
    else
      Right(
        IntegrationEnv(
          isaPath = isaPath,
          holSrc = holSrc,
          afpThys = afpThys,
          completenessDir = completenessDir,
          completenessThy = completenessThy,
          topologyDir = topologyDir
        )
      )
  }
}
