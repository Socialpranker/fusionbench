from __future__ import annotations

from ..grading.constraint import Constraint
from .base import Example


def _exactly_words(n: int) -> Constraint:
    return Constraint(f"exactly {n} words", lambda p, n=n: len(p.split()) == n)


def _contains(word: str) -> Constraint:
    return Constraint(f"contains '{word}'", lambda p, w=word: w.lower() in p.lower())


def _all_caps() -> Constraint:
    return Constraint("all uppercase", lambda p: p.strip() == p.strip().upper() and any(c.isalpha() for c in p))


_TEMPLATES = [
    ("Reply with exactly three words mentioning a cat.", [_exactly_words(3), _contains("cat")]),
    ("Answer in all capital letters.", [_all_caps()]),
    ("Write exactly five words and include the word ocean.", [_exactly_words(5), _contains("ocean")]),
]


class IFBenchLoader:
    """Instruction-following fixture: each example carries verifiable Constraints as its
    reference (not a gold string), graded by ConstraintGrader."""

    type = "instruction"

    def load(self, limit: int, split: str = "test") -> list[Example]:
        out = []
        for i in range(limit):
            prompt, constraints = _TEMPLATES[i % len(_TEMPLATES)]
            out.append(Example(id=f"ifbench-{i:04d}", prompt=prompt, reference=constraints, type=self.type))
        return out
