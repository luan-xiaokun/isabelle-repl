# v1.5 High-Risk And Engine Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productize the next proof-repair layer by adding minimal high-risk top-level command support, hardening escalation/review semantics, and making the deterministic repair engine budgeted and more observable.

**Architecture:** This plan builds on the v1.5 foundation alignment. `TopLevelCommandBlock` becomes an explicit validated block kind, policy gains enough context to gate fallback/continuation risk, `ESCALATED` stops being treated as an accepted repair artifact, and the deterministic engine records budgeted inspect/propose/validate behavior without introducing a full future action-runtime model.

**Tech Stack:** Python 3.12, pytest, dataclasses, Isabelle REPL Python client, Markdown design docs.

---

## Scope

This plan covers Batch 4-6 only:

- Batch 4: high-risk block support for `TopLevelCommandBlock`
- Batch 5: orchestrator semantics hardening for `ESCALATED`, review, and continuation policy
- Batch 6: deterministic engine budget and trace expansion

This plan intentionally does not implement multi-theory campaigns, LLM strategy memory, cross-process resume, or the full future action-runtime model described in the module PRD.

## File Structure

- `python/src/isabelle_repair/localization/contracts.py`: add `TOP_LEVEL_COMMAND_BLOCK` and map it to a new contract.
- `python/src/isabelle_repair/model/types.py`: extend `BlockContract`, `PolicyContext`, and `TaskResult` with minimal fields needed for high-risk gating and trace evidence.
- `python/src/isabelle_repair/engine/adapters.py`: add `TopLevelCommandAdapter`.
- `python/src/isabelle_repair/engine/controller.py`: enforce validation budget and emit action-count trace details.
- `python/src/isabelle_repair/engine/generator.py`: make top-level command auto-generation explicit and conservative.
- `python/src/isabelle_repair/repl/minimal.py`: preserve structured fallback behavior while enforcing budgets and richer trace summaries.
- `python/src/isabelle_repair/policy/config.py`: add rule IDs/config switches for fallback review and continuation gating.
- `python/src/isabelle_repair/policy/rules.py`: use the richer `PolicyContext`.
- `python/src/isabelle_repair/run/orchestrator.py`: treat `ESCALATED` as review/stop, not as an accepted artifact; record continuation-gating policy decisions.
- `python/tests/repair/unit/test_engine_localization.py`: add adapter/engine tests.
- `python/tests/repair/unit/test_policy_and_hook.py`: add policy context tests.
- `python/tests/repair/unit/test_orchestrator.py`: add escalation and continuation gating tests.
- `docs/v1_5/architecture/repair-agent-traceability-matrix.md`: add evidence rows for Batch 4-6.
- `docs/modules/failure-classification-and-localization-prd.md`: update implemented subset to include `TopLevelCommandBlock`.
- `docs/modules/repair-task-engine-prd.md`: update implemented subset to include budgeted deterministic trace.
- `docs/modules/policy-and-risk-gate-prd.md`: update implemented subset for fallback and continuation gating.

---

### Task 1: Add `TopLevelCommandBlock` Contract And Adapter

**Files:**
- Modify: `python/src/isabelle_repair/model/types.py`
- Modify: `python/src/isabelle_repair/localization/contracts.py`
- Modify: `python/src/isabelle_repair/engine/adapters.py`
- Modify: `python/tests/repair/unit/test_engine_localization.py`

- [ ] **Step 1: Write failing contract and adapter tests**

Append to `python/tests/repair/unit/test_engine_localization.py`:

```python
from isabelle_repair.localization import TOP_LEVEL_COMMAND_BLOCK


def test_top_level_command_contract_is_context_updated():
    from isabelle_repair.localization import contract_for_block_kind

    assert (
        contract_for_block_kind(TOP_LEVEL_COMMAND_BLOCK)
        == BlockContract.CONTEXT_UPDATED
    )


def test_top_level_command_adapter_accepts_theory_context_success():
    registry = ValidationAdapterRegistry.default()
    validation = registry.validate(
        ValidationContext(
            block_kind=TOP_LEVEL_COMMAND_BLOCK,
            block_contract=BlockContract.CONTEXT_UPDATED,
            entry_mode="THEORY",
            entry_proof_level=0,
            execution_result=_state(
                status="SUCCESS",
                mode="THEORY",
                proof_level=0,
            ),
        )
    )

    assert validation.status == ValidationStatus.PASSED


def test_top_level_command_adapter_rejects_proof_mode_leak():
    registry = ValidationAdapterRegistry.default()
    validation = registry.validate(
        ValidationContext(
            block_kind=TOP_LEVEL_COMMAND_BLOCK,
            block_contract=BlockContract.CONTEXT_UPDATED,
            entry_mode="THEORY",
            entry_proof_level=0,
            execution_result=_state(
                status="SUCCESS",
                mode="PROOF",
                proof_level=1,
            ),
        )
    )

    assert validation.status == ValidationStatus.FAILED_CONTRACT
    assert validation.reason == "theory_context_not_restored"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py -k "top_level_command" -v
```

