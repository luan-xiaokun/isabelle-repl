from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Protocol

from isa_repl import IsaReplClient, StateResult, TheoryCommand


class RepairHook(Protocol):
    def __call__(
        self,
        theory_file: Path,
        cmd_text: str,
        cmd_kind: str,
        line: int,
        error_msg: str,
        proof_level: int,
        mode: str,
        proof_state_text: str,
        *args: Any,
        **kwargs: Any,
    ) -> str: ...


def execute_and_repair(
    theory_file: Path,
    client: IsaReplClient,
    session_id: str,
    repair_hook: RepairHook,
    timeout_ms: int = 30000,
    retry_limit: int = 3,
    try_sledgehammer: bool = False,
    repair_hook_kwargs: dict[str, Any] | None = None,
) -> None:
    if not repair_hook_kwargs:
        repair_hook_kwargs = {}

    fixes = {}

    # listing all commands automatically loads the theory
    commands = client.list_theory_commands(
        session_id=session_id, theory_path=str(theory_file), only_proof_stmts=False
    )

    # try to execute the header command (i.e., theory ... imports ... begin)
    init_state = client.init_after_header(
        session_id=session_id, theory_path=str(theory_file), include_text=True
    )
    # if init_state.error is not None, it must be a theory loading error
    if init_state.error:
        print(f"Error loading theory: {init_state.error.error_msg}")
        # TODO: we could call the repair hook here to try to fix it
        return

    # reaching this points means the imports are successfully loaded
    state = init_state.success
    assert state is not None, "Expected success state, but got None"

    # get the first command after the header
    header_idx = next(i for i, cmd in enumerate(commands) if cmd.kind == "theory")

    # maintain a cache from line number to state result (only success states)
    state_cache: dict[int, StateResult] = {commands[header_idx].line: state}

    for cmd in commands[header_idx + 1 :]:
        # TODO: clean up the cache if it grows too large
        # we need a dedicated data structure to manage the cache

        next_state = client.execute(
            source_state_id=state.state_id,
            tactic=cmd.text,
            timeout_ms=timeout_ms,
            include_text=True,
        )

        if next_state.is_success():
            state_cache[cmd.line] = next_state
            state = next_state
            continue

        # we can first try sledgehammer to fix the proof
        # TODO: this seems only useful for "by ..." terminal proof commands
        # how to handle non-terminal proof commands? e.g., "proof - ..." and "apply ..."?
        # if sledgehammer succeeds, we need to skip the remaining original proof commands
        if try_sledgehammer and state.mode == "PROOF":
            found, tactic, repair_state = client.run_sledgehammer(
                source_state_id=state.state_id,
                timeout_ms=timeout_ms,
                sledgehammer_timeout_ms=timeout_ms,
            )
            if found and tactic and repair_state.is_success():
                print(f"Sledgehammer found a tactic for line {cmd.line}: {tactic}")
                fixes[(cmd.line, cmd.text)] = tactic
                state_cache[cmd.line] = repair_state
                state = repair_state
                continue

        # if execution returns error or timeout, call the repair hook
        trial = 0
        while trial < retry_limit:
            trial += 1
            err_msg = "Timeout" if next_state.is_timeout() else next_state.error_msg
            repair_attempt = repair_hook(
                theory_file=theory_file,
                cmd_text=cmd.text,
                cmd_kind=cmd.kind,
                line=cmd.line,
                error_msg=err_msg,
                proof_level=state.proof_level,
                mode=state.mode,
                proof_state_text=state.proof_state_text,
                **repair_hook_kwargs,
            )
            repair_state = client.execute(
                source_state_id=state.state_id,
                tactic=repair_attempt,
                timeout_ms=timeout_ms,
                include_text=True,
            )
            if repair_state.is_success():
                # TODO: here we have similar issues: we need to skip the remaining
                # original proof commands that were supposed to work together with
                # the currently failing command to discharge the current proof goal
                # for example, commands A/B/C together discharge the current proof goal
                # and the error is at command B, and we repaired command B to B' (where
                # B' could consist multiple commands and discharge the proof goal
                # together with A), then we need to skip the next command C,
                # because C was part of the original proof that works together with B
                # after C, there could be other commands dedicated to other proof goals
                # so we cannot simply skip all the remaining commands
                # on the other hand, if we replaced B with B' that cannot discharge the
                # proof and still needs to work together with C to discharge the proof
                # goal, then we should not skip C.
                # I think the key points here are twofold:
                # (1) what's the aim of a single repair attempt? is it to fix the current
                #     command so no error is raised and it works together with the other
                #     commands to discharge the proof goal, or is it to give a complete
                #     proof for the current proof goal, even though there may be some
                #     remaining original proof commands that are now redundant and should
                #     be skipped?
                # (2) one way to check if we should skip the next command is to check the
                #     proof level before and after executing the repaired command. if the
                #     proof level decreases, then it means the repaired command itself can
                #     discharge the current proof goal, and the following original proof
                #     commands that open no new proof goal but are just mean to discharge
                #     a proof goal should be skipped (how hard is it to check this?) if
                #     the proof level does not decrease or even increases, then it means
                #     that either we are fixing something that is supposed to open a new
                #     proof (e.g., "proof - ...") or we are fixing something that still
                #     needs to work together with the following original proof commands.
                #     But I DONT KNOW FOR SURE IF THIS IS ALWAYS THE CASE.
                print(
                    f"Repair successful for line {cmd.line} after {trial} attempt(s). "
                    f"Original command: '{cmd.text}'. "
                    f"Repair attempt: '{repair_attempt}'"
                )
                fixes[(cmd.line, cmd.text)] = repair_attempt
                state_cache[cmd.line] = repair_state
                state = repair_state
                break
        else:
            print(
                f"Repair failed for line {cmd.line} after {trial} attempt(s). "
                f"Original command: '{cmd.text}'. "
            )

            # here we can do our best to continue executing the remaining commands to
            # find more errors and call the repair hook for them
            if state.mode == "PROOF":
                # in the proof mode, if we cannot fix the current error,
                # we can use "sorry" to fake the proof, skip the original proofs, and
                # continue to execute the remaining commands;
                # but how to determine how many original proof commands to skip?
                # this is a similar issue as described in the TODO comments above
                # do we have an algorithmic way to do this?
                pass
            else:
                # in a non-proof mode, we can really do nothing to fix the error
                # we have two options here:
                # (1) we can just give up executing and repairing the current theory
                #     and we safely exit; there will be no tricky issues, but we may
                #     miss some errors that could be repaired in the remaining commands
                # (2) we can skip the current command (e.g., a lemma statement, or a
                #     definition), and continue to gather more errors in the remaining
                #     commands; but this may cause some tricky issues, for example,
                #     some errors caused by the skipped command may not be repairable
                #     and it is hard to determine if the error we encounter later is
                #     caused by the skipped command or not
                # hold on a second; if we first try to isabelle build the theory to
                # find some errors that persist no matter how we repair the failing
                # non-proof command, then we be more certain about whether we should
                # skip or not. we can just skip or execute the commands until the
                # next error that we know for sure in advance by isabelle build.
                # this seems tricky, but it is probably better than both options
                # above. maybe it's worth a try
                print(
                    f"Encountered error in non-proof mode at line {cmd.line}, "
                    f"and repair attempts have been exhausted. "
                )
                print("Giving up...")
                break


