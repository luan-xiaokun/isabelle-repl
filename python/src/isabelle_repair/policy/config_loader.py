from __future__ import annotations

import tomllib
from pathlib import Path

from isabelle_repair.model import FailureKind, PolicyDecisionScope

from .config import (
    PlaceholderPolicyConfig,
    PlaceholderPolicyMode,
    PolicyConfig,
    PolicyRuleIds,
)

DEFAULT_POLICY_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "repair_policy.toml"
)


def load_policy_config(path: Path | None = None) -> PolicyConfig:
    resolved = (path or DEFAULT_POLICY_CONFIG_PATH).expanduser().resolve()
    try:
        raw = tomllib.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Policy config not found: {resolved}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML policy config at {resolved}: {exc}") from exc

    return parse_policy_config(raw, source=resolved)


def parse_policy_config(
    raw: dict[str, object], *, source: Path | None = None
) -> PolicyConfig:
    location = str(source) if source is not None else "<policy-config>"

    policy_section = _expect_table(raw, "policy", location)
    placeholder_section = _expect_table(raw, "placeholder", location)
    rule_ids_section = _expect_table(raw, "rule_ids", location)

    failure_values = _expect_list_of_strings(
        policy_section, "high_risk_failure_kinds", location
    )
    if not failure_values:
        raise ValueError(f"{location}: policy.high_risk_failure_kinds cannot be empty")
    high_risk_failure_kinds = {
        _parse_enum(
            FailureKind,
            value,
            f"{location}: policy.high_risk_failure_kinds contains invalid value",
        )
        for value in failure_values
    }
    default_scope = _parse_enum(
        PolicyDecisionScope,
        _expect_string(policy_section, "default_scope", location),
        f"{location}: policy.default_scope is invalid",
    )
    placeholder_mode = _parse_enum(
        PlaceholderPolicyMode,
        _expect_string(placeholder_section, "mode", location),
        f"{location}: placeholder.mode is invalid",
    )

    rule_ids = PolicyRuleIds(
        high_risk_failure_requires_review=_expect_string(
            rule_ids_section, "high_risk_failure_requires_review", location
        ),
        placeholder_allow=_expect_string(
            rule_ids_section, "placeholder_allow", location
        ),
        placeholder_deny=_expect_string(rule_ids_section, "placeholder_deny", location),
        placeholder_requires_review=_expect_string(
            rule_ids_section, "placeholder_requires_review", location
        ),
        fallback_acceptance_requires_review=_expect_string(
            rule_ids_section, "fallback_acceptance_requires_review", location
        ),
        fallback_continuation_requires_review=_expect_string(
            rule_ids_section, "fallback_continuation_requires_review", location
        ),
        default_allow=_expect_string(rule_ids_section, "default_allow", location),
    )
    _validate_rule_ids(rule_ids, location)

    return PolicyConfig(
        high_risk_failure_kinds=high_risk_failure_kinds,
        default_scope=default_scope,
        placeholder=PlaceholderPolicyConfig(mode=placeholder_mode),
        rule_ids=rule_ids,
    )


def _expect_table(raw: dict[str, object], key: str, location: str) -> dict[str, object]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{location}: missing or invalid [{key}] table")
    return value


def _expect_list_of_strings(
    table: dict[str, object], key: str, location: str
) -> list[str]:
    value = table.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{location}: {key} must be a list of strings")
    return value


def _expect_string(table: dict[str, object], key: str, location: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location}: {key} must be a non-empty string")
    return value.strip()


def _parse_enum(enum_cls, value: str, error_prefix: str):
    try:
        return enum_cls(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_cls)
        raise ValueError(f"{error_prefix}: {value!r}. Allowed: {allowed}") from exc


def _validate_rule_ids(rule_ids: PolicyRuleIds, location: str) -> None:
    values = [
        rule_ids.high_risk_failure_requires_review,
        rule_ids.placeholder_allow,
        rule_ids.placeholder_deny,
        rule_ids.placeholder_requires_review,
        rule_ids.fallback_acceptance_requires_review,
        rule_ids.fallback_continuation_requires_review,
        rule_ids.default_allow,
    ]
    if len(values) != len(set(values)):
        raise ValueError(f"{location}: rule_ids values must be unique")
