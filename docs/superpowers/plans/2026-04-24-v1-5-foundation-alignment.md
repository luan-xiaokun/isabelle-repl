# v1.5 Foundation Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the proof-repair agent's active v1.5 documentation, working snapshot semantics, and localization contract model before expanding repair capability.

**Architecture:** This plan keeps the current module boundaries intact. Documentation is updated first so v1.5 is the active baseline, then `WorkingTheorySnapshot` is made the single source of truth for patchable working text, then fallback block selection is promoted from ad hoc metadata into explicit model fields consumed by the REPL localizer and deterministic task engine.

**Tech Stack:** Python 3.12, pytest, dataclasses, Isabelle REPL Python client, Markdown design docs.

---

## Scope

This plan covers the agreed Batch 1-3 only:

- Batch 1: documentation authority and implemented-subset traceability
- Batch 2: working snapshot and patch correctness
- Batch 3: structured localization fallback and block contract cleanup

This plan intentionally does not implement `TopLevelCommandBlock`, richer policy context, `ESCALATED` hardening, or engine search expansion. Those should be planned after this foundation lands.

## File Structure

- `docs/proof-repair-agent-prd.md`: mark v1.5 as the current implementation baseline and explain how v1 module PRDs relate to it.
- `docs/v1_5/README.md`: make the active-doc rule explicit.
- `docs/v1_5/architecture/repair-agent-traceability-matrix.md`: add implemented-subset rows for snapshot and localization fallback.
- `docs/modules/failure-classification-and-localization-prd.md`: add an "Implemented v1.5 Subset" section for the currently supported block kinds and contracts.
- `docs/modules/repair-task-engine-prd.md`: add an "Implemented v1.5 Subset" section distinguishing current deterministic candidate loop from future action-runtime design.
- `python/src/isabelle_repair/model/types.py`: introduce explicit fallback candidate types and add them to `LocalizedTask`.
- `python/src/isabelle_repair/localization/repl.py`: populate structured fallback candidates instead of relying only on `metadata["fallback_chain"]`.
- `python/src/isabelle_repair/repl/minimal.py`: consume structured fallback candidates.
- `python/src/isabelle_repair/run/working_snapshot.py`: make replacement application update `current_text` through the same replacement model used by patch export.
- `python/tests/repair/unit/test_working_snapshot.py`: pin snapshot text and patch consistency.
- `python/tests/repair/unit/test_engine_localization.py`: pin structured fallback behavior and metadata compatibility.
- `python/tests/shared/repair_fakes.py`: update fake task factory to support fallback candidates when needed.

---

### Task 1: Mark v1.5 As The Active Baseline In Docs

**Files:**
- Modify: `docs/proof-repair-agent-prd.md`
- Modify: `docs/v1_5/README.md`
- Modify: `docs/v1_5/architecture/repair-agent-traceability-matrix.md`

- [ ] **Step 1: Write a docs authority check**

Create `python/tests/repair/unit/test_docs_authority.py`:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_top_level_prd_declares_v1_5_current_baseline():
    text = (ROOT / "docs/proof-repair-agent-prd.md").read_text(encoding="utf-8")
    assert "Current implementation baseline: v1.5" in text
    assert "v1 module PRDs remain design context" in text


def test_v1_5_readme_declares_authoritative_runtime_baseline():
    text = (ROOT / "docs/v1_5/README.md").read_text(encoding="utf-8")
    assert "authoritative runtime baseline" in text
    assert "implemented subset" in text


def test_traceability_matrix_tracks_foundation_alignment():
    text = (
        ROOT / "docs/v1_5/architecture/repair-agent-traceability-matrix.md"
    ).read_text(encoding="utf-8")
    assert "Working snapshot text/patch consistency" in text
    assert "Structured localization fallback" in text
```

- [ ] **Step 2: Run the docs authority check and verify it fails**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_docs_authority.py -v
```

Expected: FAIL because the required phrases are not yet present.