Expected: FAIL because `TOP_LEVEL_COMMAND_BLOCK` and `BlockContract.CONTEXT_UPDATED` do not exist.

- [ ] **Step 3: Extend block contract vocabulary**

In `python/src/isabelle_repair/model/types.py`, update `BlockContract`:

```python
class BlockContract(StrEnum):
    GOAL_CLOSED = "goal_closed"
    SUBPROOF_CLOSED = "subproof_closed"
    THEOREM_CLOSED = "theorem_closed"
    CONTEXT_UPDATED = "context_updated"
```

- [ ] **Step 4: Add top-level command block constant and contract mapping**

In `python/src/isabelle_repair/localization/contracts.py`, add:

```python
TOP_LEVEL_COMMAND_BLOCK = "TopLevelCommandBlock"
```

Update `contract_for_block_kind`:

```python
    if block_kind == TOP_LEVEL_COMMAND_BLOCK:
        return BlockContract.CONTEXT_UPDATED
```

Update `python/src/isabelle_repair/localization/__init__.py` to export `TOP_LEVEL_COMMAND_BLOCK`.

- [ ] **Step 5: Add validation adapter**

In `python/src/isabelle_repair/engine/adapters.py`, import `TOP_LEVEL_COMMAND_BLOCK` and add:

```python
class TopLevelCommandAdapter:
    """Contract: context_updated."""

    def validate(self, context: ValidationContext) -> ValidationResult:
        result = context.execution_result
        context_restored = (
            result.is_success()
            and result.mode != "PROOF"
            and result.proof_level == 0
        )
        if context_restored:
            return ValidationResult(
                status=ValidationStatus.PASSED,
                details={"contract": context.block_contract.value},
            )
        return ValidationResult(
            status=ValidationStatus.FAILED_CONTRACT,
            reason="theory_context_not_restored",
            details={"contract": context.block_contract.value},
        )
```

Add it to `ValidationAdapterRegistry.default()`:

```python
TOP_LEVEL_COMMAND_BLOCK: TopLevelCommandAdapter(),
```

- [ ] **Step 6: Run focused tests**

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py -k "top_level_command" -v
```

Expected: PASS.

- [ ] **Step 7: Run repair unit tests**

```bash
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

---

### Task 2: Keep Top-Level Command Generation Conservative

**Files:**
- Modify: `python/src/isabelle_repair/engine/generator.py`
- Modify: `python/src/isabelle_repair/repl/minimal.py`
- Modify: `python/tests/repair/unit/test_engine_localization.py`

- [ ] **Step 1: Write failing tests for conservative generation**

Append to `python/tests/repair/unit/test_engine_localization.py`:

```python
def test_rule_generator_does_not_auto_rewrite_top_level_command():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[],
    )
    generator = RuleFirstGenerator(client=client)
    task = LocalizedTask(
        task_id="task-top-level",
        block_kind=TOP_LEVEL_COMMAND_BLOCK,
        failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
        block_text='definition x where "x = 0"',
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-top-level",
        task=task,
        block_contract=BlockContract.CONTEXT_UPDATED,
    )

    assert generator.generate_candidates(spec, allow_sledgehammer=False) == []


def test_repl_engine_can_validate_reviewed_top_level_replacement():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[_state(status="SUCCESS", mode="THEORY", proof_level=0)],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-review-top-level",
        block_kind=TOP_LEVEL_COMMAND_BLOCK,
        failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
        block_text='definition x where "x = 0"',
        entry_checkpoint={"mode": "THEORY", "proof_level": 0},
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-review-top-level",
        task=task,
        block_contract=BlockContract.CONTEXT_UPDATED,
    )

    validation = engine.validate_candidate(spec, 'definition x where "x = 1"')

    assert validation.status == ValidationStatus.PASSED
```

