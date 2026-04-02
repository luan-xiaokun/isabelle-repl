from __future__ import annotations

# Experimental proof-repair demo built on top of the Python REPL client.
# This file intentionally stays outside the installable ``isabelle_repl``
# package. It demonstrates how a repair workflow can drive the low-level REPL
# tools, but it is not the future proof-repair agent API.
import argparse
import os
from pathlib import Path
from typing import Any, Protocol

from isabelle_repl import IsabelleReplClient, StateResult


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
    client: IsabelleReplClient,
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

    # Listing all commands automatically loads the theory.
    commands = client.list_theory_commands(
        session_id=session_id, theory_path=str(theory_file), only_proof_stmts=False
    )

    # Try to execute the header command (i.e. theory ... imports ... begin).
    init_state = client.init_after_header(
        session_id=session_id, theory_path=str(theory_file), include_text=True
    )
    # If init_state.error is not None, it must be a theory loading error.
    if init_state.error:
        print(f"Error loading theory: {init_state.error.error_msg}")
        # TODO: We could call the repair hook here to try to fix it.
        return

    # Reaching this point means the imports are successfully loaded.
    state = init_state.success
    assert state is not None, "Expected success state, but got None"

    # Get the first command after the header.
    header_idx = next(i for i, cmd in enumerate(commands) if cmd.kind == "theory")

    # Maintain a cache from line number to state result (only success states).
    state_cache: dict[int, StateResult] = {commands[header_idx].line: state}

    for cmd in commands[header_idx + 1 :]:
        # TODO: Clean up the cache if it grows too large.
        # We need a dedicated data structure to manage the cache.

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

        # We can first try sledgehammer to fix the proof.
        # TODO: This seems only useful for "by ..." terminal proof commands.
        # How to handle non-terminal proof commands?
        # e.g. "proof - ..." and "apply ..."?
        # If sledgehammer succeeds, we need to skip the remaining original proof
        # commands.
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

        # If execution returns error or timeout, call the repair hook.
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
                # TODO: Here we have similar issues: we need to skip the remaining
                # original proof commands that were supposed to work together with the
                # currently failing command to discharge the current proof goal.
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

            # Here we can do our best to continue executing the remaining
            # commands to find more errors and call the repair hook for them.
            if state.mode == "PROOF":
                # In proof mode, if we cannot fix the current error, we could use
                # "sorry" to fake the proof and keep going. The open design
                # question is how far to skip in the original script afterward.
                pass
            else:
                # Outside proof mode, skipping a broken command may invalidate many
                # later errors, so this demo stops instead of guessing.
                print(
                    f"Encountered error in non-proof mode at line {cmd.line}, "
                    f"and repair attempts have been exhausted. "
                )
                print("Giving up...")
                break


def main() -> int:
    parser = argparse.ArgumentParser(description="Experimental proof repair demo")
    parser.add_argument(
        "theory_file",
        type=Path,
        help="Path to the Isabelle theory file to load (e.g. /path/to/MyTheory.thy)",
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
        help="Path to the Isabelle installation (e.g. /path/to/isabelle)",
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
        help=(
            "Working directory for the Isabelle process "
            "(default: directory of the theory file)"
        ),
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
            "Error: Isabelle path must be specified via --isa-path "
            "or ISA_PATH environment variable"
        )
        return 1
    isa_path = str(isa_path)

    session_roots = None
    if args.dir:
        session_roots = [str(d.expanduser().resolve()) for d in args.dir]

    with IsabelleReplClient(host=args.host, port=args.port) as client:
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
