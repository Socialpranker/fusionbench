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

# site_tokens.py lives next to this script; make sure it's importable when running
# directly (python scripts/score_contributions.py) as well as from pytest.
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from site_tokens import TOKENS_CSS  # noqa: E402

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


# LEADERBOARD_PAGE is assembled by _make_leaderboard_page() to safely embed TOKENS_CSS
# (which contains literal CSS curly braces) without breaking str.format().

_LB_HEAD = """\
<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600&family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet">
<title>FusionBench — leaderboard</title>
<style>
:root{color-scheme:light dark}
*{box-sizing:border-box}
"""

# TOKENS_CSS is injected here by _make_leaderboard_page()

_LB_CSS = """\
body{font-family:var(--fb-font-body);color:var(--fb-text);background:var(--fb-bg);margin:0;line-height:var(--fb-body-lh);font-size:var(--fb-body)}
.wrap{max-width:var(--fb-max-width);margin:0 auto;padding:40px 24px 80px}
.masthead{background:var(--fb-text);color:var(--fb-bg);border:var(--fb-border-w) solid var(--fb-border);padding:22px 24px;margin:0 0 8px}
.masthead .eyebrow{font-family:var(--fb-font-mono);font-size:var(--fb-label);letter-spacing:0.12em;text-transform:uppercase;color:var(--fb-accent);margin:0 0 8px}
h1{font-family:var(--fb-font-mono);font-size:var(--fb-h1);line-height:var(--fb-h1-lh);font-weight:700;letter-spacing:-0.02em;margin:0}
.masthead h1{color:var(--fb-bg)}
.sub{color:var(--fb-text-muted);margin:14px 0 24px;max-width:64ch}
.nav{margin:0 0 14px;font-family:var(--fb-font-mono);font-size:var(--fb-small)}
.nav a{color:var(--fb-accent);text-decoration:none}
table{width:100%;border-collapse:collapse;font-size:var(--fb-body);background:var(--fb-surface);border:var(--fb-border-w) solid var(--fb-border);border-radius:var(--fb-radius)}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--fb-border-faint)}
th{background:var(--fb-surface-2-light);color:var(--fb-text-muted);font-family:var(--fb-font-mono);font-size:var(--fb-label);font-weight:var(--fb-label-weight);text-transform:var(--fb-label-transform);letter-spacing:var(--fb-label-tracking);border-bottom:var(--fb-border-w) solid var(--fb-border)}
td.num{text-align:right;font-family:var(--fb-font-mono);font-feature-settings:var(--fb-num-features)}
.bar-wrap{background:var(--fb-surface-2-light);border:1px solid var(--fb-border);border-radius:var(--fb-radius);height:10px;overflow:hidden;min-width:80px}
.bar-fill{display:block;height:100%;background:var(--fb-accent)}
.foot{color:var(--fb-text-faint);font-family:var(--fb-font-mono);font-size:var(--fb-label);margin-top:40px;border-top:var(--fb-border-w) solid var(--fb-border);padding-top:14px}
@media (prefers-color-scheme: dark){
  .masthead{background:var(--fb-surface-2);color:var(--fb-text)}
  .masthead h1{color:var(--fb-text)}
  table{background:var(--fb-surface);border-color:var(--fb-border)}
  th{background:var(--fb-surface-2-light)}
  th,td{border-color:var(--fb-border-faint)}
}
"""

_LB_TAIL = """\
</style></head><body><div class="wrap">
<div class="nav"><a href="index.html">▸ ← catalog</a></div>
<div class="masthead">
  <p class="eyebrow">▸ fusionbench / leaderboard</p>
  <h1>Contributor leaderboard</h1>
</div>
<p class="sub">Points for verified contributions. Repeat cells decay (log). Relative ranking.</p>
<div id="board"></div>
<p class="foot" id="foot"></p>
<script src="leaderboard.js"></script>
</div></body></html>
"""


def _make_leaderboard_page() -> str:
    """Assemble leaderboard HTML, injecting TOKENS_CSS safely (no .format collision)."""
    return _LB_HEAD + TOKENS_CSS + _LB_CSS + _LB_TAIL


def render_leaderboard_html():
    return _make_leaderboard_page()


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
    out_html.write_text(render_leaderboard_html(), encoding="utf-8")
    print(f"wrote {args.out_json} ({len(lb['contributors'])} contributors) and {args.out_html}")


if __name__ == "__main__":
    main()