- [ ] **Step 2: Run focused tests and verify failures**

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py -k "top_level" -v
```

Expected: PASS after Task 1. The generator test protects against accidental autonomous top-level command rewrite rules.

- [ ] **Step 3: Make top-level generator behavior explicit**

In `python/src/isabelle_repair/engine/generator.py`, import `TOP_LEVEL_COMMAND_BLOCK` and add before sledgehammer fallback:

```python
        if block_kind == TOP_LEVEL_COMMAND_BLOCK:
            return []
```

This keeps autonomous rewriting disabled for high-risk top-level commands. Review-provided replacements still validate through `validate_candidate`.

- [ ] **Step 4: Run focused and unit tests**

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py -k "top_level" -v
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

---

### Task 3: Expand Policy Context For Fallback And Continuation Risk

**Files:**
- Modify: `python/src/isabelle_repair/model/types.py`
- Modify: `python/src/isabelle_repair/policy/config.py`
- Modify: `python/src/isabelle_repair/policy/rules.py`
- Modify: `python/tests/repair/unit/test_policy_and_hook.py`

- [ ] **Step 1: Write failing policy tests**

Append to `python/tests/repair/unit/test_policy_and_hook.py`:

```python
def test_policy_requires_review_for_fallback_artifact_acceptance():
    gate = RuleBasedPolicyGate()
    decision = gate.decide(
        PolicyContext(
            theory_run_id="run-1",
            task_id="task-fallback",
            failure_kind=FailureKind.PROOF_BODY_FAILURE,
            block_kind="TheoremShellBlock",
            artifact_kind=ArtifactKind.REPAIR,
            fallback_depth=2,
            fallback_origin="fallback",
        )
    )

    assert decision.kind == PolicyDecisionKind.REQUIRES_REVIEW
    assert "fallback_acceptance_requires_review" in decision.triggered_rule_ids


def test_policy_requires_review_for_rerun_continuation_after_fallback():
    gate = RuleBasedPolicyGate()
    decision = gate.decide(
        PolicyContext(
            theory_run_id="run-1",
            task_id="task-continuation",
            failure_kind=FailureKind.PROOF_BODY_FAILURE,
            block_kind="TheoremShellBlock",
            artifact_kind=ArtifactKind.REPAIR,
            reason_code="continuation_gating",
            fallback_depth=1,
            continuation_kind=ContinuationKind.RERUN_THEN_CONTINUE,
        )
    )

    assert decision.kind == PolicyDecisionKind.REQUIRES_REVIEW
    assert decision.scope == PolicyDecisionScope.CONTINUATION_GATING
```

Update imports to include `ContinuationKind` and `PolicyDecisionScope`.

- [ ] **Step 2: Run focused policy tests and verify failures**

```bash
cd python && uv run pytest tests/repair/unit/test_policy_and_hook.py -k "fallback or continuation" -v
```

Expected: FAIL because `PolicyContext` does not yet have the new fields/rules.

- [ ] **Step 3: Extend `PolicyContext`**

In `python/src/isabelle_repair/model/types.py`, update `PolicyContext`:

```python
@dataclass(frozen=True)
class PolicyContext:
    theory_run_id: str
    task_id: str
    failure_kind: FailureKind
    block_kind: str
    artifact_kind: ArtifactKind | None
    reason_code: str | None = None
    is_placeholder_request: bool = False
    fallback_depth: int = 0
    fallback_origin: str | None = None
    localization_confidence: str | None = None
    continuation_kind: ContinuationKind | None = None
```

- [ ] **Step 4: Add policy rule IDs**

In `python/src/isabelle_repair/policy/config.py`, update `PolicyRuleIds`:

```python
fallback_acceptance_requires_review: str = "fallback_acceptance_requires_review"
fallback_continuation_requires_review: str = "fallback_continuation_requires_review"
```

- [ ] **Step 5: Implement rules**

In `python/src/isabelle_repair/policy/rules.py`, before the default allow:

```python
        if (
            context.reason_code == "continuation_gating"
            and context.continuation_kind is not None
            and context.fallback_depth > 0
        ):
            return PolicyDecision(
                kind=PolicyDecisionKind.REQUIRES_REVIEW,
                scope=PolicyDecisionScope.CONTINUATION_GATING,
                triggered_rule_ids=[
                    self.config.rule_ids.fallback_continuation_requires_review
                ],
            )

        if context.fallback_depth > 0 and context.artifact_kind == ArtifactKind.REPAIR:
            return PolicyDecision(
                kind=PolicyDecisionKind.REQUIRES_REVIEW,
                scope=self.config.default_scope,
                triggered_rule_ids=[
                    self.config.rule_ids.fallback_acceptance_requires_review
                ],
            )
