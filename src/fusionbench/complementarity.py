"""The prefilter — the thing that makes the catalog cheap to maintain.

Mixing models only beats the best single one when their errors DECORRELATE.
These are pure functions over per-model correctness vectors (booleans on a probe
slice), so they're cheap and unit-testable. They need a small *labeled* probe set
today; a label-free predictor for generation is the open research stretch.

Refs: focal diversity (LLM-TOPLA), error-correlation / mRMR ensemble selection.
"""
from __future__ import annotations

from itertools import combinations

Correctness = dict[str, list[bool]]


def error_jaccard(a: list[bool], b: list[bool]) -> float:
    """Overlap of errors: both_wrong / either_wrong. High = redundant errors."""
    both = sum(1 for x, y in zip(a, b) if not x and not y)
    either = sum(1 for x, y in zip(a, b) if not x or not y)
    return both / either if either else 0.0


def pair_complementarity(a: list[bool], b: list[bool]) -> float:
    """1 - error overlap. High = the two models fail on different items."""
    return 1.0 - error_jaccard(a, b)


def focal_diversity(correctness: Correctness, panel: tuple[str, ...]) -> float:
    """Avg over focal models of: on the items the focal gets wrong, how often does
    at least one teammate get it right (i.e. the error is recoverable)."""
    scores = []
    for focal in panel:
        errs = [i for i, ok in enumerate(correctness[focal]) if not ok]
        if not errs:
            continue
        others = [m for m in panel if m != focal]
        recov = sum(1 for i in errs if any(correctness[m][i] for m in others))
        scores.append(recov / len(errs))
    return sum(scores) / len(scores) if scores else 0.0


def panel_complementarity(correctness: Correctness, panel: tuple[str, ...]) -> float:
    """Mean pairwise complementarity across the panel."""
    pairs = list(combinations(panel, 2))
    if not pairs:
        return 0.0
    return sum(pair_complementarity(correctness[a], correctness[b]) for a, b in pairs) / len(pairs)


def oracle_coverage(correctness: Correctness, panel: tuple[str, ...]) -> float:
    """Fraction of items at least one panel member gets right = the ceiling a perfect
    judge could reach. Gap to best-single is the *potential* fusion headroom."""
    n = len(next(iter(correctness.values()))) if correctness else 0
    if not n:
        return 0.0
    return sum(1 for i in range(n) if any(correctness[m][i] for m in panel)) / n


def prefilter_panels(candidates: list[tuple[str, ...]], correctness: Correctness,
                     k: int = 3) -> list[tuple[tuple[str, ...], float]]:
    """Rank candidate panels by complementarity, return top-k (panel, score).
    This is what prunes the search so only a few configs get a full (paid) eval."""
    scored = [(p, panel_complementarity(correctness, p)) for p in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]
