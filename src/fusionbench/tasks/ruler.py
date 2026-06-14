from __future__ import annotations

import string

from .base import Example


def _needle(i: int) -> str:
    word = "".join(string.ascii_uppercase[(i // (26**k)) % 26] for k in range(3))
    return f"NEEDLE-{word}"


class RulerLoader:
    """RULER-style needle-in-haystack. Synthetic by construction (contamination-proof),
    so the same generator serves both mock and real runs in phase 1."""

    type = "long_context"

    def load(self, limit: int, split: str = "test") -> list[Example]:
        out = []
        for i in range(limit):
            needle = _needle(i)
            haystack = " ".join(f"line {j} of filler text." for j in range(20))
            prompt = (
                f"{haystack}\nThe special token is {needle}.\n{haystack}\n"
                "Question: what is the special token? Answer with the token only."
            )
            out.append(Example(id=f"ruler-{i:04d}", prompt=prompt, reference=needle, type=self.type))
        return out
