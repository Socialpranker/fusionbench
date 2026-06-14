from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .base import Verdict


@dataclass(frozen=True)
class Constraint:
    """One checkable instruction-following rule. `describe_text` surfaces in the verdict
    so a failed submission shows *which* rule broke, not just a fraction."""

    describe_text: str
    predicate: Callable[[str], bool]

    def check(self, prediction: str) -> bool:
        return self.predicate(prediction)

    def describe(self) -> str:
        return self.describe_text


class ConstraintGrader:
    """IFBench-style: score = fraction of constraints satisfied; passed only if all are."""

    name = "Constraint@1"

    def score(self, prediction: str, reference: Any, metadata: dict) -> Verdict:
        constraints: list[Constraint] = list(reference or [])
        if not constraints:
            return Verdict(passed=True, score=1.0, detail="no constraints")

        failed = [c for c in constraints if not c.check(prediction)]
        score = (len(constraints) - len(failed)) / len(constraints)
        detail = "" if not failed else "failed: " + "; ".join(c.describe() for c in failed)
        return Verdict(passed=not failed, score=round(score, 4), detail=detail)