- [ ] **Step 3: Update the top-level PRD status block**

In `docs/proof-repair-agent-prd.md`, replace the current status line:

```markdown
Status: System PRD, overview, and document index for tentative v1 design
```

with:

```markdown
Status: System PRD, overview, and document index

Current implementation baseline: v1.5.

The v1.5 documents under `docs/v1_5/` are the authoritative runtime baseline
for current implementation work. The v1 module PRDs remain design context for
module intent, terminology, and future expansion, but they may describe
capabilities beyond the currently implemented subset.
```

- [ ] **Step 4: Update the v1.5 README**

In `docs/v1_5/README.md`, add this section after the opening paragraph:

```markdown
## Authority

This folder is the authoritative runtime baseline for current proof-repair
implementation work.

The module PRDs in `docs/modules/` remain active design context, but current
implementation planning should distinguish the implemented subset from future
design intent. When runtime behavior and older v1 text disagree, prefer the
v1.5 PRD, contract, acceptance-gate, and traceability documents.
```

- [ ] **Step 5: Update the v1.5 traceability matrix**

In `docs/v1_5/architecture/repair-agent-traceability-matrix.md`, add these rows under `## PRD Requirement Mapping`:

```markdown
| Working snapshot text/patch consistency | `run/working_snapshot`, `run/theory_run` | `test_working_snapshot.py`, `test_single_theory_flow.py` |
| Structured localization fallback | `model/types`, `localization/repl`, `repl/minimal` | `test_engine_localization.py` |
```

- [ ] **Step 6: Run the docs authority check and verify it passes**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_docs_authority.py -v
```

Expected: PASS.

- [ ] **Step 7: Run the repair unit suite**

Run:

```bash
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add docs/proof-repair-agent-prd.md docs/v1_5/README.md docs/v1_5/architecture/repair-agent-traceability-matrix.md python/tests/repair/unit/test_docs_authority.py
git commit -m "docs: mark proof repair v1.5 as active baseline"
```

---

### Task 2: Document The Implemented v1.5 Subset

**Files:**
- Modify: `docs/modules/failure-classification-and-localization-prd.md`
- Modify: `docs/modules/repair-task-engine-prd.md`
- Test: `python/tests/repair/unit/test_docs_authority.py`

- [ ] **Step 1: Extend the docs authority test**

Append these tests to `python/tests/repair/unit/test_docs_authority.py`:

```python
def test_localization_prd_declares_implemented_v1_5_subset():
    text = (
        ROOT / "docs/modules/failure-classification-and-localization-prd.md"
    ).read_text(encoding="utf-8")
    assert "## Implemented v1.5 Subset" in text
    assert "TerminalProofStepBlock" in text
    assert "WholeProofBodyBlock" in text
    assert "TheoremShellBlock" in text
    assert "TopLevelCommandBlock remains future work" in text


def test_repair_engine_prd_declares_implemented_v1_5_subset():
    text = (ROOT / "docs/modules/repair-task-engine-prd.md").read_text(
        encoding="utf-8"
    )
    assert "## Implemented v1.5 Subset" in text
    assert "deterministic inspect/propose/validate loop" in text
    assert "action-runtime design remains future work" in text
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_docs_authority.py -v
```

Expected: FAIL because the implemented-subset sections are missing.

- [ ] **Step 3: Add the localization implemented-subset section**

In `docs/modules/failure-classification-and-localization-prd.md`, add this section before `## Summary`:

```markdown
## Implemented v1.5 Subset

Current runtime support is intentionally narrower than the full block taxonomy
above.

Implemented first-class runtime block kinds:

- `TerminalProofStepBlock`
- `WholeProofBodyBlock`
- `TheoremShellBlock`

Implemented runtime contracts:

- `goal_closed`
- `subproof_closed`
- `theorem_closed`

The REPL-backed localizer currently discovers failures incrementally from the
working snapshot command cursor and selects a terminal proof-step block first.
It also returns a structured fallback chain that allows the task engine to try
larger proof-body and theorem-shell blocks under explicit contracts.

`TopLevelCommandBlock remains future work` for runtime validation. It remains
part of the design taxonomy and is the next high-risk block kind to productize.
Other block kinds in this document are design intent unless called out in the
v1.5 traceability matrix.
```

