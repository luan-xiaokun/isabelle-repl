package io.github.luanxiaokun.isabellerepl

import java.nio.file.{Path, Paths}

import de.unruh.isabelle.control.{Isabelle, OperationCollection}
import de.unruh.isabelle.mlvalue.MLValue.{compileFunction, compileFunction0}
import de.unruh.isabelle.mlvalue.Version
import de.unruh.isabelle.pure.{Theory, TheoryHeader, ToplevelState, Transition}
import de.unruh.isabelle.mlvalue.Implicits._
import de.unruh.isabelle.pure.Implicits._

import TheoryManager.Ops

// Proof-opening command kinds — commands that start a new proof obligation
object ProofCommands {
  val list: Set[String] = Set(
    "lemma",
    "theorem",
    "corollary",
    "proposition",
    "schematic_goal",
    "interpretation",
    "global_interpretation",
    "sublocale",
    "instance",
    "notepad",
    "function",
    "termination",
    "specification",
    "old_rep_datatype",
    "typedef",
    "functor",
    "quotient_type",
    "lift_definition",
    "quotient_definition",
    "bnf",
    "subclass"
  )
}

class TheoryManager(
    val sessionName: String,
    workspaceCatalog: WorkspaceCatalog
)(implicit isabelle: Isabelle) {

  def getThyTransitions(
      thy: Theory,
      thyText: String,
      removeComments: Boolean = false
  ): List[(Transition, String)] = {
    val transitions = Transition.parseOuterSyntax(thy, thyText)
    if (removeComments)
      transitions.filterNot { case (_, text) =>
        text.isEmpty || (text.startsWith("(*") && text.endsWith("*)"))
      }
    else transitions
  }

  def initToplevel(): ToplevelState = Ops.init_toplevel().force.retrieveNow

  def beginTheory(text: String, path: os.Path): Theory = {
    val header = TheoryHeader.read(text)
    val masterDir = Option(path.toNIO.getParent).getOrElse(Paths.get(""))
    val imports = workspaceCatalog
      .resolveHeaderImports(sessionName, header.imports)
      .fold(
        error => throw new IllegalArgumentException(error.message),
        identity
      )
    Ops
      .begin_theory(
        masterDir,
        header,
        imports.map(Theory.apply)
      )
      .force
      .retrieveNow
  }

  def applySledgehammer(
      toplevelState: ToplevelState,
      theory: Theory,
      sledgehammerTimeout: Int = 30
  ): (Boolean, List[List[Transition]], List[String]) = {
    val Sledgehammer: String = theory.importMLStructureNow("Sledgehammer")
    val Sledgehammer_Commands: String =
      theory.importMLStructureNow("Sledgehammer_Commands")
    val Sledgehammer_Prover: String =
      theory.importMLStructureNow("Sledgehammer_Prover")
    val provers: String =
      if (Version.from2022) "cvc5 vampire verit e spass z3 zipperposition"
      else "cvc4 vampire verit e spass z3 zipperposition"
    val outcome: String =
      if (Version.from2022)
        f"$Sledgehammer.short_string_of_sledgehammer_outcome (fst (snd result))"
      else "fst (snd result)"
    val apply_sledgehammer = compileFunction[ToplevelState, Theory, List[
      String
    ], List[String], (Boolean, (String, List[String]))](
      s"""fn (state, thy, adds, dels) =>
         |  let
         |    val ret: string list Synchronized.var = Synchronized.var "sledgehammer_output" [];
         |    fun get_refs_and_token_lists (name) = (Facts.named name, []);
         |    val adds_refs_and_token_lists = map get_refs_and_token_lists adds;
         |    val dels_refs_and_token_lists = map get_refs_and_token_lists dels;
         |    val override = {add=adds_refs_and_token_lists,del=dels_refs_and_token_lists,only=false};
         |    val params = $Sledgehammer_Commands.default_params thy
         |                 [("provers","$provers"),("timeout","${sledgehammerTimeout.toString}"),("verbose","true")];
         |    val p_state = Toplevel.proof_of state;
         |    fun hack ret string =
         |      let
         |        fun find_sendback [] = NONE
         |          | find_sendback (XML.Elem ((name, _), body) :: rest) =
         |              if name = "sendback" then SOME (XML.content_of body)
         |              else (case find_sendback body of
         |                SOME s => SOME s | NONE => find_sendback rest)
         |          | find_sendback (_ :: rest) = find_sendback rest;
         |      in
         |        case find_sendback (YXML.parse_body string) of
         |          SOME s_prf => Synchronized.change ret (fn prfs => s_prf :: prfs)
         |        | NONE => ()
         |      end;
         |    val result = $Sledgehammer.run_sledgehammer params $Sledgehammer_Prover.Normal (SOME (hack ret)) 1 override p_state;
         |  in
         |    (fst result, ($outcome, Synchronized.value ret))
         |  end""".stripMargin
    )
    val result = apply_sledgehammer(
      toplevelState,
      theory,
      List(),
      List()
    ).force.retrieveNow
    val tactics = result._2._2.map(
      _.stripPrefix("Try this: ").replaceAll(raw" \(\d+ ms\)", "")
    )
    val parseResults =
      tactics.map(tactic => Transition.parseOuterSyntax(theory, tactic))
    val transitions = parseResults.map(_.map(_._1))
    val commands = parseResults.map(_.map(_._2).mkString(" "))
    (result._1, transitions, commands)
  }
}

object TheoryManager extends OperationCollection {
  protected final class Ops(implicit isabelle: Isabelle) {
    val init_toplevel = compileFunction0[ToplevelState](
      if (Version.from2023) "fn () => Toplevel.make_state NONE"
      else "Toplevel.init_toplevel"
    )

    val begin_theory = compileFunction[Path, TheoryHeader, List[
      Theory
    ], Theory](
      "fn (path, header, parents) => Resources.begin_theory path header parents"
    )
  }

  override protected def newOps(implicit isabelle: Isabelle) = new Ops
}
