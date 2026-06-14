# src/fusionbench/gold.py
"""Serialize a loader's Example into the gold-file row CI re-grades against, and back.

This is the single boundary between Example/Constraint objects and the JSON gold file.
String-reference suites (frames, ruler) pass through; the instruction suite (ifbench)
carries a list of constraints whose predicates are lambdas — those round-trip through
the constraint registry, not raw JSON.
"""
from __future__ import annotations

from typing import Any

from .grading.constraint import Constraint, constraint_from_dict, constraint_to_dict
from .tasks.base import Example

# Suites whose grader reference is a list[Constraint] rather than a plain string.
# Invariant: a suite belongs here iff its loader's reference is list[Constraint].
# example_to_gold auto-detects by isinstance; gold_to_reference decides by this set —
# the two detection paths must stay in agreement (keep in sync when adding a suite).
_CONSTRAINT_SUITES = {"ifbench"}


def example_to_gold(ex: Example) -> dict[str, Any]:
    """Dump an Example to a JSON-serializable gold row: {id, type, reference, metadata}."""
    ref = ex.reference
    if isinstance(ref, list) and all(isinstance(c, Constraint) for c in ref):
        reference: Any = [constraint_to_dict(c) for c in ref]
    else:
        reference = ref
    return {
        "id": ex.id,
        "type": ex.type,
        "reference": reference,
        "metadata": dict(ex.metadata),
    }


def gold_to_reference(suite: str, row: dict[str, Any]) -> tuple[Any, dict]:
    """Rebuild (reference, metadata) for grader.score() from a gold row."""
    metadata = dict(row.get("metadata", {}))
    if suite in _CONSTRAINT_SUITES:
        reference: Any = [constraint_from_dict(d) for d in row["reference"]]
    else:
        reference = row["reference"]
    return reference, metadata
