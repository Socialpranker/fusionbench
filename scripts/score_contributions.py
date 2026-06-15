#!/usr/bin/env python3
"""Score crowdsourced contributions into a relative leaderboard.

Pure core: score_contributions(submissions, now) -> leaderboard dict.
I/O wrapper (read submissions/*/manifest.json, write site/leaderboard.json + .html)
is added in a later task. Verify-before-score: a manifest present under submissions/
on main has already passed regrade (submit.yml required check) — we do NOT re-grade.
"""
import sys

WEIGHT_CELL = 20  # proposal §4.1 — points for a new verified (recipe × suite) cell


def _valid(man):
    if not isinstance(man, dict):
        return False
    if not man.get("submitted_by") or not man.get("suite"):
        return False
    claimed = man.get("claimed")
    return isinstance(claimed, dict) and bool(claimed.get("recipe"))


def _cell_key(man):
    return man["suite"] + "×" + man["claimed"]["recipe"]


def score_contributions(submissions, now):
    """submissions: iterable of manifest dicts. now: ISO date string (caller-supplied,
    not generated here — keeps output deterministic for tests). Returns leaderboard dict."""
    valid = [m for m in submissions if _valid(m)]
    # deterministic order: by run_id (lexicographic), fallback "" so decay is stable
    valid.sort(key=lambda m: str(m.get("run_id", "")))

    seen_cell = {}                       # cell_key -> how many prior submissions of that cell
    by_user = {}                         # user -> {"points": float, "verified": int, "cells": set}
    for m in valid:
        cell = _cell_key(m)
        prior = seen_cell.get(cell, 0)
        pts = WEIGHT_CELL * (0.5 ** prior)
        seen_cell[cell] = prior + 1
        u = by_user.setdefault(m["submitted_by"],
                               {"points": 0.0, "verified": 0, "cells": set()})
        u["points"] += pts
        u["verified"] += 1
        u["cells"].add(cell)

    contributors = [
        {"user": user, "points": round(d["points"], 2),
         "verified": d["verified"], "cells": sorted(d["cells"])}
        for user, d in by_user.items()
    ]
    # sort: points desc, then user asc (deterministic tie-break)
    contributors.sort(key=lambda c: (-c["points"], c["user"]))
    return {"updated": now, "contributors": contributors}
