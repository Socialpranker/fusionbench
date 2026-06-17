#!/usr/bin/env python3
"""Build the public catalog site from runs/*.jsonl.

A single self-contained site/index.html (no external deps): per-task-type recipe
table, an inline-SVG cost-quality Pareto, and complementarity-by-type bars.

    python scripts/build_catalog.py                       # runs/*.jsonl -> site/index.html
    python scripts/build_catalog.py --runs runs/catalog.jsonl --out site/index.html
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# site_tokens.py lives next to this script; make sure it's importable when running
# directly (python scripts/build_catalog.py) as well as from pytest (sys.path already set).
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from site_tokens import TOKENS_CSS  # noqa: E402

# Kept in sync (by hand) with the --fb-arm-* token values in site_tokens.py — used by the
# static <noscript> SVG scatter only; the live ECharts views read the CSS vars directly.
ARM_COLOR = {
    "best_single": "#8a8276", "self_moa": "#3b6ea5",
    "fusion": "#ff5b04", "source_pool": "#7a4fb5",
}


def load_rows(patterns: list[str]) -> list[dict]:
    rows = []
    for pat in patterns:
        for fp in glob.glob(pat):
            for ln in Path(fp).read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    rows.append(json.loads(ln))
    return rows


def dedupe(rows: list[dict]) -> list[dict]:
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r.get("suite"), r["task_type"], r["recipe"])
        if key not in best or r.get("ts", 0) >= best[key].get("ts", 0):
            best[key] = r
    return list(best.values())


def recommended(rows: list[dict]) -> dict:
    return min(rows, key=lambda r: (-r["accuracy"], r["mean_cost_usd"]))


def fmt_usd(x: float) -> str:
    return f"${x:.4f}"


def worth_color(w: float) -> str:
    # CSS var() so the static <noscript> table tracks the token layer (light/dark) too.
    if w > 0.02:
        return "var(--fb-better)"
    if w < -0.02:
        return "var(--fb-worse)"
    return "var(--fb-text-muted)"


def pareto_frontier(by_recipe: dict[str, dict]) -> list[dict]:
    """Non-dominated cost-quality points: sort by cost asc, keep strictly rising accuracy.
    Input: name -> {acc, cost, ...}. Output: [{"cost_usd", "accuracy"}] sorted by cost asc."""
    pts = sorted(by_recipe.values(), key=lambda v: v["cost"])
    front: list[dict] = []
    best_a = -1.0
    for v in pts:
        if v["acc"] > best_a + 1e-9:
            front.append({"cost_usd": v["cost"], "accuracy": v["acc"]})
            best_a = v["acc"]
    return front


def svg_scatter(by_recipe: dict[str, dict]) -> str:
    """Aggregate cost-quality scatter with a Pareto frontier. by_recipe: name -> {acc,cost,arm}."""
    if not by_recipe:
        return ""
    W, H, pad = 640, 380, 56
    accs = [v["acc"] for v in by_recipe.values()]
    costs = [v["cost"] for v in by_recipe.values()]
    amin, amax = min(accs), max(accs)
    cmin, cmax = min(costs), max(costs)
    amin = max(0.0, amin - 0.05); amax = min(1.0, amax + 0.05)
    span_c = (cmax - cmin) or 1.0
    cmin -= span_c * 0.1; cmax += span_c * 0.1

    def X(c): return pad + (c - cmin) / (cmax - cmin) * (W - 2 * pad)
    def Y(a): return H - pad - (a - amin) / (amax - amin) * (H - 2 * pad)

    # SVG presentation attrs don't resolve CSS var() — use style="..." so the static
    # <noscript> scatter still tracks the token layer (light/dark) like the live charts.
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-label="Cost-quality scatter of recipes with Pareto frontier" '
             f'style="font-family:var(--fb-font-mono)">']
    # axes
    parts.append(f'<line x1="{pad}" y1="{H-pad}" x2="{W-pad}" y2="{H-pad}" style="stroke:var(--fb-chart-svg-axis)"/>')
    parts.append(f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{H-pad}" style="stroke:var(--fb-chart-svg-axis)"/>')
    parts.append(f'<text x="{W/2}" y="{H-16}" text-anchor="middle" font-size="13" '
                 f'style="fill:var(--fb-chart-axis)">cost per task ($) -></text>')
    parts.append(f'<text x="18" y="{H/2}" text-anchor="middle" font-size="13" '
                 f'style="fill:var(--fb-chart-axis)" transform="rotate(-90 18 {H/2})">accuracy -></text>')
    # frontier (upper-left envelope) via shared pareto_frontier
    front = [(p["cost_usd"], p["accuracy"]) for p in pareto_frontier(by_recipe)]
    if len(front) >= 2:
        poly = " ".join(f"{X(c):.1f},{Y(a):.1f}" for c, a in front)
        parts.append(f'<polyline points="{poly}" fill="none" style="stroke:var(--fb-chart-pareto)" '
                     f'stroke-dasharray="5 5" stroke-width="1.5"/>')
    # points
    for nm, v in by_recipe.items():
        col = ARM_COLOR.get(v["arm"], ARM_COLOR["best_single"])
        x, y = X(v["cost"]), Y(v["acc"])
        parts.append(f'<rect x="{x-6:.1f}" y="{y-6:.1f}" width="12" height="12" '
                     f'style="fill:{col}" fill-opacity="0.9"/>')
        parts.append(f'<text x="{x:.1f}" y="{y-12:.1f}" text-anchor="middle" font-size="11.5" '
                     f'style="fill:var(--fb-chart-text)">{html.escape(nm)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def compl_bars(by_type: dict[str, list[dict]]) -> str:
    items = []
    for ttype, rows in by_type.items():
        cs = [r["complementarity"] for r in rows if r.get("complementarity") is not None]
        if cs:
            items.append((ttype, sum(cs) / len(cs)))
    if not items:
        return "<p style='color:var(--fb-text-muted)'>No complementarity recorded.</p>"
    out = ['<div class="bars">']
    for ttype, c in sorted(items, key=lambda x: -x[1]):
        pct = round(c * 100)
        out.append(
            f'<div class="bar-row"><span class="bar-label">{html.escape(ttype)}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{pct}%"></span></span>'
            f'<span class="bar-val">{c:.2f}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


# PAGE is split into three parts to safely embed TOKENS_CSS (which contains literal
# CSS curly braces) without breaking str.format().  _make_page() concatenates them.
_PAGE_HEAD = """\
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600&family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet">
<title>__TITLE__</title><style>
:root{color-scheme:light dark}
*{box-sizing:border-box}
"""

# TOKENS_CSS is injected here (no .format — raw concatenation)

_PAGE_CSS = """\
body{font-family:var(--fb-font-body);color:var(--fb-text);background:var(--fb-bg);margin:0;line-height:var(--fb-body-lh);font-size:var(--fb-body)}
.wrap{max-width:var(--fb-max-width);margin:0 auto;padding:40px 24px 80px}
/* masthead — брутал-плита: чернильный блок с mono-eyebrow + крупным заголовком */
.masthead{background:var(--fb-text);color:var(--fb-bg);border:var(--fb-border-w) solid var(--fb-border);padding:22px 24px;margin:0 0 8px}
.masthead .eyebrow{font-family:var(--fb-font-mono);font-size:var(--fb-label);letter-spacing:0.12em;text-transform:uppercase;color:var(--fb-accent);margin:0 0 8px}
h1{font-family:var(--fb-font-mono);font-size:var(--fb-h1);line-height:var(--fb-h1-lh);font-weight:700;letter-spacing:-0.02em;margin:0}
.masthead h1{color:var(--fb-bg)}
.sub{color:var(--fb-text-muted);margin:14px 0 24px;max-width:64ch}
/* verdict — инверсная плита с офсет-тенью и оранжевой левой колонкой-маркером */
.verdict{background:var(--fb-verdict-bg);border:var(--fb-border-w) solid var(--fb-verdict-border);box-shadow:var(--fb-shadow);padding:16px 20px;margin:0 0 30px;color:var(--fb-verdict-text);font-size:var(--fb-body);position:relative}
.verdict::before{content:"▸";color:var(--fb-accent);font-family:var(--fb-font-mono);margin-right:10px;font-weight:700}
.verdict b{color:var(--fb-accent)}
h2{font-family:var(--fb-font-mono);font-size:var(--fb-h2);line-height:var(--fb-h2-lh);font-weight:700;letter-spacing:-0.01em;margin:36px 0 12px;padding-bottom:6px;border-bottom:var(--fb-border-w) solid var(--fb-border)}
table{width:100%;border-collapse:collapse;font-size:var(--fb-body);background:var(--fb-surface);border:var(--fb-border-w) solid var(--fb-border);border-radius:var(--fb-radius)}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--fb-border-faint)}
th{background:var(--fb-surface-2-light);color:var(--fb-text-muted);font-family:var(--fb-font-mono);font-size:var(--fb-label);font-weight:var(--fb-label-weight);text-transform:var(--fb-label-transform);letter-spacing:var(--fb-label-tracking);border-bottom:var(--fb-border-w) solid var(--fb-border)}
td.num{text-align:right;font-family:var(--fb-font-mono);font-feature-settings:var(--fb-num-features)}
tr.rec{background:var(--fb-accent-bg)}
tr.rec td:first-child{border-left:4px solid var(--fb-accent)}
.badge{display:inline-block;background:var(--fb-accent);color:var(--fb-accent-ink);font-family:var(--fb-font-mono);font-size:11px;font-weight:500;padding:1px 7px;border-radius:var(--fb-radius-pill);margin-left:8px;text-transform:uppercase;letter-spacing:0.04em}
.card{background:var(--fb-surface);border:var(--fb-border-w) solid var(--fb-border);border-radius:var(--fb-radius);padding:18px;margin-top:8px}
.bars{display:flex;flex-direction:column;gap:8px}
.bar-row{display:flex;align-items:center;gap:12px}
.bar-label{width:130px;color:var(--fb-text-strong);font-family:var(--fb-font-mono);font-size:var(--fb-small)}
.bar-track{flex:1;height:12px;background:var(--fb-surface-2-light);border:1px solid var(--fb-border);border-radius:var(--fb-radius);overflow:hidden}
.bar-fill{display:block;height:100%;background:var(--fb-accent)}
.bar-val{width:42px;text-align:right;font-family:var(--fb-font-mono);font-feature-settings:var(--fb-num-features);color:var(--fb-text-muted);font-size:var(--fb-small)}
.foot{color:var(--fb-text-faint);font-family:var(--fb-font-mono);font-size:var(--fb-label);margin-top:40px;border-top:var(--fb-border-w) solid var(--fb-border);padding-top:14px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-family:var(--fb-font-mono);font-size:var(--fb-small);color:var(--fb-text-muted);margin:8px 0 0}
.dot{display:inline-block;width:10px;height:10px;border-radius:0;margin-right:5px;vertical-align:-1px}
/* контролы — терминальная строка: квадратные, хард-границы */
#filters select,#filters input,button{font-family:var(--fb-font-mono);border-radius:var(--fb-radius)}
button{background:var(--fb-surface);color:var(--fb-text);border:var(--fb-border-w) solid var(--fb-border);padding:6px 14px;font-size:var(--fb-small);cursor:pointer;transition:background .12s,color .12s}
button:hover{background:var(--fb-accent);color:var(--fb-accent-ink);border-color:var(--fb-accent)}
@media (prefers-color-scheme: dark){
  .masthead{background:var(--fb-surface-2);color:var(--fb-text)}
  .masthead h1{color:var(--fb-text)}
  .card,table{background:var(--fb-surface);border-color:var(--fb-border)}
  th{background:var(--fb-surface-2-light)}
  #filters select,#filters input,button{background:var(--fb-surface);color:var(--fb-text);border:var(--fb-border-w) solid var(--fb-border)}
}
"""

_PAGE_TAIL = """\
</style></head><body><div class="wrap">
<div class="nav" style="margin:0 0 14px;font-family:var(--fb-font-mono);font-size:var(--fb-small)"><a href="leaderboard.html" style="color:var(--fb-accent);text-decoration:none">▸ contributor leaderboard →</a></div>
<div class="masthead">
  <p class="eyebrow">▸ fusionbench / catalog</p>
  <h1>__TITLE__</h1>