- [ ] **Step 4: Add the repair-engine implemented-subset section**

In `docs/modules/repair-task-engine-prd.md`, add this section before `## Testing Decisions`:

```markdown
## Implemented v1.5 Subset

The current runtime implements a deterministic inspect/propose/validate loop,
not the full future action-runtime design.

Implemented runtime behavior:

- one task-scoped inspection step represented by the localized task input
- ordered candidate proposal from the rule-first generator
- review-injected candidates through the same validation path as automatic
  candidates
- block-kind-aware validation adapters for the implemented block subset
- compact task trace summaries promoted into run records

The action-runtime design remains future work. In particular, the current
implementation does not yet include a first-class enabled-action model,
task-local observation store, controller legality mechanism, or granular action
record stream.
```

- [ ] **Step 5: Run the focused docs test and verify it passes**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_docs_authority.py -v
```

Expected: PASS.

- [ ] **Step 6: Run the repair acceptance gate**

Run:

```bash
cd python && uv run python scripts/check_repair_acceptance_gate.py
```

Expected: PASS with `Repair acceptance gate PASSED`.

- [ ] **Step 7: Commit**

```bash
git add docs/modules/failure-classification-and-localization-prd.md docs/modules/repair-task-engine-prd.md python/tests/repair/unit/test_docs_authority.py
git commit -m "docs: record implemented proof repair v1.5 subset"
```

---

### Task 3: Make Snapshot Current Text Match Patch Replacement Semantics

**Files:**
- Modify: `python/src/isabelle_repair/run/working_snapshot.py`
- Modify: `python/tests/repair/unit/test_working_snapshot.py`

- [ ] **Step 1: Add a failing snapshot consistency test**

Append this test to `python/tests/repair/unit/test_working_snapshot.py`:

```python
def test_snapshot_current_text_uses_same_replacements_as_patch_export():
    source = 'theory T imports Main begin\nlemma t: "True"\nby auto\n'
    snapshot = WorkingTheorySnapshot(theory_path="T.thy", original_text=source)

    snapshot.apply_artifact(
        ArtifactKind.REPAIR,
        "by simp",
        task_id="task-1",
        command_line=3,
        original_text="by auto",
    )

    assert snapshot.current_text == 'theory T imports Main begin\nlemma t: "True"\nby simp\n'
    assert "(* applied:" not in snapshot.current_text
    assert snapshot.export_json_patch()["entries"][0]["replacement_text"] == "by simp"
    assert "+by simp" in snapshot.export_unified_diff()
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_working_snapshot.py::test_snapshot_current_text_uses_same_replacements_as_patch_export -v
```

Expected: FAIL because `current_text` currently appends `(* applied: by simp *)`.

- [ ] **Step 3: Update `apply_artifact` to recompute current text from replacements**

In `python/src/isabelle_repair/run/working_snapshot.py`, replace `apply_artifact` with:

```python
    def apply_artifact(
        self,
        artifact_kind: ArtifactKind,
        artifact_text: str,
        *,
        task_id: str | None = None,
        command_line: int | None = None,
        original_text: str | None = None,
    ) -> None:
        self.applied_artifacts.append((artifact_kind, artifact_text))
        if command_line is not None:
            self.applied_replacements.append(
                {
                    "patch_entry_id": f"pe-{len(self.applied_replacements) + 1}",
                    "task_id": task_id,
                    "command_line": command_line,
                    "artifact_kind": artifact_kind.value,
                    "replacement_text": artifact_text,
                    "original_text": original_text,
                    "artifact_record_id": None,
                }
            )
            self.current_text = self._render_patched_text()
            return
        self.current_text = self._render_patched_text()
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_working_snapshot.py::test_snapshot_current_text_uses_same_replacements_as_patch_export -v
```

Expected: PASS.

- [ ] **Step 5: Run all snapshot tests**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_working_snapshot.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add python/src/isabelle_repair/run/working_snapshot.py python/tests/repair/unit/test_working_snapshot.py
git commit -m "fix: align working snapshot text with patch export"
```

