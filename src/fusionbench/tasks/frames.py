from __future__ import annotations

from .base import Example
from .loaders import load_frames


class FramesLoader:
    """FRAMES multi-hop QA. Live load goes through HuggingFace (load_frames); the --mock
    path is handled by the caller, which substitutes synthetic probes instead of calling
    this, so importing `datasets` is never required for a mock run."""

    type = "multihop_qa"

    def load(self, limit: int, split: str = "test") -> list[Example]:
        return [
            Example(
                id=row["id"],
                prompt=row["question"],
                reference=row["gold"],
                type=self.type,
                metadata={"aliases": row.get("aliases", [])},
            )
            for row in load_frames(limit, split)
        ]
