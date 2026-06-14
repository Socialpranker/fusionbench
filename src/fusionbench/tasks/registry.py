from __future__ import annotations

from dataclasses import dataclass

from ..grading.base import Grader
from ..grading.constraint import ConstraintGrader
from ..grading.exact import ExactMatchGrader
from ..grading.synthetic import SyntheticGrader
from .base import Loader
from .frames import FramesLoader
from .ifbench import IFBenchLoader
from .ruler import RulerLoader


@dataclass(frozen=True)
class TaskSpec:
    type: str
    loader: Loader
    grader: Grader
    license: str
    contamination_policy: str  # "synthetic" | "time-windowed" | "static-risk"


# Keyed by CLI suite name. The task `type` (used in outputs.jsonl and catalog grouping)
# lives inside the spec, so "ruler" maps to type "long_context" without ambiguity.
REGISTRY: dict[str, TaskSpec] = {
    "frames": TaskSpec("multihop_qa", FramesLoader(), ExactMatchGrader(), "Apache-2.0", "static-risk"),
    "ruler": TaskSpec("long_context", RulerLoader(), SyntheticGrader(), "Apache-2.0", "synthetic"),
    "ifbench": TaskSpec("instruction", IFBenchLoader(), ConstraintGrader(), "Apache-2.0", "static-risk"),
}