```

Add `PolicyDecisionScope` to imports.

- [ ] **Step 6: Run tests**

```bash
cd python && uv run pytest tests/repair/unit/test_policy_and_hook.py -v
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

---

### Task 4: Record Active Fallback Metadata In Engine Results

**Files:**
- Modify: `python/src/isabelle_repair/model/types.py`
- Modify: `python/src/isabelle_repair/repl/minimal.py`
- Modify: `python/tests/repair/unit/test_engine_localization.py`

- [ ] **Step 1: Write failing engine metadata test**

Append to `python/tests/repair/unit/test_engine_localization.py`:

```python
def test_repl_engine_records_selected_fallback_metadata():
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
        task_id="task-fallback-metadata",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={"source_state_id": "s0"},
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
        theory_run_id="run-fallback-metadata",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )

    result = engine.run(spec)

    assert result.outcome == TaskOutcome.ACCEPTED
    assert result.selected_block_kind == THEOREM_SHELL_BLOCK
    assert result.fallback_depth == 1
    assert result.fallback_origin == "fallback"
```

- [ ] **Step 2: Run focused test and verify failure**

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_repl_engine_records_selected_fallback_metadata -v
```

Expected: FAIL because `TaskResult` lacks selected fallback fields.

- [ ] **Step 3: Extend `TaskResult`**

In `python/src/isabelle_repair/model/types.py`, add fields to `TaskResult`:

```python
    selected_block_kind: str | None = None
    fallback_depth: int = 0
    fallback_origin: str | None = None
```

- [ ] **Step 4: Populate fields in REPL engine**

In `python/src/isabelle_repair/repl/minimal.py`, when returning accepted result:

```python
                    selected_block_kind=block_kind,
                    fallback_depth=index,
                    fallback_origin=candidate.origin,
```

When returning promoted review fallback:

```python
                selected_block_kind=None,
                fallback_depth=0,
                fallback_origin=None,
```

When returning failed result:

```python
            selected_block_kind=None,
            fallback_depth=0,
            fallback_origin=None,
```

- [ ] **Step 5: Preserve fields in fake engine**

In `python/tests/shared/repair_fakes.py`, update `RuleBasedTaskEngine.run` and `accepted_repair` to carry the new `TaskResult` fields. Use defaults for existing tests:

```python
selected_block_kind=configured.selected_block_kind,
fallback_depth=configured.fallback_depth,
fallback_origin=configured.fallback_origin,
```

and in `accepted_repair`:

```python
selected_block_kind: str | None = None,
fallback_depth: int = 0,
fallback_origin: str | None = None,
```

- [ ] **Step 6: Run tests**

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_repl_engine_records_selected_fallback_metadata -v
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

---

### Task 5: Wire Fallback Metadata Into Policy Decisions

**Files:**
- Modify: `python/src/isabelle_repair/run/orchestrator.py`
- Modify: `python/tests/repair/unit/test_orchestrator.py`

- [ ] **Step 1: Write failing orchestrator policy test**

Append to `python/tests/repair/unit/test_orchestrator.py`:

```python
def test_orchestrator_sends_fallback_metadata_to_policy():
    task = make_localized_task("task-fallback-policy")
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-fallback-policy": RuleBasedTaskEngine.accepted_repair(
                "task-fallback-policy",
                "by simp",
                selected_block_kind="TheoremShellBlock",
                fallback_depth=1,
                fallback_origin="fallback",
            )
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-fallback-policy",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(
            responses=[
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                )
            ]
        ),
    )

    final_state = orchestrator.run_until_terminal(max_steps=5)

    assert final_state == RunState.FINISHED
    policy_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.POLICY
    ]
    assert policy_records[0].payload["triggered_rule_ids"] == [
        "fallback_acceptance_requires_review"
    ]
```

- [ ] **Step 2: Run focused test and verify failure**

```bash
cd python && uv run pytest tests/repair/unit/test_orchestrator.py::test_orchestrator_sends_fallback_metadata_to_policy -v
```

Expected: FAIL because `_gate_or_review` does not pass fallback fields.

- [ ] **Step 3: Pass fallback metadata into artifact policy context**

In `python/src/isabelle_repair/run/orchestrator.py`, update `_gate_or_review` `PolicyContext`:

```python
                block_kind=task_result.selected_block_kind or task_spec.task.block_kind,
                fallback_depth=task_result.fallback_depth,
                fallback_origin=task_result.fallback_origin,
