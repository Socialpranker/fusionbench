from __future__ import annotations

from ..grading.constraint import make_constraint
from .base import Example

# Templates described as DATA so each constraint serializes to gold and round-trips.
# Each entry: (prompt, [(kind, params), ...]).
_TEMPLATES = [
    ("Reply with exactly three words mentioning a cat.",
     [("exactly_words", {"n": 3}), ("contains", {"word": "cat"})]),
    ("Answer in all capital letters.",
     [("all_caps", {})]),
    ("Write exactly five words and include the word ocean.",
     [("exactly_words", {"n": 5}), ("contains", {"word": "ocean"})]),
]


class IFBenchLoader:
    """Instruction-following fixture: each example carries verifiable Constraints as its
    reference (not a gold string), graded by ConstraintGrader. Constraints are built from
    registered kinds so they serialize to gold for CI re-grade."""

    type = "instruction"

    def load(self, limit: int, split: str = "test") -> list[Example]:
        out = []
        for i in range(limit):
            prompt, specs = _TEMPLATES[i % len(_TEMPLATES)]
            constraints = [make_constraint(kind, **params) for kind, params in specs]
            out.append(Example(id=f"ifbench-{i:04d}", prompt=prompt, reference=constraints, type=self.type))
        return out