</div>
<p class="sub">When is multi-model fusion worth it — and which combo, per task type. __META__</p>
<div class="verdict">__VERDICT__</div>
<div id="filters" class="card" style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-top:8px"></div>
<h2>Cost vs quality</h2>
<div id="hero" class="card" style="height:420px"></div>
<h2>Worthiness — recipe \xd7 task type</h2>
<div id="heatmap" class="card" style="height:420px"></div>
<h2>Explorer</h2>
<div style="margin:8px 0">
  <button id="dl-csv">Скачать CSV</button>
  <button id="dl-json">Скачать JSON</button>
</div>
<div id="explorer-chart" class="card" style="height:420px"></div>
<div id="explorer-table" class="card" style="overflow-x:auto"></div>
<noscript>
__SECTIONS__
<h2>Cost vs quality (static)</h2>
<div class="card">__SCATTER__<div class="legend">__LEGEND__</div></div>
<h2>Panel complementarity by task type</h2>
<div class="card">__BARS__</div>
</noscript>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>
<script src="app.js"></script>
<p class="foot">__FOOT__</p>
</div></body></html>
"""


def _make_page(*, title: str, meta: str, verdict: str, sections: str,
               scatter: str, legend: str, bars: str, foot: str) -> str:
    """Assemble the catalog HTML page, injecting TOKENS_CSS safely (no .format collision)."""
    page = (
        _PAGE_HEAD.replace("__TITLE__", title, 1)
        + TOKENS_CSS
        + _PAGE_CSS
        + _PAGE_TAIL
        .replace("__TITLE__", title)
        .replace("__META__", meta)
        .replace("__VERDICT__", verdict)
        .replace("__SECTIONS__", sections)
        .replace("__SCATTER__", scatter)
        .replace("__LEGEND__", legend)
        .replace("__BARS__", bars)
        .replace("__FOOT__", foot)
    )
    return page


def render_fallback(rows: list[dict], title: str) -> str:
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_type[r["task_type"]].append(r)

    n_types = len(by_type)
    n_fusion_best = 0
    sections = []
    for ttype in sorted(by_type):
        rs = sorted(by_type[ttype], key=lambda r: -r["accuracy"])
        rec = recommended(rs)
        if rec["arm"] in ("fusion", "source_pool"):
            n_fusion_best += 1
        head = ("<tr><th>recipe</th><th>arm</th><th class='num'>accuracy</th>"
                "<th class='num'>$ / task</th><th class='num'>Δ vs self-moa</th>"
                "<th class='num'>complementarity</th></tr>")
        body = []
        for r in rs:
            is_rec = (r["recipe"] == rec["recipe"])
            w = r.get("worthiness_vs_self_moa", 0.0)
            compl = r.get("complementarity")
            compl_s = f"{compl:.2f}" if compl is not None else "—"
            badge = "<span class='badge'>recommended</span>" if is_rec else ""
            body.append(
                f"<tr class='{'rec' if is_rec else ''}'>"
                f"<td>{html.escape(r['recipe'])}{badge}</td>"
                f"<td>{html.escape(r['arm'])}</td>"
                f"<td class='num'>{r['accuracy']:.3f}</td>"
                f"<td class='num'>{fmt_usd(r['mean_cost_usd'])}</td>"
                f"<td class='num' style='color:{worth_color(w)}'>{w:+.3f}</td>"
                f"<td class='num'>{compl_s}</td></tr>"
            )
        sections.append(f"<h2>{html.escape(ttype)}</h2><table>{head}{''.join(body)}</table>")

    by_recipe: dict[str, dict] = {}
    agg: dict[str, list] = defaultdict(list)
    for r in rows:
        agg[r["recipe"]].append(r)
    for nm, rs in agg.items():
        by_recipe[nm] = {
            "acc": sum(r["accuracy"] for r in rs) / len(rs),
            "cost": sum(r["mean_cost_usd"] for r in rs) / len(rs),
            "arm": rs[0]["arm"],
        }

    legend = "".join(
        f"<span><span class='dot' style='background:{c}'></span>{a}</span>"
        for a, c in ARM_COLOR.items()
    )
    verdict = (f"On <b>{n_types - n_fusion_best} of {n_types}</b> task types the best recipe is "
               f"<b>not</b> fusion — use a single model or self-MoA and save the spend. "
               f"Fusion earns its cost on <b>{n_fusion_best}</b>.")
    meta = f"{len(rows)} catalog rows · {n_types} task types"
    foot = ("Generated {t} by FusionBench build_catalog. Numbers reflect the runs in runs/*.jsonl "
            "(mock data is illustrative — re-generate after a live run)."
            ).format(t=time.strftime("%Y-%m-%d"))
    return _make_page(
        title=html.escape(title), meta=meta, verdict=verdict,
        sections="".join(sections), scatter=svg_scatter(by_recipe),
        legend=legend, bars=compl_bars(by_type), foot=foot,
    )


def build_data(rows: list[dict]) -> dict:
    """Emit the site/data.json contract from catalog rows. Pure: no I/O.

    Expects already-deduplicated rows (one per suite/task_type/recipe, as produced by
    dedupe()); the recommended flag assumes a recipe appears at most once per task_type."""
    suites = sorted({r["suite"] for r in rows if r.get("suite")})

    # recipes: name -> arm (first seen), stable by name
    recipe_arm: dict[str, str] = {}
    for r in rows:
        recipe_arm.setdefault(r["recipe"], r["arm"])
    recipes = [{"name": n, "arm": a} for n, a in sorted(recipe_arm.items())]

    # recommended flag: best (-accuracy, mean_cost_usd) per task_type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_type[r["task_type"]].append(r)
    rec_keys: set[tuple] = set()
    for ttype, rs in by_type.items():
        rec = recommended(rs)
        rec_keys.add((ttype, rec["recipe"]))

    cells = []
    for r in rows:
        cells.append({
            "type": r["task_type"],
            "recipe": r["recipe"],
            "arm": r["arm"],
            "accuracy": r["accuracy"],
            "cost_usd": r["mean_cost_usd"],
            "latency_s": r["mean_latency_s"],
            "worthiness_vs_best": r["worthiness_vs_best"],
            "worthiness_vs_self_moa": r["worthiness_vs_self_moa"],
            "complementarity": r.get("complementarity"),
            "recommended": (r["task_type"], r["recipe"]) in rec_keys,
            "n": r["n_tasks"],
        })

    # recipe_points / pareto: mean cost/accuracy per recipe across task types (hero scatter).
    # app.js recomputes these in JS from the filtered cells; kept here for the noscript SVG
    # fallback and as a stable data.json contract (JS no longer reads these two fields).
    agg: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        agg[r["recipe"]].append(r)
    recipe_points = []
    by_recipe_for_front: dict[str, dict] = {}
    for nm, rs in sorted(agg.items()):
        acc = sum(x["accuracy"] for x in rs) / len(rs)
        cost = sum(x["mean_cost_usd"] for x in rs) / len(rs)
        arm = rs[0]["arm"]
        recipe_points.append({"recipe": nm, "arm": arm, "accuracy": acc, "cost_usd": cost})
        by_recipe_for_front[nm] = {"acc": acc, "cost": cost, "arm": arm}

    pareto = pareto_frontier(by_recipe_for_front)

    # complementarity passthrough (emitted for the next stage; not drawn in core).
    # Shape is {type, recipe, value} — a per-recipe scalar, NOT the spec's pairwise
    # {a, b, type, value}: CatalogRow stores one complementarity scalar + a panel list,
    # not pairwise model values. The pairwise form is a next-stage (explorer) concern.
    complementarity = []
    for r in rows:
        if r.get("complementarity") is not None:
            complementarity.append({"type": r["task_type"], "recipe": r["recipe"],
                                    "value": r["complementarity"]})

    return {
        "generated": time.strftime("%Y-%m-%d"),
        "suites": suites,
        "recipes": recipes,
        "cells": cells,
        "recipe_points": recipe_points,
        "pareto": pareto,
        "complementarity": complementarity,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*", default=["runs/*.jsonl"])
    ap.add_argument("--out", default="site/index.html")
    ap.add_argument("--title", default="FusionBench — fusion recipe catalog")
    args = ap.parse_args()

    rows = dedupe(load_rows(args.runs))
    if not rows:
        raise SystemExit("no catalog rows found; run scripts/run_v0.py first")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_fallback(rows, args.title), encoding="utf-8")
    data_path = out.parent / "data.json"
    data_path.write_text(json.dumps(build_data(rows), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} and {data_path} from {len(rows)} deduped rows across "
          f"{len(set(r['task_type'] for r in rows))} task types")


if __name__ == "__main__":
    main()