def main():
    parser = argparse.ArgumentParser(description="Proof Repair client")
    parser.add_argument(
        "theory_file",
        type=Path,
        help="Path to the Isabelle theory file to load (e.g., /path/to/MyTheory.thy)",
    )
    parser.add_argument(
        "--host", type=str, default="localhost", help="Hostname of the REPL server"
    )
    parser.add_argument(
        "--port", type=int, default=50051, help="Port number for the REPL server"
    )
    parser.add_argument(
        "--isa-path",
        type=Path,
        help="Path to the Isabelle installation (e.g., /path/to/isabelle)",
    )
    parser.add_argument(
        "-l", "--logic", type=str, default="HOL", help="Logic to use (default: HOL)"
    )
    parser.add_argument(
        "-d",
        "--dir",
        type=Path,
        action="append",
        help="Additional session root directories (can be specified multiple times)",
    )
    parser.add_argument(
        "--working-dir",
        type=Path,
        default=None,
        help="Working directory for the Isabelle process (default: directory of the theory file)",
    )
    args = parser.parse_args()

    theory_file: Path = args.theory_file
    if not theory_file.is_file():
        print(f"Error: Theory file '{theory_file}' does not exist")
        return 1
    theory_file = theory_file.expanduser().resolve()

    isa_path = args.isa_path or os.getenv("ISA_PATH")
    if not isa_path:
        print(
            "Error: Isabelle path must be specified via --isa-path or ISA_PATH environment variable"
        )
        return 1
    isa_path = str(isa_path)

    session_roots = None
    if args.dir:
        session_roots = [str(d.expanduser().resolve()) for d in args.dir]

    with IsaReplClient(host=args.host, port=args.port) as client:
        print(f"Isabelle path: {isa_path}")
        print(f"Creating session with logic {args.logic}...")
        session_id = client.create_session(
            isa_path=isa_path,
            logic=args.logic,
            working_directory=args.working_dir or str(theory_file.parent),
            session_roots=session_roots,
        )

        print(f"Loading theory {theory_file}...")

        execute_and_repair(
            theory_file, client, session_id, repair_hook=lambda **kwargs: "by simp"
        )

        client.destroy_session(session_id=session_id)


if __name__ == "__main__":
    main()
