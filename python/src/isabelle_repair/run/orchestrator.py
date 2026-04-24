from __future__ import annotations

from dataclasses import dataclass, field

from isabelle_repair.hooks import validate_intervention_response
from isabelle_repair.localization import contract_for_block_kind
from isabelle_repair.model import (
    ArtifactKind,
    BlockContract,
    ContinuationKind,
    ContinuationSelection,
    HookTriggerSource,
    InterventionContext,
    InterventionResponse,
    InterventionResponseKind,
    Localizer,
    PendingReview,
    PolicyContext,
    PolicyDecision,
    PolicyDecisionKind,
    PolicyDecisionScope,
    PolicyGate,
    RecordFactory,
    RecordStore,
    ReviewHook,
    RunMode,
    RunRecordKind,
    RunState,
    TaskEngine,
    TaskOutcome,
    TaskResult,
    TaskSpec,
    ValidationStatus,
)

from .observability import MultiEventLogger
from .working_snapshot import WorkingTheorySnapshot


@dataclass
class TheoryRepairOrchestrator:
    theory_run_id: str
    localizer: Localizer
    engine: TaskEngine
    policy: PolicyGate
    hook: ReviewHook
    record_store: RecordStore
    record_factory: RecordFactory
    snapshot: WorkingTheorySnapshot
    logger: MultiEventLogger | None = None
    auto_resolve_review: bool = True
    run_mode: RunMode = RunMode.THEORY_WIDE
    target_max_tasks: int | None = None
    state: RunState = RunState.ACTIVE
    pending_review: PendingReview | None = None
    accepted_artifact_count: int = 0
    terminal_reason: str | None = None
    applied_artifact_task_ids: set[str] = field(default_factory=set)

    def run_until_terminal(self, max_steps: int = 100) -> RunState:
        self._emit(
            "run_started",
            payload={
                "max_steps": max_steps,
                "run_mode": self.run_mode.value,
                "target_max_tasks": self.target_max_tasks,
            },
        )
        steps = 0
        while self.state == RunState.ACTIVE and steps < max_steps:
            steps += 1
            localized = self.localizer.next_task(self.theory_run_id, self.snapshot)
            if localized is None:
                self._finalize_without_next_task()
                break
            self._emit(
                "task_selected",
                task_id=localized.task_id,
                payload={
                    "failure_kind": localized.failure_kind.value,
                    "block_kind": localized.block_kind,
                },
            )

            task_spec = TaskSpec(
                theory_run_id=self.theory_run_id,
                task=localized,
                block_contract=contract_for_block_kind(localized.block_kind)
                or BlockContract.GOAL_CLOSED,
            )
            task_result = self.engine.run(task_spec)
            self._emit(
                "task_result",
                task_id=task_result.task_id,
                payload={
                    "outcome": task_result.outcome.value,
                    "artifact_kind": (
                        task_result.artifact_kind.value
                        if task_result.artifact_kind
                        else None
                    ),
                },
            )
            self._record_task(
                task_result=task_result,
                block_kind=task_spec.task.block_kind,
                localizer_drift_reason=(
                    (localized.metadata or {}).get("drift_fallback_reason")
                ),
            )

            if task_result.outcome == TaskOutcome.FAILED:
                self._record_continuation(
                    task_result.task_id,
                    ContinuationSelection(
                        kind=ContinuationKind.STOP,
                        reason="task_failed",
                    ),
                )
                self._set_terminal(state=RunState.STOPPED, reason="stopped_task_failed")
                break

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
                if self._is_terminal_state(self.state):
                    break
                continue

            if task_result.artifact_kind and task_result.artifact_text:
                accepted = self._gate_or_review(task_spec, task_result)
                if self.state == RunState.AWAITING_REVIEW:
                    break
                if not accepted:
                    continue
                self._apply_accepted_artifact(task_spec, task_result)
                if self._is_terminal_state(self.state):
                    break

        if self._is_terminal_state(self.state):
            self._emit(
                "run_finished",
                payload={
                    "final_state": self.state.value,
                    "terminal_reason": self.terminal_reason,
                },
            )
            self._record_terminal()
        else:
            self._emit(
                "run_paused",
                payload={"state": self.state.value, "max_steps": max_steps},
            )
        return self.state

    def resume_from_review(self, response: InterventionResponse | None = None) -> bool:
        if self.state != RunState.AWAITING_REVIEW or self.pending_review is None:
            return False
        pending = self.pending_review
        raw_response = response or self.hook.handle(pending.context)
        guard_result = validate_intervention_response(pending.context, raw_response)
        resolved_response = guard_result.response
        invalid_response_reason = guard_result.invalid_response_reason

        self._emit(
            "review_resolved",
            task_id=pending.task_result.task_id,
            payload={
                "response_kind": resolved_response.kind.value,
                "invalid_response_reason": invalid_response_reason,
            },
        )
        self._record_intervention(
            task_id=pending.task_result.task_id,
            reason_code=pending.context.reason_code,
            allowed_response_kinds=[
                kind.value for kind in pending.context.allowed_response_kinds
            ],
            response_kind=resolved_response.kind.value,
            invalid_response_reason=invalid_response_reason,
        )
        self.pending_review = None
        self._set_state(RunState.ACTIVE)
        accepted = self._apply_review_response(
            task_spec=pending.task_spec,
            task_result=pending.task_result,
            response=resolved_response,
            invalid_response_reason=invalid_response_reason,
        )
        if (
            accepted
            and pending.context.reason_code == "continuation_policy_requires_review"
        ):
            self._finalize_accepted_continuation(
                pending.task_result.task_id,
                self._continuation_for_result(pending.task_result),
            )
        elif accepted and pending.context.reason_code in {
            "policy_requires_review",
            "task_escalated_requires_review",
            "placeholder_policy_requires_review",
        }:
            self._apply_accepted_artifact(pending.task_spec, pending.task_result)
        return accepted

    def _gate_or_review(self, task_spec: TaskSpec, task_result: TaskResult) -> bool:
        policy_decision = self.policy.decide(
            PolicyContext(
                theory_run_id=self.theory_run_id,
                task_id=task_result.task_id,
                failure_kind=task_spec.task.failure_kind,
                block_kind=task_result.selected_block_kind or task_spec.task.block_kind,
                artifact_kind=task_result.artifact_kind,
                reason_code="task_artifact_evaluation",
                fallback_depth=task_result.fallback_depth,
                fallback_origin=task_result.fallback_origin,
                localization_confidence=task_result.localization_confidence,
            )
        )
        self._emit_policy_decision(task_result.task_id, policy_decision)
        self._record_policy(
            task_result.task_id,
            policy_decision.kind.value,
            policy_decision.scope.value,
            policy_decision.triggered_rule_ids,
            reason_code="task_artifact_evaluation",
        )

        if policy_decision.kind == PolicyDecisionKind.DENY:
            return False
        if policy_decision.kind == PolicyDecisionKind.ALLOW:
            return True

        self._enter_review(
            task_spec=task_spec,
            task_result=task_result,
            policy_decision=policy_decision,
            reason_code="policy_requires_review",
        )
        if not self.auto_resolve_review:
            return False
        self.resume_from_review()
        return False

    def _enter_review(
        self,
        *,
        task_spec: TaskSpec,
        task_result: TaskResult,
        policy_decision: PolicyDecision,
        reason_code: str,
        allowed_response_kinds: list[InterventionResponseKind] | None = None,
    ) -> None:
        allowed = allowed_response_kinds or [
            InterventionResponseKind.APPROVE_CURRENT_ARTIFACT,
            InterventionResponseKind.REJECT_CURRENT_ARTIFACT,
            InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT,
            InterventionResponseKind.REQUEST_COMMITTED_PLACEHOLDER,
            InterventionResponseKind.REQUEST_STOP,
        ]
        context = InterventionContext(
            trigger_source=HookTriggerSource.POLICY_TRIGGERED,
            reason_code=reason_code,
            task_id=task_result.task_id,
            current_artifact_text=task_result.artifact_text,
            current_artifact_kind=task_result.artifact_kind,
            policy_decision=policy_decision,
            validation=task_result.validation,
            allowed_response_kinds=allowed,
        )
        self.pending_review = PendingReview(
            task_spec=task_spec,
            task_result=task_result,
            context=context,
        )
        self._set_state(RunState.AWAITING_REVIEW)
        self._emit("review_entered", task_id=task_result.task_id)
        self._record_intervention(
            task_id=task_result.task_id,
            reason_code=reason_code,
            allowed_response_kinds=[kind.value for kind in allowed],
            response_kind=None,
            invalid_response_reason=None,
        )

    def _apply_review_response(
        self,
        *,
        task_spec: TaskSpec,
        task_result: TaskResult,
        response: InterventionResponse,
        invalid_response_reason: str | None,
    ) -> bool:
        if response.kind == InterventionResponseKind.REQUEST_STOP:
            self._record_continuation(
                task_result.task_id,
                ContinuationSelection(
                    kind=ContinuationKind.STOP,
                    reason="hook_requested_stop",
                ),
            )
            self._set_terminal(state=RunState.STOPPED, reason="stopped_by_review_stop")
            return False

        if invalid_response_reason is not None:
            return False

        if response.kind == InterventionResponseKind.REJECT_CURRENT_ARTIFACT:
            return False
        if response.kind == InterventionResponseKind.APPROVE_CURRENT_ARTIFACT:
            return True

        if response.kind == InterventionResponseKind.REQUEST_COMMITTED_PLACEHOLDER:
            return self._resolve_placeholder_request(task_spec, task_result)

        if (
            response.kind == InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT
            and response.replacement_artifact_text
        ):
            validation = self.engine.validate_candidate(
                task_spec, response.replacement_artifact_text
            )
            task_result.validation = validation
            task_result.selected_generator = "review_injected"
            task_result.attempted_candidates.append(response.replacement_artifact_text)
            if validation.status == ValidationStatus.PASSED:
                task_result.artifact_text = response.replacement_artifact_text
                task_result.artifact_kind = ArtifactKind.REPAIR
                return True
            return False
        return False

    def _apply_accepted_artifact(
        self,
        task_spec: TaskSpec,
        task_result: TaskResult,
    ) -> None:
        if task_result.artifact_kind is None or task_result.artifact_text is None:
            return
        if task_result.task_id in self.applied_artifact_task_ids:
            return
        self.snapshot.apply_artifact(
            task_result.artifact_kind,
            task_result.artifact_text,
            task_id=task_result.task_id,
            command_line=self._command_line_for_task(task_spec),
            original_text=task_spec.task.block_text,
        )
        self._emit(
            "artifact_applied",
            task_id=task_result.task_id,
            payload={
                "artifact_kind": task_result.artifact_kind.value,
                "artifact_text": task_result.artifact_text,
            },
        )
        self._record_artifact(
            task_id=task_result.task_id,
            task_result=task_result,
        )
        self.applied_artifact_task_ids.add(task_result.task_id)
        continuation = self._continuation_for_result(task_result)
        if self._requires_continuation_gate(task_result, continuation) and not (
            self._gate_continuation(task_spec, task_result, continuation)
        ):
            return
        self._finalize_accepted_continuation(task_result.task_id, continuation)

    def _continuation_for_result(
        self,
        task_result: TaskResult,
    ) -> ContinuationSelection:
        return ContinuationSelection(
            kind=(
                ContinuationKind.RERUN_THEN_CONTINUE
                if task_result.requires_rerun
                else ContinuationKind.CONTINUE
            ),
            reason="accepted_artifact",
        )

    @staticmethod
    def _requires_continuation_gate(
        task_result: TaskResult,
        continuation: ContinuationSelection,
    ) -> bool:
        return (
            continuation.kind == ContinuationKind.RERUN_THEN_CONTINUE
            and task_result.fallback_depth > 0
        )

    def _gate_continuation(
        self,
        task_spec: TaskSpec,
        task_result: TaskResult,
        continuation: ContinuationSelection,
    ) -> bool:
        policy_decision = self.policy.decide(
            PolicyContext(
                theory_run_id=self.theory_run_id,
                task_id=task_result.task_id,
                failure_kind=task_spec.task.failure_kind,
                block_kind=task_result.selected_block_kind or task_spec.task.block_kind,
                artifact_kind=task_result.artifact_kind,
                reason_code="continuation_gating",
                fallback_depth=task_result.fallback_depth,
                fallback_origin=task_result.fallback_origin,
                localization_confidence=task_result.localization_confidence,
                continuation_kind=continuation.kind,
            )
        )
        self._emit_policy_decision(task_result.task_id, policy_decision)
        self._record_policy(
            task_result.task_id,
            policy_decision.kind.value,
            policy_decision.scope.value,
            policy_decision.triggered_rule_ids,
            reason_code="continuation_gating",
        )
        if policy_decision.kind == PolicyDecisionKind.DENY:
            self._record_continuation(
                task_result.task_id,
                ContinuationSelection(
                    kind=ContinuationKind.STOP,
                    reason="continuation_denied",
                ),
            )
            self._set_terminal(
                state=RunState.STOPPED,
                reason="stopped_continuation_denied",
            )
            return False
        if policy_decision.kind == PolicyDecisionKind.REQUIRES_REVIEW:
            self._enter_review(
                task_spec=task_spec,
                task_result=task_result,
                policy_decision=policy_decision,
                reason_code="continuation_policy_requires_review",
                allowed_response_kinds=[
                    InterventionResponseKind.APPROVE_CURRENT_ARTIFACT,
                    InterventionResponseKind.REQUEST_STOP,
                ],
            )
            if self.auto_resolve_review:
                self.resume_from_review()
            return False
        return True

    def _finalize_accepted_continuation(
        self,
        task_id: str,
        continuation: ContinuationSelection,
    ) -> None:
        self._record_continuation(task_id, continuation)
        self._record_provenance(task_id)
        self.accepted_artifact_count += 1
        if self._target_boundary_reached():
            self._set_terminal(
                state=RunState.COMPLETED,
                reason="target_boundary_completed",
            )

    def _resolve_placeholder_request(
        self,
        task_spec: TaskSpec,
        task_result: TaskResult,
    ) -> bool:
        if task_result.artifact_text is None:
            return False
        policy_decision = self.policy.decide(
            PolicyContext(
                theory_run_id=self.theory_run_id,
                task_id=task_result.task_id,
                failure_kind=task_spec.task.failure_kind,
                block_kind=task_spec.task.block_kind,
                artifact_kind=ArtifactKind.COMMITTED_PLACEHOLDER,
                reason_code="review_placeholder_request",
                is_placeholder_request=True,
            )
        )
        self._emit_policy_decision(task_result.task_id, policy_decision)
        self._record_policy(
            task_result.task_id,
            policy_decision.kind.value,
            policy_decision.scope.value,
            policy_decision.triggered_rule_ids,
            reason_code="review_placeholder_request",
        )
        if policy_decision.kind == PolicyDecisionKind.DENY:
            return False
        if policy_decision.kind == PolicyDecisionKind.REQUIRES_REVIEW:
            original_artifact_kind = task_result.artifact_kind
            task_result.artifact_kind = ArtifactKind.COMMITTED_PLACEHOLDER
            self._enter_review(
                task_spec=task_spec,
                task_result=task_result,
                policy_decision=policy_decision,
                reason_code="placeholder_policy_requires_review",
                allowed_response_kinds=[
                    InterventionResponseKind.APPROVE_CURRENT_ARTIFACT,
                    InterventionResponseKind.REJECT_CURRENT_ARTIFACT,
                    InterventionResponseKind.REQUEST_STOP,
                ],
            )
            if not self.auto_resolve_review:
                return False
            accepted = self.resume_from_review()
            if not accepted and self.state != RunState.AWAITING_REVIEW:
                task_result.artifact_kind = original_artifact_kind
            return accepted
        task_result.artifact_kind = ArtifactKind.COMMITTED_PLACEHOLDER
        return True

    def _emit_policy_decision(
        self, task_id: str, policy_decision: PolicyDecision
    ) -> None:
        self._emit(
            "policy_decision",
            task_id=task_id,
            payload={
                "decision_kind": policy_decision.kind.value,
                "scope": policy_decision.scope.value,
                "triggered_rule_ids": policy_decision.triggered_rule_ids,
            },
        )

    def _record_task(
        self,
        *,
        task_result: TaskResult,
        block_kind: str,
        localizer_drift_reason: str | None,
    ) -> None:
        fallback_target_contract = (
            task_result.fallback_target_contract.value
            if task_result.fallback_target_contract
            else None
        )
        self._append_record(
            self.record_factory.create(
                record_kind=RunRecordKind.TASK,
                task_id=task_result.task_id,
                payload={
                    "outcome": task_result.outcome.value,
                    "block_kind": block_kind,
                    "selected_generator": task_result.selected_generator,
                    "validation_status": (
                        task_result.validation.status.value
                        if task_result.validation
                        else None
                    ),
                    "localizer_drift_reason": localizer_drift_reason,
                    "selected_block_kind": task_result.selected_block_kind,
                    "fallback_depth": task_result.fallback_depth,
                    "fallback_origin": task_result.fallback_origin,
                    "fallback_target_contract": fallback_target_contract,
                    "localization_confidence": task_result.localization_confidence,
                    "snapshot": self.snapshot.to_metadata(),
                },
            )
        )

    def _record_artifact(
        self,
        *,
        task_id: str,
        task_result: TaskResult,
    ) -> None:
        artifact_kind = (
            task_result.artifact_kind.value if task_result.artifact_kind else None
        )
        fallback_target_contract = (
            task_result.fallback_target_contract.value
            if task_result.fallback_target_contract
            else None
        )
        record = self.record_factory.create(
            record_kind=RunRecordKind.ARTIFACT,
            task_id=task_id,
            payload={
                "artifact_kind": artifact_kind,
                "artifact_text": task_result.artifact_text,
                "selected_generator": task_result.selected_generator,
                "selected_block_kind": task_result.selected_block_kind,
                "fallback_depth": task_result.fallback_depth,
                "fallback_origin": task_result.fallback_origin,
                "fallback_target_contract": fallback_target_contract,
                "localization_confidence": task_result.localization_confidence,
                "attempted_candidates": list(task_result.attempted_candidates),
                "validation_status": (
                    task_result.validation.status.value
                    if task_result.validation
                    else None
                ),
                "snapshot": self.snapshot.to_metadata(),
            },
        )
        self._append_record(record)
        self.snapshot.attach_artifact_record_id(
            task_id=task_id,
            record_id=record.record_id,
        )

    def _record_policy(
        self,
        task_id: str,
        decision_kind: str,
        scope: str,
        triggered_rule_ids: list[str],
        *,
        reason_code: str | None,
    ) -> None:
        self._append_record(
            self.record_factory.create(
                record_kind=RunRecordKind.POLICY,
                task_id=task_id,
                payload={
                    "decision_kind": decision_kind,
                    "scope": scope,
                    "triggered_rule_ids": list(triggered_rule_ids),
                    "reason_code": reason_code,
                },
            )
        )

    def _record_intervention(
        self,
        *,
        task_id: str,
        reason_code: str,
        allowed_response_kinds: list[str],
        response_kind: str | None,
        invalid_response_reason: str | None,
    ) -> None:
        self._append_record(
            self.record_factory.create(
                record_kind=RunRecordKind.INTERVENTION,
                task_id=task_id,
                payload={
                    "reason_code": reason_code,
                    "allowed_response_kinds": allowed_response_kinds,
                    "response_kind": response_kind,
                    "invalid_response_reason": invalid_response_reason,
                },
            )
        )

    def _record_provenance(self, task_id: str) -> None:
        self._append_record(
            self.record_factory.create(
                record_kind=RunRecordKind.PROVENANCE,
                task_id=task_id,
                payload={"linked_to": "task/artifact/policy/continuation"},
            )
        )

    def _record_terminal(self) -> None:
        if self.terminal_reason is None:
            return
        self._append_record(
            self.record_factory.create(
                record_kind=RunRecordKind.TERMINAL,
                task_id=None,
                payload={
                    "final_state": self.state.value,
                    "terminal_reason": self.terminal_reason,
                    "run_mode": self.run_mode.value,
                    "target_max_tasks": self.target_max_tasks,
                    "accepted_artifact_count": self.accepted_artifact_count,
                },
            )
        )

    def _record_continuation(
        self, task_id: str, continuation: ContinuationSelection
    ) -> None:
        self._emit(
            "continuation_selected",
            task_id=task_id,
            payload={
                "continuation_kind": continuation.kind.value,
                "reason": continuation.reason,
            },
        )
        self._append_record(
            self.record_factory.create(
                record_kind=RunRecordKind.CONTINUATION,
                task_id=task_id,
                payload={
                    "continuation_kind": continuation.kind.value,
                    "reason": continuation.reason,
                },
            )
        )

    def _append_record(self, record) -> None:
        self.record_store.append(record)

    @staticmethod
    def _command_line_for_task(task_spec: TaskSpec) -> int | None:
        for key in ("line", "command_line"):
            raw = task_spec.task.metadata.get(key)
            if raw is None:
                continue
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
        return None

    def _set_state(self, state: RunState) -> None:
        self.state = state

    def _set_terminal(self, *, state: RunState, reason: str) -> None:
        self.state = state
        self.terminal_reason = reason

    def _finalize_without_next_task(self) -> None:
        if self.run_mode == RunMode.TARGET_BOUNDARY:
            self._set_terminal(
                state=RunState.COMPLETED,
                reason="target_boundary_completed",
            )
            return
        self._set_terminal(
            state=RunState.FINISHED,
            reason="theory_wide_finished",
        )

    def _target_boundary_reached(self) -> bool:
        if self.run_mode != RunMode.TARGET_BOUNDARY:
            return False
        if self.target_max_tasks is None:
            return False
        return self.accepted_artifact_count >= self.target_max_tasks

    @staticmethod
    def _is_terminal_state(state: RunState) -> bool:
        return state in (RunState.STOPPED, RunState.COMPLETED, RunState.FINISHED)

    def _emit(
        self,
        event: str,
        *,
        task_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        if self.logger is None:
            return
        self.logger.emit(
            event=event,
            task_id=task_id,
            state=self.state.value,
            payload=payload or {},
        )
