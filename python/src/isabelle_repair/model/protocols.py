from __future__ import annotations

from typing import Any, Protocol

from .types import (
    InterventionContext,
    InterventionResponse,
    LocalizedTask,
    PolicyContext,
    PolicyDecision,
    RunRecord,
    RunRecordKind,
    TaskResult,
    TaskSpec,
    ValidationResult,
)


class Localizer(Protocol):
    def next_task(
        self,
        theory_run_id: str,
        snapshot: Any | None = None,
    ) -> LocalizedTask | None:
        """Return the next localized task or None when no failure remains."""


class TaskEngine(Protocol):
    def run(self, task_spec: TaskSpec) -> TaskResult:
        """Run one task and return outcome/artifact summary."""

    def validate_candidate(
        self, task_spec: TaskSpec, candidate_text: str
    ) -> ValidationResult:
        """Validate a replacement candidate supplied by hook/intervention."""


class PolicyGate(Protocol):
    def decide(self, context: PolicyContext) -> PolicyDecision:
        """Return allow/deny/requires_review policy decision."""


class ReviewHook(Protocol):
    def handle(self, context: InterventionContext) -> InterventionResponse:
        """Resolve external review with structured response."""


class RecordStore(Protocol):
    def append(self, record: RunRecord) -> None:
        """Append one run-level record."""


class RecordFactory(Protocol):
    def create(
        self,
        record_kind: RunRecordKind,
        task_id: str | None,
        payload: dict[str, object],
    ) -> RunRecord:
        """Create one run-level record with sequence metadata."""
