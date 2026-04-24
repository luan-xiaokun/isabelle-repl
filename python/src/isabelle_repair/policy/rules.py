from __future__ import annotations

from dataclasses import dataclass, field

from isabelle_repair.model import (
    ArtifactKind,
    PolicyContext,
    PolicyDecision,
    PolicyDecisionKind,
    PolicyDecisionScope,
)

from .config import PlaceholderPolicyMode, PolicyConfig


@dataclass
class RuleBasedPolicyGate:
    config: PolicyConfig = field(default_factory=PolicyConfig)

    def decide(self, context: PolicyContext) -> PolicyDecision:
        if (
            context.artifact_kind == ArtifactKind.COMMITTED_PLACEHOLDER
            or context.is_placeholder_request
        ):
            return self._placeholder_decision()

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

        if context.failure_kind in self.config.high_risk_failure_kinds:
            return PolicyDecision(
                kind=PolicyDecisionKind.REQUIRES_REVIEW,
                scope=self.config.default_scope,
                triggered_rule_ids=[
                    self.config.rule_ids.high_risk_failure_requires_review
                ],
            )

        return PolicyDecision(
            kind=PolicyDecisionKind.ALLOW,
            scope=self.config.default_scope,
            triggered_rule_ids=[self.config.rule_ids.default_allow],
        )

    def _placeholder_decision(self) -> PolicyDecision:
        mode = self.config.placeholder.mode
        if mode == PlaceholderPolicyMode.DENY:
            return PolicyDecision(
                kind=PolicyDecisionKind.DENY,
                scope=self.config.default_scope,
                triggered_rule_ids=[self.config.rule_ids.placeholder_deny],
            )
        if mode == PlaceholderPolicyMode.REQUIRES_REVIEW:
            return PolicyDecision(
                kind=PolicyDecisionKind.REQUIRES_REVIEW,
                scope=self.config.default_scope,
                triggered_rule_ids=[self.config.rule_ids.placeholder_requires_review],
            )
        return PolicyDecision(
            kind=PolicyDecisionKind.ALLOW,
            scope=self.config.default_scope,
            triggered_rule_ids=[self.config.rule_ids.placeholder_allow],
        )