```

Keep existing failure kind and artifact kind behavior.

- [ ] **Step 4: Record fallback fields in task and artifact records**

In `_record_task` and `_record_artifact`, add payload fields:

```python
"selected_block_kind": task_result.selected_block_kind,
"fallback_depth": task_result.fallback_depth,
"fallback_origin": task_result.fallback_origin,
```

If `_record_task` does not currently receive `task_result`, change its signature to receive `task_result: TaskResult` and update the call site. Keep existing payload fields.

- [ ] **Step 5: Run orchestrator and unit tests**

```bash
cd python && uv run pytest tests/repair/unit/test_orchestrator.py::test_orchestrator_sends_fallback_metadata_to_policy -v
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

---

### Task 6: Harden `ESCALATED` So It Cannot Auto-Apply As Repair

**Files:**
- Modify: `python/src/isabelle_repair/run/orchestrator.py`
- Modify: `python/tests/repair/unit/test_orchestrator.py`

- [ ] **Step 1: Write failing escalation test**

Append to `python/tests/repair/unit/test_orchestrator.py`:

```python
def test_escalated_task_enters_review_without_applying_artifact():
    task = make_localized_task(
        "task-escalated",
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
    )
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-escalated": TaskResult(
                task_id="task-escalated",
                outcome=TaskOutcome.ESCALATED,
                artifact_kind=ArtifactKind.REPAIR,
                artifact_text="by sorry",
                validation=ValidationResult(
                    status=ValidationStatus.INCONCLUSIVE,
                    reason="auto_candidates_exhausted_promote_review",
                ),
            )
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-escalated",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(),
        auto_resolve_review=False,
    )

    state = orchestrator.run_until_terminal(max_steps=5)

    assert state == RunState.AWAITING_REVIEW
    assert orchestrator.pending_review is not None
    assert not [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.ARTIFACT
    ]
```

Update imports for `ArtifactKind`, `TaskOutcome`, `TaskResult`, `ValidationResult`, and `ValidationStatus`.

- [ ] **Step 2: Run focused test and verify failure**

```bash
cd python && uv run pytest tests/repair/unit/test_orchestrator.py::test_escalated_task_enters_review_without_applying_artifact -v
```

Expected: FAIL because `ESCALATED` with artifact currently flows through artifact apply.

- [ ] **Step 3: Add escalation review path**

In `python/src/isabelle_repair/run/orchestrator.py`, after the `FAILED` handling and before artifact application:

```python
            if task_result.outcome == TaskOutcome.ESCALATED:
                self._enter_review(
                    task_spec=task_spec,
                    task_result=task_result,
                    policy_decision=PolicyDecision(
                        kind=PolicyDecisionKind.REQUIRES_REVIEW,
                        scope=PolicyDecisionScope.ARTIFACT_ACCEPTANCE,
                        triggered_rule_ids=["task_escalated_requires_review"],
                    ),
                    reason_code="task_escalated_requires_review",
                    allowed_response_kinds=[
                        InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT,
                        InterventionResponseKind.REQUEST_COMMITTED_PLACEHOLDER,
                        InterventionResponseKind.REQUEST_STOP,
                    ],
                )
                if not self.auto_resolve_review:
                    break
                if not self.resume_from_review():
                    continue
```

Add `PolicyDecisionScope` to imports.

- [ ] **Step 4: Run tests**

```bash
cd python && uv run pytest tests/repair/unit/test_orchestrator.py::test_escalated_task_enters_review_without_applying_artifact -v
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

---

### Task 7: Add Continuation-Gating Policy Check

**Files:**
- Modify: `python/src/isabelle_repair/run/orchestrator.py`
- Modify: `python/tests/repair/unit/test_orchestrator.py`

- [ ] **Step 1: Write failing continuation-gating test**

Append to `python/tests/repair/unit/test_orchestrator.py`:

```python
def test_fallback_rerun_continuation_requires_review_before_continue():
    task = make_localized_task("task-continuation-gate")
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-continuation-gate": RuleBasedTaskEngine.accepted_repair(
                "task-continuation-gate",
                "by simp",
                requires_rerun=True,
                selected_block_kind="TheoremShellBlock",
                fallback_depth=1,
                fallback_origin="fallback",
            )
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-continuation-gate",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(
            responses=[
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                ),
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                ),
            ]
        ),
    )

    final_state = orchestrator.run_until_terminal(max_steps=5)

    assert final_state == RunState.FINISHED
    policy_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.POLICY
    ]
    assert any(
        record.payload["reason_code"] == "continuation_gating"
        and record.payload["scope"] == "continuation_gating"
        for record in policy_records
    )
