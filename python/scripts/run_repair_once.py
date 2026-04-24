from __future__ import annotations

import argparse
import os
from pathlib import Path
from uuid import uuid4

from isabelle_repair.hooks import StaticReviewHook
from isabelle_repair.model import (
    InterventionResponse,
    InterventionResponseKind,
    RunMode,
)
from isabelle_repair.policy import RuleBasedPolicyGate, load_policy_config
from isabelle_repair.repl import ReplBlockLocalizer, ReplDeterministicTaskEngine
from isabelle_repair.run import TheoryRepairRun
from isabelle_repl import IsabelleReplClient


def _ensure_localhost_proxy_bypass() -> None:
    current = os.environ.get("NO_PROXY", "")
    tokens = {item.strip() for item in current.split(",") if item.strip()}
    tokens.update({"localhost", "127.0.0.1", "::1"})
    merged = ",".join(sorted(tokens))
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one real single-theory repair run and persist records."
    )
    parser.add_argument("theory_file", type=Path)
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--isa-path", type=Path, required=True)
    parser.add_argument("--logic", type=str, default="HOL")
    parser.add_argument(
        "--working-dir",
        type=Path,
        default=None,
        help="Isabelle working directory; defaults to theory parent.",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        action="append",
        default=None,
        help="Additional Isabelle session root (repeatable).",
    )
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument(
        "--run-mode",
        type=str,
        choices=[RunMode.THEORY_WIDE.value, RunMode.TARGET_BOUNDARY.value],
        default=RunMode.THEORY_WIDE.value,
        help="Run termination mode: theory-wide (default) or target-boundary.",
    )
    parser.add_argument(
        "--target-max-tasks",
        type=int,
        default=None,
        help="In target-boundary mode, complete after this many accepted artifacts.",
    )
    parser.add_argument(
        "--candidate-tactic",
        type=str,
        default="by simp",
        help="Deterministic candidate tactic used by minimal task engine.",
    )
    parser.add_argument(
        "--disable-sledgehammer",
        action="store_true",
        help="Disable sledgehammer fallback in rule-first generator.",
    )
    parser.add_argument(
        "--records-path",
        type=Path,
        default=None,
        help="JSONL output path; default .artifacts/repair_runs/<run_id>.jsonl",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Optional additional JSONL log file (stdout always enabled).",
    )
    parser.add_argument(
        "--policy-config",
        type=Path,
        default=None,
        help="Optional TOML path overriding default policy config.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _ensure_localhost_proxy_bypass()

    theory_file = args.theory_file.expanduser().resolve()
    if not theory_file.is_file():
        raise FileNotFoundError(f"Theory file does not exist: {theory_file}")
    working_dir = (
        args.working_dir.expanduser().resolve()
        if args.working_dir
        else theory_file.parent
    )
    session_roots = (
        [str(path.expanduser().resolve()) for path in args.dir] if args.dir else None
    )
    run_id = f"run-{uuid4().hex}"
    records_path = args.records_path or (
        Path(".artifacts") / "repair_runs" / f"{run_id}.jsonl"
    )
    policy_config = load_policy_config(args.policy_config)

    with IsabelleReplClient(host=args.host, port=args.port) as client:
        session_id = client.create_session(
            isa_path=str(args.isa_path.expanduser().resolve()),
            logic=args.logic,
            working_directory=str(working_dir),
            session_roots=session_roots,
        )
        try:
            client.load_theory(session_id, str(theory_file))
            localizer = ReplBlockLocalizer.from_theory(
                client=client,
                session_id=session_id,
                theory_path=str(theory_file),
                default_candidate_tactic=args.candidate_tactic,
                allow_sledgehammer=not args.disable_sledgehammer,
                timeout_ms=args.timeout_ms,
            )
            run = TheoryRepairRun(
                theory_path=str(theory_file),
                theory_text=theory_file.read_text(encoding="utf-8"),
                localizer=localizer,
                engine=ReplDeterministicTaskEngine(
                    client=client,
                    timeout_ms=args.timeout_ms,
                ),
                policy=RuleBasedPolicyGate(config=policy_config),
                hook=StaticReviewHook(
                    response_factory=InterventionResponse(
                        kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                    )
                ),
            )
            final_state, records = run.execute(
                run_id=run_id,
                max_steps=args.max_steps,
                records_path=records_path,
                log_file=args.log_file,
                run_mode=RunMode(args.run_mode),
                target_max_tasks=args.target_max_tasks,
            )
            record_list = records.list_records()
            task_count = sum(1 for r in record_list if r.record_kind.value == "task")
            continuation_count = sum(
                1 for r in record_list if r.record_kind.value == "continuation"
            )
            print(f"run_id={run_id}")
            print(f"final_state={final_state.value}")
            print(f"task_records={task_count}")
            print(f"continuation_records={continuation_count}")
            print(f"records_file={records_path.resolve()}")
        finally:
            client.destroy_session(session_id=session_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
