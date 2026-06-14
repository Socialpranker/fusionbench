from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Verdict:
    passed: bool
    score: float  # 0..1; binary graders use 1.0/0.0
    detail: str = ""


@runtime_checkable
class Grader(Protocol):
    name: str  # versioned, e.g. "ExactMatch@1"

    def score(self, prediction: str, reference: Any, metadata: dict) -> Verdict: ...
