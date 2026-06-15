from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Example:
    id: str
    prompt: str
    reference: Any  # shape depends on the grader: str, or list[Constraint] for instruction
    type: str
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class Loader(Protocol):
    def load(self, limit: int, split: str = "test") -> list[Example]: ...
