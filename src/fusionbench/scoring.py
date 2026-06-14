"""Verifiable grading for short-answer suites (BrowseComp / FRAMES style).

v0 deliberately uses only verifiable grading — no LLM judge in the scoring path —
so the headline result is unarguable. Supports gold aliases and numeric tolerance.
Known limit: answers needing true semantic equivalence are under-credited; that's an
accepted v0 tradeoff (rubric/judge grading is a v1 addition, with self-family exclusion).
"""
from __future__ import annotations

import re

_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")  # comma = thousands separator (benchmark convention)


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _nums(s: str) -> set[float]:
    out = set()
    for m in _NUM.findall(s or ""):
        try:
            out.add(round(float(m.replace(",", "")), 4))
        except ValueError:
            pass
    return out


def is_correct(answer: str, gold: str, aliases: list[str] | None = None) -> bool:
    a = normalize(answer)
    golds = [gold, *(aliases or [])]

    for g in golds:
        gn = normalize(g)
        if gn and (a == gn or gn in a):
            return True

    # numeric fallback: credit if a gold number appears in the answer
    ans_nums = _nums(answer)
    if ans_nums:
        for g in golds:
            if _nums(g) & ans_nums:
                return True
    return False
