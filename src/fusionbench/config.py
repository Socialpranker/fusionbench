"""Core data types: models, recipes, results."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class ModelSpec:
    """A model addressable through OpenRouter, plus pricing for cost accounting."""
    slug: str                 # OpenRouter slug, e.g. "google/gemini-3-flash"
    label: str                # short display name
    family: str               # used to forbid a model judging its own family
    price_in: float = 0.0     # USD per 1M input tokens
    price_out: float = 0.0    # USD per 1M output tokens


ArmType = str  # "best_single" | "self_moa" | "fusion" | "source_pool"


@dataclass(frozen=True)
class RecipeConfig:
    """One configuration under test = one row of the eventual catalog."""
    name: str
    arm: ArmType
    panel: tuple[str, ...] = ()      # model slugs answering in parallel (fusion / source_pool)
    judge: str | None = None         # judge model slug (fusion)
    synth: str | None = None         # synthesizer / final model slug
    single: str | None = None        # the one model (best_single / self_moa / source_pool target)
    n_samples: int = 1               # self_moa sample count (set by matched-budget)
    topology: str = "single"         # "single" | "self_moa" | "panel_judge_synth" | "source_pool"


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens


@dataclass
class ArmResult:
    """Outcome of running one recipe on one task."""
    recipe: str
    arm: ArmType
    answer: str
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    latency_s: float = 0.0
    panel_answers: dict[str, str] = field(default_factory=dict)  # model_slug -> answer
    judge: dict[str, Any] | None = None
    correct: bool | None = None

    def to_record(self) -> dict[str, Any]:
        d = asdict(self)
        d["tokens"] = self.usage.total
        return d