```

- [ ] **Step 2: Run focused test and verify failure**

```bash
cd python && uv run pytest tests/repair/unit/test_orchestrator.py::test_fallback_rerun_continuation_requires_review_before_continue -v
```

Expected: FAIL because continuation policy is not checked.

- [ ] **Step 3: Add continuation gate helper**

In `python/src/isabelle_repair/run/orchestrator.py`, add:

```python
    def _gate_continuation(
        self,
        task_spec: TaskSpec,
        task_result: TaskResult,
        continuation: ContinuationSelection,
    ) -> bool:
        decision = self.policy.decide(
            PolicyContext(
                theory_run_id=self.theory_run_id,
                task_id=task_result.task_id,
                failure_kind=task_spec.task.failure_kind,
                block_kind=task_result.selected_block_kind or task_spec.task.block_kind,
                artifact_kind=task_result.artifact_kind,
                reason_code="continuation_gating",
                fallback_depth=task_result.fallback_depth,
                fallback_origin=task_result.fallback_origin,
                continuation_kind=continuation.kind,
            )
        )
        self._emit_policy_decision(task_result.task_id, decision)
        self._record_policy(
            task_result.task_id,
            decision.kind.value,
            decision.scope.value,
            decision.triggered_rule_ids,
            reason_code="continuation_gating",
        )
        if decision.kind == PolicyDecisionKind.DENY:
            self._record_continuation(
                task_result.task_id,
                ContinuationSelection(kind=ContinuationKind.STOP, reason="continuation_denied"),
            )
            self._set_terminal(state=RunState.STOPPED, reason="stopped_continuation_denied")
            return False
        if decision.kind == PolicyDecisionKind.REQUIRES_REVIEW:
            self._enter_review(
                task_spec=task_spec,
                task_result=task_result,
                policy_decision=decision,
                reason_code="continuation_policy_requires_review",
                allowed_response_kinds=[
                    InterventionResponseKind.APPROVE_CURRENT_ARTIFACT,
                    InterventionResponseKind.REQUEST_STOP,
                ],
            )
            if not self.auto_resolve_review:
                return False
            return self.resume_from_review()
        return True
```

- [ ] **Step 4: Call continuation gate before recording continuation**

Before `_record_continuation(task_result.task_id, continuation)`, add:

```python
                if not self._gate_continuation(task_spec, task_result, continuation):
                    if self.state == RunState.AWAITING_REVIEW:
                        break
                    continue
```

- [ ] **Step 5: Run tests**

```bash
cd python && uv run pytest tests/repair/unit/test_orchestrator.py::test_fallback_rerun_continuation_requires_review_before_continue -v
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

---

### Task 8: Enforce Engine Validation Budget

**Files:**
- Modify: `python/src/isabelle_repair/repl/minimal.py`
- Modify: `python/tests/repair/unit/test_engine_localization.py`

- [ ] **Step 1: Write failing budget test**

Append to `python/tests/repair/unit/test_engine_localization.py`:

```python
def test_repl_engine_stops_when_validation_budget_is_exhausted():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="SUCCESS", mode="PROOF", proof_level=1),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-budget",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-budget",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
        max_validations=1,
    )

    result = engine.run(spec)

    assert result.outcome == TaskOutcome.FAILED
    assert result.validation is not None
    assert result.validation.reason == "validation_budget_exhausted"
    assert len(client.execute_calls) == 1
```

- [ ] **Step 2: Run focused test and verify failure**

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_repl_engine_stops_when_validation_budget_is_exhausted -v
```

Expected: FAIL because the engine currently validates all generated candidates.

- [ ] **Step 3: Thread budget into deterministic controller**

In `python/src/isabelle_repair/engine/controller.py`, before each candidate validation:

```python
            if validate_count >= task_spec.max_validations:
                return TaskResult(
                    task_id=task_spec.task.task_id,
                    outcome=TaskOutcome.FAILED,
                    validation=self._annotate_validation(
                        ValidationResult(
                            status=ValidationStatus.FAILED_CONTRACT,
                            reason="validation_budget_exhausted",
                        ),
                        source_name=candidate_source.source_name,
                        source_metadata=source_metadata,
                    ),
                    attempted_candidates=attempted_candidates,
                    selected_generator=candidate_source.source_name,
                    trace_summary=(
                        f"inspect={inspect_count} propose={propose_count} "
                        f"validate={validate_count} reason=validation_budget_exhausted "
                        f"source={candidate_source.source_name}"
                    ),
                )