---

### Task 4: Add Structured Fallback Candidate Model

**Files:**
- Modify: `python/src/isabelle_repair/model/types.py`
- Modify: `python/src/isabelle_repair/model/__init__.py`
- Modify: `python/src/isabelle_repair/__init__.py`
- Modify: `python/tests/shared/repair_fakes.py`
- Modify: `python/tests/repair/unit/test_engine_localization.py`

- [ ] **Step 1: Add a failing model-level fallback test**

Append this test to `python/tests/repair/unit/test_engine_localization.py`:

```python
def test_localized_task_exposes_structured_fallback_candidates():
    task = LocalizedTask(
        task_id="task-structured",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="by auto",
        fallback_candidates=[
            RepairBlockCandidate(
                block_kind=TERMINAL_PROOF_STEP_BLOCK,
                block_contract=BlockContract.GOAL_CLOSED,
                origin="primary",
            ),
            RepairBlockCandidate(
                block_kind=WHOLE_PROOF_BODY_BLOCK,
                block_contract=BlockContract.SUBPROOF_CLOSED,
                origin="fallback",
            ),
        ],
    )

    assert [candidate.block_kind for candidate in task.fallback_candidates] == [
        TERMINAL_PROOF_STEP_BLOCK,
        WHOLE_PROOF_BODY_BLOCK,
    ]
    assert task.fallback_candidates[0].block_contract == BlockContract.GOAL_CLOSED
```

Also update the import block in that file to include `RepairBlockCandidate`:

```python
from isabelle_repair.model import (
    BlockContract,
    FailureKind,
    LocalizedTask,
    RepairBlockCandidate,
    TaskOutcome,
    TaskSpec,
    ValidationStatus,
)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_localized_task_exposes_structured_fallback_candidates -v
```

Expected: FAIL with an import error or unexpected keyword argument for `RepairBlockCandidate`.

- [ ] **Step 3: Add the model type**

In `python/src/isabelle_repair/model/types.py`, insert this dataclass immediately before `LocalizedTask`:

```python
@dataclass(frozen=True)
class RepairBlockCandidate:
    block_kind: str
    block_contract: BlockContract
    origin: str = "primary"
    metadata: dict[str, Any] = field(default_factory=dict)
```

Then replace `LocalizedTask` with:

```python
@dataclass(frozen=True)
class LocalizedTask:
    task_id: str
    block_kind: str
    failure_kind: FailureKind
    block_text: str
    entry_checkpoint: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    fallback_candidates: list[RepairBlockCandidate] = field(default_factory=list)
```

- [ ] **Step 4: Export the model type from package init files**

In `python/src/isabelle_repair/model/__init__.py`, add `RepairBlockCandidate` to the imported names from `.types` and to `__all__`.

Use this import shape:

```python
from .types import (
    ArtifactKind,
    BlockContract,
    ContinuationKind,
    ContinuationSelection,
    FailureKind,
    HookTriggerSource,
    InterventionContext,
    InterventionResponse,
    InterventionResponseKind,
    LocalizedTask,
    PendingReview,
    PolicyContext,
    PolicyDecision,
    PolicyDecisionKind,
    PolicyDecisionScope,
    RepairBlockCandidate,
    RunMode,
    RunRecord,
    RunRecordKind,
    RunState,
    TaskOutcome,
    TaskResult,
    TaskSpec,
    ValidationResult,
    ValidationStatus,
)
```

Add this string to `__all__`:

