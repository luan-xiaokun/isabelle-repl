from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from isabelle_repair.model import TaskSpec

from .generator import RuleFirstGenerator


class CandidateSource(Protocol):
    source_name: str

    def candidates(self, task_spec: TaskSpec) -> list[str]:
        """Return ordered candidates to evaluate."""

    def source_metadata(self, task_spec: TaskSpec) -> dict[str, object]:
        """Return source-level metadata for audit/debug."""


@dataclass
class AutoCandidateSource:
    generator: RuleFirstGenerator
    allow_sledgehammer: bool = True
    source_name: str = "auto_rule_first"

    def candidates(self, task_spec: TaskSpec) -> list[str]:
        return self.generator.generate_candidates(
            task_spec,
            allow_sledgehammer=self.allow_sledgehammer,
        )

    def source_metadata(self, task_spec: TaskSpec) -> dict[str, object]:  # noqa: ARG002
        return {
            "allow_sledgehammer": self.allow_sledgehammer,
            "strategy": "rule_first",
        }


@dataclass
class ReviewCandidateSource:
    candidate_text: str
    source_name: str = "review_injected"

    def candidates(self, task_spec: TaskSpec) -> list[str]:  # noqa: ARG002
        return [self.candidate_text]

    def source_metadata(self, task_spec: TaskSpec) -> dict[str, object]:  # noqa: ARG002
        return {"strategy": "review_replacement"}
