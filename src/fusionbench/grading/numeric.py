from __future__ import annotations

import re
from typing import Any

from .base import Verdict

_BOXED = re.compile(r"\\boxed\{([^}]*)\}")
_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_TOL = 1e-6


def _last_number(text: str) -> float | None:
    boxed = _BOXED.findall(text or "")
    candidates = boxed if boxed else _NUM.findall(text or "")
    for raw in reversed(candidates):
        m = _NUM.search(raw)
        if m:
            return float(m.group().replace(",", ""))
    return None


def _symbolically_equal(prediction: str, reference: str) -> bool | None:
    """None when SymPy is unavailable or can't parse — caller falls back to numeric."""
    try:
        from sympy import simplify
        from sympy.parsing.sympy_parser import parse_expr
    except ImportError:
        return None
    try:
        return bool(simplify(parse_expr(prediction) - parse_expr(reference)) == 0)
    except (SyntaxError, TypeError, ValueError):
        return None


class NumericGrader:
    """Math answers: boxed/last number with tolerance, plus optional SymPy equivalence
    (e.g. 1/2 == 0.5) when sympy is installed."""

    name = "Numeric@1"

    def score(self, prediction: str, reference: Any, metadata: dict) -> Verdict:
        ref = str(reference)
        symbolic = _symbolically_equal(prediction, ref)
        if symbolic:
            return Verdict(passed=True, score=1.0, detail="sympy")

        pred_num = _last_number(prediction)
        ref_num = _last_number(ref)
        if pred_num is None:
            return Verdict(passed=False, score=0.0, detail="no number in prediction")
        if ref_num is None:
            return Verdict(passed=False, score=0.0, detail="no number in reference")

        ok = abs(pred_num - ref_num) <= _TOL
        return Verdict(passed=ok, score=1.0 if ok else 0.0)