```python
    "RepairBlockCandidate",
```

In `python/src/isabelle_repair/__init__.py`, make the same `RepairBlockCandidate` import and `__all__` addition.

- [ ] **Step 5: Update the test fake factory**

In `python/tests/shared/repair_fakes.py`, add `RepairBlockCandidate` to the import from `isabelle_repair.model`, then change `make_localized_task` to:

```python
def make_localized_task(
    task_id: str,
    *,
    block_kind: str = "TerminalProofStepBlock",
    failure_kind: FailureKind = FailureKind.PROOF_BODY_FAILURE,
    block_text: str = "by simp",
    fallback_candidates: list[RepairBlockCandidate] | None = None,
) -> LocalizedTask:
    return LocalizedTask(
        task_id=task_id,
        block_kind=block_kind,
        failure_kind=failure_kind,
        block_text=block_text,
        fallback_candidates=list(fallback_candidates or []),
    )
```

- [ ] **Step 6: Run the focused test and verify it passes**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_localized_task_exposes_structured_fallback_candidates -v
```

Expected: PASS.

- [ ] **Step 7: Run repair unit tests**

Run:

```bash
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add python/src/isabelle_repair/model/types.py python/src/isabelle_repair/model/__init__.py python/src/isabelle_repair/__init__.py python/tests/shared/repair_fakes.py python/tests/repair/unit/test_engine_localization.py
git commit -m "feat: add structured repair block fallback candidates"
```

---

### Task 5: Populate Structured Fallback Candidates In The REPL Localizer

**Files:**
- Modify: `python/src/isabelle_repair/localization/repl.py`
- Modify: `python/tests/repair/unit/test_engine_localization.py`

- [ ] **Step 1: Strengthen the localizer fallback test**

In `python/tests/repair/unit/test_engine_localization.py`, update `test_localizer_has_terminal_to_whole_to_theorem_fallback_chain` by adding these assertions after the existing `metadata["fallback_chain"]` assertion:

```python
    assert [candidate.block_kind for candidate in task.fallback_candidates] == [
        TERMINAL_PROOF_STEP_BLOCK,
        WHOLE_PROOF_BODY_BLOCK,
        THEOREM_SHELL_BLOCK,
    ]
    assert [candidate.block_contract for candidate in task.fallback_candidates] == [
        BlockContract.GOAL_CLOSED,
        BlockContract.SUBPROOF_CLOSED,
        BlockContract.THEOREM_CLOSED,
    ]
    assert task.fallback_candidates[0].origin == "primary"
    assert task.fallback_candidates[1].origin == "fallback"
```

- [ ] **Step 2: Run the strengthened test and verify it fails**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_localizer_has_terminal_to_whole_to_theorem_fallback_chain -v
```

Expected: FAIL because `fallback_candidates` is empty.

- [ ] **Step 3: Update localizer imports**

In `python/src/isabelle_repair/localization/repl.py`, change:

```python
from isabelle_repair.model import FailureKind, LocalizedTask
```

to:

```python
from isabelle_repair.model import (
    BlockContract,
    FailureKind,
    LocalizedTask,
    RepairBlockCandidate,
)
```

- [ ] **Step 4: Populate fallback candidates**

In `python/src/isabelle_repair/localization/repl.py`, add this helper method near `_classify_failure`:

```python
    @staticmethod
    def _default_fallback_candidates() -> list[RepairBlockCandidate]:
        return [
            RepairBlockCandidate(
                block_kind=TERMINAL_PROOF_STEP_BLOCK,
                block_contract=BlockContract.GOAL_CLOSED,
                origin="primary",
            ),
            RepairBlockCandidate(
                block_kind=WHOLE_PROOF_BODY_BLOCK,
                block_contract=BlockContract.SUBPROOF_CLOSED,
                origin="fallback",
            ),
            RepairBlockCandidate(
                block_kind=THEOREM_SHELL_BLOCK,
                block_contract=BlockContract.THEOREM_CLOSED,
                origin="fallback",
            ),
        ]
```