```

This uses `max_validations` as the cap on REPL executions for candidate validation.

- [ ] **Step 4: Run tests**

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_repl_engine_stops_when_validation_budget_is_exhausted -v
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

---

### Task 9: Add Action-Count Trace Summary Without Full Action Runtime

**Files:**
- Modify: `python/src/isabelle_repair/model/types.py`
- Modify: `python/src/isabelle_repair/engine/controller.py`
- Modify: `python/src/isabelle_repair/repl/minimal.py`
- Modify: `python/tests/shared/repair_fakes.py`
- Modify: `python/tests/repair/unit/test_engine_localization.py`

- [ ] **Step 1: Write failing trace evidence test**

Append to `python/tests/repair/unit/test_engine_localization.py`:

```python
def test_controller_returns_action_count_trace_details():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="PROOF_COMPLETE", mode="THEORY", proof_level=0),
        ],
    )
    controller = DeterministicTaskController(
        client=client,
        generator=RuleFirstGenerator(client=client),
        adapters=ValidationAdapterRegistry.default(),
    )
    task = LocalizedTask(
        task_id="task-trace-details",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-trace-details",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )

    result = controller.run(spec)

    assert result.trace_counts == {
        "inspect": 1,
        "propose": 1,
        "validate": 1,
    }
```

- [ ] **Step 2: Run focused test and verify failure**

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_controller_returns_action_count_trace_details -v
```

Expected: FAIL because `TaskResult.trace_counts` does not exist.

- [ ] **Step 3: Add trace counts field**

In `python/src/isabelle_repair/model/types.py`, add to `TaskResult`:

```python
    trace_counts: dict[str, int] = field(default_factory=dict)
```

- [ ] **Step 4: Populate trace counts in controller**

In `python/src/isabelle_repair/engine/controller.py`, every `TaskResult` returned from `run_with_source` should include:

```python
trace_counts={
    "inspect": inspect_count,
    "propose": propose_count,
    "validate": validate_count,
},
```

For early missing-source-state return, use:

```python
trace_counts={"inspect": 0, "propose": 0, "validate": 0},
```

- [ ] **Step 5: Preserve trace counts in REPL engine and fakes**

In `python/src/isabelle_repair/repl/minimal.py`, add a helper inside `run` before the fallback loop:

```python
        aggregate_trace_counts = {"inspect": 0, "propose": 0, "validate": 0}

        def add_trace_counts(result: TaskResult) -> None:
            for key in aggregate_trace_counts:
                aggregate_trace_counts[key] += int(result.trace_counts.get(key, 0))
```

After each controller result:

```python
            add_trace_counts(result)
```

When returning accepted result, pass:

```python
                    trace_counts=dict(aggregate_trace_counts),
```

When returning promoted review fallback, pass:

```python
                trace_counts=dict(aggregate_trace_counts),
```

When returning failed result, pass:

```python
            trace_counts=dict(aggregate_trace_counts),
```

In `python/tests/shared/repair_fakes.py`, preserve `trace_counts` in `RuleBasedTaskEngine.run`.

- [ ] **Step 6: Run tests**

```bash
cd python && uv run pytest tests/repair/unit/test_engine_localization.py::test_controller_returns_action_count_trace_details -v
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

---

### Task 10: Refresh Docs And Traceability For Batch 4-6

**Files:**
- Modify: `docs/modules/failure-classification-and-localization-prd.md`
- Modify: `docs/modules/repair-task-engine-prd.md`
- Modify: `docs/modules/policy-and-risk-gate-prd.md`
- Modify: `docs/v1_5/architecture/repair-agent-traceability-matrix.md`
- Modify: `python/tests/repair/unit/test_docs_authority.py`

- [ ] **Step 1: Add docs authority tests**

Append to `python/tests/repair/unit/test_docs_authority.py`:

```python
def test_batch_4_6_docs_name_high_risk_and_engine_evidence():
    traceability = (
        ROOT / "docs/v1_5/architecture/repair-agent-traceability-matrix.md"
    ).read_text(encoding="utf-8")
    localization = (
        ROOT / "docs/modules/failure-classification-and-localization-prd.md"
    ).read_text(encoding="utf-8")
    engine = (ROOT / "docs/modules/repair-task-engine-prd.md").read_text(
        encoding="utf-8"
    )
    policy = (ROOT / "docs/modules/policy-and-risk-gate-prd.md").read_text(
        encoding="utf-8"
    )

    assert "TopLevelCommandBlock" in localization
    assert "test_top_level_command_adapter_accepts_theory_context_success" in traceability
    assert "test_escalated_task_enters_review_without_applying_artifact" in traceability
    assert "test_repl_engine_stops_when_validation_budget_is_exhausted" in traceability
    assert "budgeted deterministic trace" in engine
    assert "fallback and continuation gating" in policy
```

- [ ] **Step 2: Run focused docs test and verify failure**

```bash
cd python && uv run pytest tests/repair/unit/test_docs_authority.py::test_batch_4_6_docs_name_high_risk_and_engine_evidence -v
```

Expected: FAIL until docs are updated.

- [ ] **Step 3: Update localization implemented subset**

In `docs/modules/failure-classification-and-localization-prd.md`, add `TopLevelCommandBlock` to the implemented runtime block list and add `context_updated` to implemented runtime contracts.

Replace the sentence saying `TopLevelCommandBlock` remains future work with:

```markdown
`TopLevelCommandBlock` has minimal v1.5 runtime validation support through the
`context_updated` contract. Autonomous generation remains conservative; reviewed
or externally supplied replacements are the primary supported path.
```

- [ ] **Step 4: Update repair engine implemented subset**

In `docs/modules/repair-task-engine-prd.md`, add:

```markdown
The current runtime also includes budgeted deterministic trace evidence:

- validation budget enforcement through `max_validations`
- compact action-count summaries for inspect/propose/validate
- structured fallback block metadata on accepted task results
```

Ensure the exact phrase `budgeted deterministic trace` appears.

- [ ] **Step 5: Update policy implemented subset**

In `docs/modules/policy-and-risk-gate-prd.md`, add before `## Testing Decisions`:

```markdown
## Implemented v1.5 Subset

The current runtime includes fallback and continuation gating for the v1.5
single-theory repair loop.

Implemented policy inputs include failure kind, block kind, artifact kind,
fallback depth, fallback origin, and continuation kind. High-risk failure kinds
still require review, committed placeholder policy remains configurable, and
fallback-based repair acceptance or rerun continuation can require review.
```

- [ ] **Step 6: Update traceability matrix**

In `docs/v1_5/architecture/repair-agent-traceability-matrix.md`, add:

```markdown
## High-Risk And Engine Hardening Evidence

| Concern | Evidence test |
| --- | --- |
| Top-level command validation | `test_top_level_command_adapter_accepts_theory_context_success` |
| Escalated task does not auto-apply artifact | `test_escalated_task_enters_review_without_applying_artifact` |
| Fallback continuation gating | `test_fallback_rerun_continuation_requires_review_before_continue` |
| Engine validation budget | `test_repl_engine_stops_when_validation_budget_is_exhausted` |
| Engine action-count trace | `test_controller_returns_action_count_trace_details` |
```

- [ ] **Step 7: Run docs and repair tests**

```bash
cd python && uv run pytest tests/repair/unit/test_docs_authority.py -v
cd python && uv run pytest tests/repair/unit
cd python && uv run python scripts/check_repair_acceptance_gate.py
```

Expected: PASS.

---

## Final Verification

- [ ] **Step 1: Run repair unit suite**

```bash
cd python && uv run pytest tests/repair/unit
```

Expected: PASS.

- [ ] **Step 2: Run repair acceptance gate**

```bash
cd python && uv run python scripts/check_repair_acceptance_gate.py
```

Expected: PASS with `Repair acceptance gate PASSED`.

- [ ] **Step 3: Run focused integration smoke if local REPL environment is available**

```bash
cd python && uv run pytest tests/repair/integration/test_single_theory_flow.py -v
```

Expected: PASS if local dependencies are available. If unavailable, record the exact environment blocker.

- [ ] **Step 4: Check changed files**

```bash
git status --short
```

Expected: only intentional changes from Batch 4-6 plus pre-existing dirty workspace files are present. Do not commit until the repository cleanup pass unless the user explicitly re-enables commits.

## Self-Review Notes

- Batch 4 maps to Tasks 1, 2, and 10.
- Batch 5 maps to Tasks 3, 5, 6, 7, and 10.
- Batch 6 maps to Tasks 4, 8, 9, and 10.
- This plan avoids the full action-runtime model and keeps deterministic engine changes bounded to validation budgets and trace counts.
- No unresolved-marker language is used.
