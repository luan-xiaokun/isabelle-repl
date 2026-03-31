import scala.language.postfixOps

ThisBuild / version := "0.1.0"
ThisBuild / scalaVersion := "2.13.18"
ThisBuild / organization := "io.github.luan-xiaokun"

Compile / PB.targets := Seq(
  scalapb.gen(grpc = true) -> (Compile / sourceManaged).value / "scalapb"
)

lazy val root = (project in file("."))
  .settings(name := "isabelle-repl")

libraryDependencies ++= Seq(
  "de.unruh" %% "scala-isabelle" % "0.4.5",
  "com.lihaoyi" %% "os-lib" % "0.11.8",
  "com.thesamet.scalapb" %% "scalapb-runtime" % scalapb.compiler.Version.scalapbVersion % "protobuf",
  "com.thesamet.scalapb" %% "scalapb-runtime-grpc" % scalapb.compiler.Version.scalapbVersion,
  "io.grpc" % "grpc-netty-shaded" % scalapb.compiler.Version.grpcJavaVersion,
  "org.scalatest" %% "scalatest" % "3.2.19" % Test
)
