from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPO_ROOT / "python"

REQUIRED_DOCS = [
    REPO_ROOT
    / "docs"
    / "v1_5"
    / "architecture"
    / "repair-agent-traceability-matrix.md",
    REPO_ROOT
    / "docs"
    / "v1_5"
    / "contracts"
    / "theory-repair-run-state-machine-contract.md",
    REPO_ROOT / "docs" / "v1_5" / "testing" / "repair-acceptance-gate.md",
    REPO_ROOT / "docs" / "v1_5" / "implementation" / "task-checklist-and-acceptance.md",
]

FORBIDDEN_RUNTIME_FILES = [
    PYTHON_ROOT / "src" / "isabelle_repair" / "engine" / "simple.py",
    PYTHON_ROOT / "src" / "isabelle_repair" / "localization" / "simple.py",
]

REQUIRED_DOC_TOKENS = {
    REQUIRED_DOCS[0]: [
        "Drawio Node Mapping",
        "PRD Requirement Mapping",
    ],
    REQUIRED_DOCS[1]: [
        "State Definitions",
        "Invariants",
        "Trigger Conditions",
        "terminal_reason",
    ],
    REQUIRED_DOCS[3]: [
        "Phase 0: Baseline and Guardrails",
        "Phase 1: Incremental Localizer + Snapshot",
    ],
}


def _check_required_docs() -> None:
    for path in REQUIRED_DOCS:
        if not path.is_file():
            raise SystemExit(f"Acceptance gate failed: missing required doc: {path}")
    for path, tokens in REQUIRED_DOC_TOKENS.items():
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                raise SystemExit(
                    f"Acceptance gate failed: missing token {token!r} in {path}"
                )
    for path in FORBIDDEN_RUNTIME_FILES:
        if path.exists():
            raise SystemExit(
                f"Acceptance gate failed: test-only helper still in runtime src: {path}"
            )


def _run_acceptance_tests() -> None:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        "acceptance_gate",
        "tests/repair",
    ]
    proc = subprocess.run(
        cmd,
        cwd=PYTHON_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    if "SKIPPED" in proc.stdout:
        raise SystemExit(
            "Acceptance gate failed: acceptance marker suite contains skipped tests."
        )


def main() -> int:
    _check_required_docs()
    _run_acceptance_tests()
    print("Repair acceptance gate PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
