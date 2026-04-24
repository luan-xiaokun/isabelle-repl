from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from isabelle_repair.model import InterventionContext, InterventionResponse


@dataclass
class StaticReviewHook:
    """
    Hook adapter that returns a deterministic response or delegates to callback.
    """

    response_factory: (
        InterventionResponse | Callable[[InterventionContext], InterventionResponse]
    )

    def handle(self, context: InterventionContext) -> InterventionResponse:
        if callable(self.response_factory):
            return self.response_factory(context)
        return self.response_factory
