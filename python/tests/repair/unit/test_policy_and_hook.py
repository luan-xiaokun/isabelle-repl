from __future__ import annotations

from pathlib import Path

import pytest

from isabelle_repair.hooks import StaticReviewHook, validate_intervention_response
from isabelle_repair.model import (
    ArtifactKind,
    ContinuationKind,
    FailureKind,
    HookTriggerSource,
    InterventionContext,
    InterventionResponse,
    InterventionResponseKind,
    PolicyContext,
    PolicyDecisionKind,
    PolicyDecisionScope,
)
from isabelle_repair.policy import RuleBasedPolicyGate, load_policy_config
from isabelle_repair.policy.config import (
    PlaceholderPolicyConfig,
    PlaceholderPolicyMode,
    PolicyConfig,
)


def test_policy_requires_review_for_statement_failure():
    gate = RuleBasedPolicyGate()
    decision = gate.decide(
        PolicyContext(
            theory_run_id="run-1",
            task_id="task-1",
            failure_kind=FailureKind.STATEMENT_FAILURE,
            block_kind="TheoremShellBlock",
            artifact_kind=ArtifactKind.REPAIR,
        )
    )
    assert decision.kind == PolicyDecisionKind.REQUIRES_REVIEW


def test_policy_can_deny_committed_placeholder():
    gate = RuleBasedPolicyGate(
        config=PolicyConfig(
            placeholder=PlaceholderPolicyConfig(mode=PlaceholderPolicyMode.DENY)
        )
    )
    decision = gate.decide(
        PolicyContext(
            theory_run_id="run-1",
            task_id="task-1",
            failure_kind=FailureKind.PROOF_BODY_FAILURE,
            block_kind="WholeProofBodyBlock",
            artifact_kind=ArtifactKind.COMMITTED_PLACEHOLDER,
            is_placeholder_request=True,
        )
    )
    assert decision.kind == PolicyDecisionKind.DENY


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


def test_policy_loader_uses_default_config():
    config = load_policy_config()
    assert FailureKind.STATEMENT_FAILURE in config.high_risk_failure_kinds


def test_policy_loader_cli_override(tmp_path: Path):
    policy_path = tmp_path / "policy.toml"
    policy_path.write_text(
        """
[policy]
default_scope = "artifact_acceptance"
high_risk_failure_kinds = ["statement_failure"]

[placeholder]
mode = "deny"

[rule_ids]
high_risk_failure_requires_review = "risk_review"
placeholder_allow = "allow_placeholder"
placeholder_deny = "deny_placeholder"
placeholder_requires_review = "placeholder_review"
fallback_acceptance_requires_review = "custom_fallback_acceptance_review"
fallback_continuation_requires_review = "custom_fallback_continuation_review"
default_allow = "default_allow"
""".strip(),
        encoding="utf-8",
    )
    config = load_policy_config(policy_path)
    assert config.placeholder.mode == PlaceholderPolicyMode.DENY
    assert config.rule_ids.placeholder_deny == "deny_placeholder"
    assert (
        config.rule_ids.fallback_acceptance_requires_review
        == "custom_fallback_acceptance_review"
    )
    assert (
        config.rule_ids.fallback_continuation_requires_review
        == "custom_fallback_continuation_review"
    )


def test_policy_loader_rejects_duplicate_rule_ids(tmp_path: Path):
    policy_path = tmp_path / "duplicate_rules.toml"
    policy_path.write_text(
        """
[policy]
default_scope = "artifact_acceptance"
high_risk_failure_kinds = ["statement_failure"]

[placeholder]
mode = "allow"

[rule_ids]
high_risk_failure_requires_review = "duplicate"
placeholder_allow = "placeholder_allow"
placeholder_deny = "placeholder_deny"
placeholder_requires_review = "placeholder_requires_review"
fallback_acceptance_requires_review = "duplicate"
fallback_continuation_requires_review = "fallback_continuation_requires_review"
default_allow = "default_allow"
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="rule_ids values must be unique"):
        load_policy_config(policy_path)


def test_policy_loader_rejects_invalid_toml(tmp_path: Path):
    policy_path = tmp_path / "broken.toml"
    policy_path.write_text("not = [valid", encoding="utf-8")
    with pytest.raises(ValueError):
        load_policy_config(policy_path)


def test_static_hook_returns_preconfigured_response():
    hook = StaticReviewHook(
        response_factory=InterventionResponse(
            kind=InterventionResponseKind.REQUEST_STOP
        )
    )
    response = hook.handle(
        InterventionContext(
            trigger_source=HookTriggerSource.POLICY_TRIGGERED,
            reason_code="manual_test",
            task_id="task-1",
            current_artifact_text="by simp",
            current_artifact_kind=ArtifactKind.REPAIR,
            policy_decision=None,
            validation=None,
            allowed_response_kinds=[InterventionResponseKind.REQUEST_STOP],
        )
    )
    assert response.kind == InterventionResponseKind.REQUEST_STOP


def test_guard_rejects_disallowed_response():
    context = InterventionContext(
        trigger_source=HookTriggerSource.POLICY_TRIGGERED,
        reason_code="policy_requires_review",
        task_id="task-1",
        current_artifact_text="by simp",
        current_artifact_kind=ArtifactKind.REPAIR,
        policy_decision=None,
        validation=None,
        allowed_response_kinds=[InterventionResponseKind.REQUEST_STOP],
    )
    result = validate_intervention_response(
        context,
        InterventionResponse(kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT),
    )
    assert not result.is_valid
    assert result.invalid_response_reason is not None
    assert result.response.kind == InterventionResponseKind.REJECT_CURRENT_ARTIFACT


def test_guard_rejects_replacement_without_text():
    context = InterventionContext(
        trigger_source=HookTriggerSource.POLICY_TRIGGERED,
        reason_code="policy_requires_review",
        task_id="task-1",
        current_artifact_text="by simp",
        current_artifact_kind=ArtifactKind.REPAIR,
        policy_decision=None,
        validation=None,
        allowed_response_kinds=[
            InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT,
        ],
    )
    result = validate_intervention_response(
        context,
        InterventionResponse(
            kind=InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT
        ),
    )
    assert not result.is_valid
    assert result.invalid_response_reason == "replacement_artifact_text_missing"
