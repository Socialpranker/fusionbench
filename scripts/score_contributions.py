#!/usr/bin/env python3
"""Score crowdsourced contributions into a relative leaderboard.

Pure core: score_contributions(submissions, now) -> leaderboard dict.
I/O wrapper (read submissions/*/manifest.json, write site/leaderboard.json + .html)
is added in a later task. Verify-before-score: a manifest present under submissions/
on main has already passed regrade (submit.yml required check) — we do NOT re-grade.
"""
import argparse
import json
import sys
from pathlib import Path

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
    # deterministic order: by run_id (lexicographic). `or ""` normalises both a
    # missing key and an explicit null/empty run_id to "" so decay is stable.
    valid.sort(key=lambda m: str(m.get("run_id") or ""))

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


def load_submissions(submissions_dir):
    """Read every submissions/<user>/<run_id>/manifest.json. Malformed/unreadable
    manifests are skipped with a warning (not fatal). Absent dir -> []."""
    root = Path(submissions_dir)
    out = []
    if not root.is_dir():
        return out
    for mf in sorted(root.glob("*/*/manifest.json")):
        try:
            out.append(json.loads(mf.read_text()))
        except (OSError, json.JSONDecodeError) as e:
            print(f"WARN: skipping {mf}: {e}", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--submissions", default="submissions", help="submissions root dir")
    ap.add_argument("--out-json", default="site/leaderboard.json")
    ap.add_argument("--out-html", default="site/leaderboard.html")
    ap.add_argument("--now", required=True, help="ISO date for 'updated' field (e.g. CI date)")
    args = ap.parse_args()

    subs = load_submissions(args.submissions)
    lb = score_contributions(subs, now=args.now)

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(lb, ensure_ascii=False, indent=2) + "\n")

    Path(args.out_html).write_text(render_leaderboard_html())   # template added in Task 4
    print(f"wrote {args.out_json} ({len(lb['contributors'])} contributors) and {args.out_html}")


if __name__ == "__main__":
    main()


def render_leaderboard_html():
    return ""   # replaced in Task 4 with the real template
