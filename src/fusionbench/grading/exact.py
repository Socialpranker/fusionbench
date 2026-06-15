from __future__ import annotations

from typing import Any

from ..scoring import is_correct
from .base import Verdict


class ExactMatchGrader:
    """Normalized exact / substring / alias match. Wraps scoring.is_correct so the
    v0 grading rule and the versioned grader stay one implementation."""

    name = "ExactMatch@1"

    def score(self, prediction: str, reference: Any, metadata: dict) -> Verdict:
        aliases = metadata.get("aliases") if metadata else None
        ok = is_correct(prediction, str(reference), aliases)
        return Verdict(passed=ok, score=1.0 if ok else 0.0)
