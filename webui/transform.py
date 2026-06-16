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


_LEADERBOARD_HEADERS = ["#", "user", "points", "verified", "cells"]
_CATALOG_HEADERS = ["type", "recipe", "arm", "accuracy", "cost_usd",
                    "worthiness_vs_best", "complementarity", "n"]


def to_leaderboard_df(leaderboard):
    """(headers, rows) for the leaderboard Dataframe. Rank = 1-based row index."""
    rows = []
    for i, c in enumerate(leaderboard.get("contributors", []), start=1):
        rows.append([i, c.get("user", ""), c.get("points", 0.0),
                     c.get("verified", 0), ", ".join(c.get("cells", []))])
    return _LEADERBOARD_HEADERS, rows


def to_catalog_df(cells):
    """(headers, rows) for the catalog Dataframe, in fixed column order."""
    rows = [[c.get("type"), c.get("recipe"), c.get("arm"), c.get("accuracy"),
             c.get("cost_usd"), c.get("worthiness_vs_best"),
             c.get("complementarity"), c.get("n")] for c in cells]
    return _CATALOG_HEADERS, rows


def slider_bounds(cells):
    """Safe slider ranges from data: maxcost = max observed cost (or 1.0), minacc = 0.0."""
    costs = [c["cost_usd"] for c in cells if c.get("cost_usd") is not None]
    return {"maxcost": max(costs) if costs else 1.0, "minacc": 0.0}