Then in the `LocalizedTask(...)` returned by `next_task`, add:

```python
                fallback_candidates=self._default_fallback_candidates(),
```

Keep the existing `metadata["fallback_chain"]` for compatibility during this migration.

- [ ] **Step 5: Run the strengthened test and verify it passes**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_localizer_has_terminal_to_whole_to_theorem_fallback_chain -v
```

Expected: PASS.

- [ ] **Step 6: Run all localization and engine unit tests**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add python/src/isabelle_repair/localization/repl.py python/tests/repair/unit/test_engine_localization.py
git commit -m "feat: populate structured localization fallback candidates"
```

---

### Task 6: Make The Deterministic Task Engine Consume Structured Fallbacks

**Files:**
- Modify: `python/src/isabelle_repair/repl/minimal.py`
- Modify: `python/tests/repair/unit/test_engine_localization.py`

- [ ] **Step 1: Add a failing test for structured fallback consumption**

Append this test to `python/tests/repair/unit/test_engine_localization.py`:

```python
def test_repl_task_engine_prefers_structured_fallback_candidates_over_metadata():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="SUCCESS", mode="PROOF", proof_level=1),
            _state(status="PROOF_COMPLETE", mode="THEORY", proof_level=0),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-structured-engine",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="by auto",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={
            "source_state_id": "s0",
            "fallback_chain": [THEOREM_SHELL_BLOCK],
        },
        fallback_candidates=[
            RepairBlockCandidate(
                block_kind=TERMINAL_PROOF_STEP_BLOCK,
                block_contract=BlockContract.GOAL_CLOSED,
                origin="primary",
            ),
            RepairBlockCandidate(
                block_kind=THEOREM_SHELL_BLOCK,
                block_contract=BlockContract.THEOREM_CLOSED,
                origin="fallback",
            ),
        ],
    )
    spec = TaskSpec(
        theory_run_id="run-structured-engine",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )

    result = engine.run(spec)

    assert result.outcome == TaskOutcome.ACCEPTED
    assert result.trace_summary.startswith(
        "TerminalProofStepBlock:failed | TheoremShellBlock:accepted"
    )
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_repl_task_engine_prefers_structured_fallback_candidates_over_metadata -v
```

Expected: FAIL because the engine still uses `metadata["fallback_chain"]`.

- [ ] **Step 3: Add fallback resolution helpers**

In `python/src/isabelle_repair/repl/minimal.py`, add `RepairBlockCandidate` to the model imports:

```python
    RepairBlockCandidate,
```

Then add this helper method to `ReplDeterministicTaskEngine` before `run`:

```python
    @staticmethod
    def _fallback_candidates(task_spec: TaskSpec) -> list[RepairBlockCandidate]:
        if task_spec.task.fallback_candidates:
            return list(task_spec.task.fallback_candidates)
        fallback_chain = list(task_spec.task.metadata.get("fallback_chain", []))
        if not fallback_chain:
            fallback_chain = [task_spec.task.block_kind]
        candidates: list[RepairBlockCandidate] = []
        for index, block_kind in enumerate(fallback_chain):
            contract = contract_for_block_kind(block_kind)
            if contract is None:
                continue
            candidates.append(
                RepairBlockCandidate(
                    block_kind=block_kind,
                    block_contract=contract,
                    origin="primary" if index == 0 else "fallback",
                )
            )
        return candidates
```

- [ ] **Step 4: Update `run` to use structured candidates**

In `ReplDeterministicTaskEngine.run`, replace:

```python
        fallback_chain = list(task_spec.task.metadata.get("fallback_chain", []))
        if not fallback_chain:
            fallback_chain = [task_spec.task.block_kind]
```

with:

```python
        fallback_candidates = self._fallback_candidates(task_spec)
```

Replace:

