from __future__ import annotations

from dataclasses import dataclass

from isabelle_repair.model import (
    InterventionContext,
    InterventionResponse,
    InterventionResponseKind,
)


@dataclass(frozen=True)
class HookValidationResult:
    response: InterventionResponse
    invalid_response_reason: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.invalid_response_reason is None


def validate_intervention_response(
    context: InterventionContext,
    response: InterventionResponse,
) -> HookValidationResult:
    allowed = set(context.allowed_response_kinds)
    if response.kind not in allowed:
        allowed_values = ",".join(kind.value for kind in allowed)
        return _invalid(
            response,
            f"response_not_allowed:{response.kind.value};allowed={allowed_values}",
        )

    if (
        response.kind == InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT
        and not response.replacement_artifact_text
    ):
        return _invalid(response, "replacement_artifact_text_missing")

    return HookValidationResult(response=response)


def _invalid(
    response: InterventionResponse,
    reason: str,
) -> HookValidationResult:
    return HookValidationResult(
        response=InterventionResponse(
            kind=InterventionResponseKind.REJECT_CURRENT_ARTIFACT,
            metadata={
                "invalid_response_reason": reason,
                "original_response_kind": response.kind.value,
            },
        ),
        invalid_response_reason=reason,
    )
