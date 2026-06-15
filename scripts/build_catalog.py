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
import time
from collections import defaultdict
from pathlib import Path

ARM_COLOR = {
    "best_single": "#6b7280", "self_moa": "#2563eb",
    "fusion": "#0d9488", "source_pool": "#7c3aed",
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
    if w > 0.02:
        return "#15803d"
    if w < -0.02:
        return "#b91c1c"
    return "#6b7280"


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

    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-label="Cost-quality scatter of recipes with Pareto frontier" '
             f'font-family="system-ui,sans-serif">']
    # axes
    parts.append(f'<line x1="{pad}" y1="{H-pad}" x2="{W-pad}" y2="{H-pad}" stroke="#d1d5db"/>')
    parts.append(f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{H-pad}" stroke="#d1d5db"/>')
    parts.append(f'<text x="{W/2}" y="{H-16}" text-anchor="middle" font-size="13" '
                 f'fill="#6b7280">cost per task ($) -></text>')
    parts.append(f'<text x="18" y="{H/2}" text-anchor="middle" font-size="13" fill="#6b7280" '
                 f'transform="rotate(-90 18 {H/2})">accuracy -></text>')
    # frontier (upper-left envelope) via shared pareto_frontier
    front = [(p["cost_usd"], p["accuracy"]) for p in pareto_frontier(by_recipe)]
    if len(front) >= 2:
        poly = " ".join(f"{X(c):.1f},{Y(a):.1f}" for c, a in front)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="#9ca3af" '
                     f'stroke-dasharray="5 5" stroke-width="1.5"/>')
    # points
    for nm, v in by_recipe.items():
        col = ARM_COLOR.get(v["arm"], "#6b7280")
        x, y = X(v["cost"]), Y(v["acc"])
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{col}" '
                     f'fill-opacity="0.85"/>')
        parts.append(f'<text x="{x:.1f}" y="{y-12:.1f}" text-anchor="middle" font-size="11.5" '
                     f'fill="#374151">{html.escape(nm)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def compl_bars(by_type: dict[str, list[dict]]) -> str:
    items = []
    for ttype, rows in by_type.items():
        cs = [r["complementarity"] for r in rows if r.get("complementarity") is not None]
        if cs:
            items.append((ttype, sum(cs) / len(cs)))
    if not items:
        return "<p style='color:#6b7280'>No complementarity recorded.</p>"
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


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{color-scheme:light}}
*{{box-sizing:border-box}}
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#111827;background:#f8fafc;margin:0;line-height:1.55}}
.wrap{{max-width:880px;margin:0 auto;padding:40px 24px 80px}}
h1{{font-size:26px;font-weight:600;margin:0 0 4px}}
.sub{{color:#6b7280;margin:0 0 24px}}
.verdict{{background:#ecfdf5;border:1px solid #a7f3d0;border-radius:12px;padding:14px 18px;margin:0 0 28px;color:#065f46;font-size:15px}}
h2{{font-size:18px;font-weight:600;margin:34px 0 12px}}
table{{width:100%;border-collapse:collapse;font-size:14px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #f1f5f9}}
th{{background:#f8fafc;color:#6b7280;font-weight:600;font-size:12.5px;text-transform:uppercase;letter-spacing:.03em}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}
tr.rec{{background:#f0fdfa}}
tr.rec td:first-child{{border-left:3px solid #0d9488}}
.badge{{display:inline-block;background:#0d9488;color:#fff;font-size:11px;padding:2px 8px;border-radius:999px;margin-left:8px}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:18px;margin-top:8px}}
.bars{{display:flex;flex-direction:column;gap:8px}}
.bar-row{{display:flex;align-items:center;gap:12px}}
.bar-label{{width:130px;color:#374151;font-size:13px}}
.bar-track{{flex:1;height:10px;background:#f1f5f9;border-radius:999px;overflow:hidden}}
.bar-fill{{display:block;height:100%;background:#0d9488}}
.bar-val{{width:42px;text-align:right;font-variant-numeric:tabular-nums;color:#6b7280;font-size:13px}}
.foot{{color:#9ca3af;font-size:12.5px;margin-top:40px;border-top:1px solid #e5e7eb;padding-top:14px}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:#6b7280;margin:8px 0 0}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:-1px}}
</style></head><body><div class="wrap">
<h1>{title}</h1>
<p class="sub">When is multi-model fusion worth it — and which combo, per task type. {meta}</p>
<div class="verdict">{verdict}</div>
<h2>Cost vs quality</h2>
<div id="hero" class="card" style="height:420px"></div>
<h2>Worthiness — recipe × task type</h2>
<div id="heatmap" class="card" style="height:420px"></div>
<noscript>
{sections}
<h2>Cost vs quality (static)</h2>
<div class="card">{scatter}<div class="legend">{legend}</div></div>
<h2>Panel complementarity by task type</h2>
<div class="card">{bars}</div>
</noscript>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<script src="app.js"></script>
<p class="foot">{foot}</p>
</div></body></html>"""


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
    return PAGE.format(title=html.escape(title), meta=meta, verdict=verdict,
                       sections="".join(sections), scatter=svg_scatter(by_recipe),
                       legend=legend, bars=compl_bars(by_type), foot=foot)


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

    # recipe_points: mean cost/accuracy per recipe across task types (hero scatter)
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

    # complementarity passthrough (emitted for the next stage; not drawn in core)
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
