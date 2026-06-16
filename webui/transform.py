"""Pure catalog transforms for the Gradio showcase: filter, sort, to-DataFrame.

No Gradio import here — everything is testable as plain functions.
"""
from __future__ import annotations

_SORT_KEYS = {
    "worthiness": ("worthiness_vs_best", True),
    "accuracy": ("accuracy", True),
    "cost": ("cost_usd", False),
    "recipe": ("recipe", False),
}


def filter_catalog(cells, type, maxcost, minacc, sort):
    """Filter catalog cells by type/maxcost/minacc, then sort.

    `type=""` means all types. Nulls in the sort key land last, deterministically.
    """
    rows = [
        c for c in cells
        if (not type or c.get("type") == type)
        and (c.get("cost_usd") is None or c["cost_usd"] <= maxcost)
        and (c.get("accuracy") is None or c["accuracy"] >= minacc)
    ]
    key_name, reverse = _SORT_KEYS.get(sort, _SORT_KEYS["worthiness"])

    def sort_key(c):
        v = c.get(key_name)
        missing = v is None
        # missing always sorts last regardless of direction; strings compare as-is.
        if isinstance(v, str):
            return (missing, v)
        return (missing, -(v or 0.0) if reverse else (v or 0.0))

    return sorted(rows, key=sort_key)
