#!/usr/bin/env python3
"""Prefilter-driven recipe search per task type.

    python scripts/run_search.py --mock --limit 60
    python scripts/run_search.py --suite frames --limit 200 --probe 8 --k 2

Stage 1 probes each model cheaply; stage 2 fully evaluates only the top-k most
complementary panels (+ baselines) per task type, then writes catalog rows and
reports how much of the brute-force search was pruned.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from fusionbench.presets import CHEAP_PANEL, STRONG_PANEL, BEST_SINGLE
from fusionbench.client import MockClient, OpenRouterClient
from fusionbench.solvers import run_arm
from fusionbench.scoring import is_correct
from fusionbench.search import probe_correctness, shortlist_for_type
from fusionbench.catalog import CatalogRow, write_rows, worthiness
from fusionbench.tasks.loaders import load_tasks


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="browsecomp")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--probe", type=int, default=6, help="probe tasks per type (stage 1)")
    ap.add_argument("--panel-size", type=int, default=3)
    ap.add_argument("--k", type=int, default=2, help="panels to keep per type")
    ap.add_argument("--n-self-moa", type=int, default=5)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--out", default="runs/catalog_search.jsonl")
    args = ap.parse_args()

    client = MockClient() if args.mock else OpenRouterClient()
    pool = list(dict.fromkeys(CHEAP_PANEL + STRONG_PANEL))
    tasks = load_tasks(args.suite, args.limit, args.mock)

    by_type = defaultdict(list)
    for t in tasks:
        by_type[t["type"]].append(t)
    probe = [t for ts in by_type.values() for t in ts[:args.probe]]
    eval_by_type = {ty: ts[args.probe:] for ty, ts in by_type.items()}

    corr, probe_usage = await probe_correctness(client, probe, pool)
    n_cand = None
    print(f"pool={len(pool)} models | probe={len(probe)} tasks ({args.probe}/type) | "
          f"stage-1 tokens={probe_usage.total}  ({'MOCK' if args.mock else 'LIVE'})\n")

    rows, total_eval = [], 0
    for ttype in by_type:
        ev = eval_by_type.get(ttype, [])
        if ttype not in corr or not ev:
            continue
        recipes, ranked, n_cand = shortlist_for_type(
            corr[ttype], pool, panel_size=args.panel_size, k=args.k,
            synth="anthropic/claude-opus-4.8", best=BEST_SINGLE, n_self_moa=args.n_self_moa,
        )
        compl_of = {f"fusion-top{i+1}": s for i, (_p, s) in enumerate(ranked)}

        jobs = [(t, r) for t in ev for r in recipes]
        res = await asyncio.gather(*[run_arm(client, t, r) for (t, r) in jobs])
        per = defaultdict(list)
        for (t, r), ar in zip(jobs, res):
            ar.correct = is_correct(ar.answer, t["gold"], t.get("aliases"))
            per[r.name].append(ar)
        total_eval += len(recipes)

        acc = {nm: mean(a.correct for a in per[nm]) for nm in per}
        cost = {nm: mean(a.cost_usd for a in per[nm]) for nm in per}
        winner = min((nm for nm in acc), key=lambda nm: (-acc[nm], cost[nm]))

        print(f"=== {ttype} ===  eval={len(ev)}  pruned {n_cand - args.k}/{n_cand} candidate panels")
        for i, (panel, score) in enumerate(ranked):
            print(f"   top{i+1} compl={score:.2f}  {'+'.join(p.split('/')[-1] for p in panel)}")
        for nm in sorted(acc, key=lambda n: -acc[n]):
            star = "  <- winner" if nm == winner else ""
            print(f"   {nm:<14} acc={acc[nm]:.3f} cost=${cost[nm]:.4f}{star}")
        print()

        best_recipe = next(r for r in recipes if r.name == winner)
        rows.append(CatalogRow(
            suite=args.suite, task_type=ttype, recipe=winner, arm=best_recipe.arm, n_tasks=len(ev),
            accuracy=round(acc[winner], 4),
            mean_tokens=round(mean(a.usage.total for a in per[winner]), 1),
            mean_cost_usd=round(cost[winner], 6),
            mean_latency_s=round(mean(a.latency_s for a in per[winner]), 4),
            worthiness_vs_best=worthiness(acc[winner], acc.get("best-single", 0.0)),
            worthiness_vs_self_moa=worthiness(acc[winner], acc.get("self-moa", 0.0)),
            panel=list(best_recipe.panel), judge=best_recipe.judge, synth=best_recipe.synth,
            complementarity=compl_of.get(winner), notes="search " + ("mock" if args.mock else "live"),
        ))

    write_rows(args.out, rows)
    brute = (n_cand or 0) * len(by_type)
    print(f"evaluated {total_eval} recipes total; brute force over panels alone would be "
          f"~{brute}. wrote {len(rows)} winning rows -> {args.out}")
    if not args.mock:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
