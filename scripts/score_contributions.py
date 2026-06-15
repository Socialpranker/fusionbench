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
            # JSON is UTF-8 per RFC 8259; pin it so a non-UTF-8 CI locale can't
            # mis-decode (UnicodeDecodeError is also caught here, so it skips
            # rather than crashing).
            out.append(json.loads(mf.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f"WARN: skipping {mf}: {e}", file=sys.stderr)
    return out


LEADERBOARD_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FusionBench — leaderboard</title>
<style>
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#111827;background:#f8fafc;margin:0;line-height:1.55}
.wrap{max-width:880px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:26px;font-weight:600;margin:0 0 4px}
.sub{color:#6b7280;margin:0 0 24px}
.nav{margin:0 0 20px;font-size:14px}
.nav a{color:#0d9488;text-decoration:none}
table{width:100%;border-collapse:collapse;font-size:14px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #f1f5f9}
th{background:#f8fafc;color:#6b7280;font-weight:600;font-size:12.5px;text-transform:uppercase;letter-spacing:.03em}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.bar-wrap{background:#f1f5f9;border-radius:999px;height:8px;overflow:hidden;min-width:80px}
.bar-fill{display:block;height:100%;background:#0d9488}
.foot{color:#9ca3af;font-size:12.5px;margin-top:40px;border-top:1px solid #e5e7eb;padding-top:14px}
@media (prefers-color-scheme: dark){
  body{background:#0f1419;color:#e5e7eb}
  .sub,.foot{color:#9ca3af}
  table{background:#1a1f2e;border-color:#374151}
  th{background:#161b26;color:#9ca3af}
  th,td{border-color:#374151}
  .bar-wrap{background:#374151}
}
</style></head><body><div class="wrap">
<div class="nav"><a href="index.html">← Catalog</a></div>
<h1>Contributor leaderboard</h1>
<p class="sub">Points for verified contributions. Repeat cells decay (log). Relative ranking.</p>
<div id="board"></div>
<p class="foot" id="foot"></p>
<script src="leaderboard.js"></script>
</div></body></html>
"""


def render_leaderboard_html():
    return LEADERBOARD_PAGE


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
    out_json.write_text(json.dumps(lb, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    out_html = Path(args.out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(render_leaderboard_html(), encoding="utf-8")  # template added in Task 4
    print(f"wrote {args.out_json} ({len(lb['contributors'])} contributors) and {args.out_html}")


if __name__ == "__main__":
    main()
