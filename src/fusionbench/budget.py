"""Token accounting and matched-budget logic.

The headline control of v0 is *matched compute*: self-moa's sample count N is set so
its token spend ~ the fusion arm's token spend. Otherwise "fusion beats one model"
just means "we spent more".
"""
from __future__ import annotations

from .config import ModelSpec, Usage


def estimate_tokens(text: str) -> int:
    """Cheap heuristic when an API doesn't return usage (~4 chars/token)."""
    return max(1, len(text) // 4)


def cost_usd(usage: Usage, spec: ModelSpec) -> float:
    return usage.prompt_tokens / 1e6 * spec.price_in + usage.completion_tokens / 1e6 * spec.price_out


def n_for_budget(target_tokens: int, per_sample_tokens: int) -> int:
    """How many self-moa samples fit a target token budget."""
    if per_sample_tokens <= 0:
        return 1
    return max(1, round(target_tokens / per_sample_tokens))


class Ledger:
    """Accumulates tokens and USD per recipe across a run."""

    def __init__(self) -> None:
        self.tokens: dict[str, int] = {}
        self.cost: dict[str, float] = {}

    def add(self, recipe: str, usage: Usage, cost: float) -> None:
        self.tokens[recipe] = self.tokens.get(recipe, 0) + usage.total
        self.cost[recipe] = self.cost.get(recipe, 0.0) + cost

    def mean(self, recipe: str, n: int) -> tuple[float, float]:
        n = max(1, n)
        return self.tokens.get(recipe, 0) / n, self.cost.get(recipe, 0.0) / n
