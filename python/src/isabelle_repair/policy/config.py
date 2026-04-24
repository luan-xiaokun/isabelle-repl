from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from isabelle_repair.model import FailureKind, PolicyDecisionScope


class PlaceholderPolicyMode(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_REVIEW = "requires_review"


@dataclass(frozen=True)
class PolicyRuleIds:
    high_risk_failure_requires_review: str = "high_risk_failure_requires_review"
    placeholder_allow: str = "placeholder_allow"
    placeholder_deny: str = "placeholder_deny"
    placeholder_requires_review: str = "placeholder_requires_review"
    fallback_acceptance_requires_review: str = "fallback_acceptance_requires_review"
    fallback_continuation_requires_review: str = "fallback_continuation_requires_review"
    default_allow: str = "default_allow"


@dataclass(frozen=True)
class PlaceholderPolicyConfig:
    mode: PlaceholderPolicyMode = PlaceholderPolicyMode.ALLOW


@dataclass(frozen=True)
class PolicyConfig:
    high_risk_failure_kinds: set[FailureKind] = field(
        default_factory=lambda: {
            FailureKind.STATEMENT_FAILURE,
            FailureKind.NON_PROOF_COMMAND_FAILURE,
            FailureKind.THEORY_LOAD_OR_HEADER_FAILURE,
        }
    )
    default_scope: PolicyDecisionScope = PolicyDecisionScope.ARTIFACT_ACCEPTANCE
    placeholder: PlaceholderPolicyConfig = field(
        default_factory=PlaceholderPolicyConfig
    )
    rule_ids: PolicyRuleIds = field(default_factory=PolicyRuleIds)
