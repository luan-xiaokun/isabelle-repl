package isa.repl

sealed trait ReplaySelectorError {
  def code: InitStateErrorCode
  def message: String
  def candidateLines: List[Int]
}

final case class ReplaySelectorNotFound(
    selector: String
) extends ReplaySelectorError {
  override val code: InitStateErrorCode = InitStateErrorCode.INIT_STATE_NOT_FOUND
  override val message: String =
    s"after_command selector matched no command: $selector"
  override val candidateLines: List[Int] = Nil
}

final case class ReplaySelectorAmbiguous(
    selector: String,
    candidateLines: List[Int]
) extends ReplaySelectorError {
  override val code: InitStateErrorCode = InitStateErrorCode.INIT_STATE_AMBIGUOUS
  override val message: String =
    s"after_command selector is ambiguous: $selector"
}

object ReplayPlanner {
  private def normalizeWhitespace(s: String): String =
    s.replaceAll("\\s+", " ").trim

  def resolveTargetLine(
      commands: List[(Int, String)],
      position: Either[Int, String]
  ): Either[ReplaySelectorError, Int] =
    position match {
      case Left(line) => Right(line)
      case Right(selector) =>
        val normalizedSelector = normalizeWhitespace(selector)
        val matches = commands.collect {
          case (line, cmd)
              if line > 0 && normalizeWhitespace(cmd) == normalizedSelector =>
            line
        }
        matches.distinct match {
          case Nil =>
            Left(ReplaySelectorNotFound(selector))
          case line :: Nil =>
            Right(line)
          case lines =>
            Left(ReplaySelectorAmbiguous(selector, lines.sorted))
        }
    }

  def transitionsBetweenLines(
      entries: List[(Int, (de.unruh.isabelle.pure.Transition, String))],
      startLineExclusive: Int,
      targetLineInclusive: Int
  ): List[(de.unruh.isabelle.pure.Transition, String)] =
    entries.collect {
      case (line, entry)
          if line > startLineExclusive && line <= targetLineInclusive =>
        entry
    }
}