```python
        for index, block_kind in enumerate(fallback_chain):
            contract = contract_for_block_kind(block_kind)
            if contract is None:
                trace_parts.append(f"{block_kind}:unsupported_contract")
                continue
```

with:

```python
        for index, candidate in enumerate(fallback_candidates):
            block_kind = candidate.block_kind
            contract = candidate.block_contract
```

Replace the inconclusive validation details:

```python
                        "fallback_chain": fallback_chain,
```

with:

```python
                        "fallback_chain": [
                            candidate.block_kind for candidate in fallback_candidates
                        ],
```

- [ ] **Step 5: Run the focused test and verify it passes**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_repl_task_engine_prefers_structured_fallback_candidates_over_metadata -v
```

Expected: PASS.

- [ ] **Step 6: Run all repair unit tests**

Run:

```bash
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add python/src/isabelle_repair/repl/minimal.py python/tests/repair/unit/test_engine_localization.py
git commit -m "refactor: consume structured repair block fallbacks"
```

---

### Task 7: Refresh Records And Acceptance Evidence

**Files:**
- Modify: `docs/v1_5/architecture/repair-agent-traceability-matrix.md`
- Test: `python/tests/repair/unit/test_docs_authority.py`

- [ ] **Step 1: Extend traceability evidence test**

Append this test to `python/tests/repair/unit/test_docs_authority.py`:

```python
def test_traceability_matrix_names_new_foundation_evidence_tests():
    text = (
        ROOT / "docs/v1_5/architecture/repair-agent-traceability-matrix.md"
    ).read_text(encoding="utf-8")
    assert "test_snapshot_current_text_uses_same_replacements_as_patch_export" in text
    assert "test_repl_task_engine_prefers_structured_fallback_candidates_over_metadata" in text
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_docs_authority.py::test_traceability_matrix_names_new_foundation_evidence_tests -v
```

Expected: FAIL because the specific test names are not yet in the traceability matrix.

- [ ] **Step 3: Update the traceability matrix known evidence**

In `docs/v1_5/architecture/repair-agent-traceability-matrix.md`, add this subsection after `## PRD Requirement Mapping`:

```markdown
## Foundation Alignment Evidence

| Foundation concern | Evidence test |
| --- | --- |
| Working snapshot text/patch consistency | `test_snapshot_current_text_uses_same_replacements_as_patch_export` |
| Structured fallback consumed before legacy metadata | `test_repl_task_engine_prefers_structured_fallback_candidates_over_metadata` |
```

- [ ] **Step 4: Run docs authority tests**

Run:

```bash
cd python && uv run pytest tests/repair/unit/test_docs_authority.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the acceptance gate**

Run:

```bash
cd python && uv run python scripts/check_repair_acceptance_gate.py
```

Expected: PASS with `Repair acceptance gate PASSED`.

- [ ] **Step 6: Run all repair unit tests**

Run:

```bash
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add docs/v1_5/architecture/repair-agent-traceability-matrix.md python/tests/repair/unit/test_docs_authority.py
git commit -m "docs: refresh proof repair foundation traceability"
```

---

## Final Verification

- [ ] **Step 1: Run repair unit tests**

```bash
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

- [ ] **Step 2: Run repair acceptance gate**

```bash
cd python && uv run python scripts/check_repair_acceptance_gate.py
```

Expected: PASS with `Repair acceptance gate PASSED`.

- [ ] **Step 3: Check changed files**

```bash
git status --short
```

Expected: only intentional changes from this plan are present, or a clean tree if all task commits were made.

## Self-Review Notes

- Spec coverage: Batch 1 maps to Tasks 1, 2, and 7. Batch 2 maps to Task 3. Batch 3 maps to Tasks 4, 5, and 6.
- Placeholder scan: no plan step uses unresolved-marker language.
- Type consistency: `RepairBlockCandidate` is introduced in `model/types.py`, exported from both init files, populated by `ReplBlockLocalizer`, and consumed by `ReplDeterministicTaskEngine`.
