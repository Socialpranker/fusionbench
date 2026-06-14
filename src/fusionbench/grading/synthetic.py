from __future__ import annotations

from typing import Any

from ..scoring import normalize
from .base import Verdict


class SyntheticGrader:
    """Synthetic suites (RULER): the reference is an exact generated needle. Credit when
    the normalized needle appears in the answer — no aliases, no numeric fallback, since
    synthetic targets are deterministic."""

    name = "Synthetic@1"

    def score(self, prediction: str, reference: Any, metadata: dict) -> Verdict:
        needle = normalize(str(reference))
        ans = normalize(prediction)
        ok = bool(needle) and needle in ans
        return Verdict(passed=ok, score=1.0 if ok else 0.0)
