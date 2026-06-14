#!/usr/bin/env python3
"""FusionBench v0 runner.

Runs the five arms at a *matched token budget*, scores them on a verifiable suite,
computes panel complementarity, writes catalog rows, and prints a cost-quality
summary plus the two headline answers.

    python scripts/run_v0.py --mock --limit 30
    python scripts/run_v0.py --suite browsecomp --budget 8000 --limit 150
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

from fusionbench.presets import build_v0_recipes, CHEAP_PANEL, TASK_TYPES
from fusionbench.client import MockClient, OpenRouterClient
from fusionbench.solvers import run_arm
from fusionbench.scoring import is_correct
from fusionbench.budget import n_for_budget
from fusionbench import complementarity as C
from fusionbench.catalog import CatalogRow, write_rows, worthiness
from fusionbench.tasks.loaders import load_tasks, LOADERS
from fusionbench.tasks.browsecomp import synth_tasks
from fusionbench.tasks.registry import REGISTRY
from fusionbench.tasks.base import Example
from fusionbench.grading.base import Verdict
from fusionbench.runs import output_record, write_outputs


def load_suite(suite, limit, mock):
    """Returns (tasks, scorer, grader_name). Registry suites carry their own grader and
    reference; legacy suites (data/*.jsonl, --mock synth) keep the gold + is_correct path."""
    spec = REGISTRY.get(suite)
    if spec is not None and not (mock and suite == "frames"):
        examples = spec.loader.load(limit)
        tasks = [{"id": e.id, "type": e.type, "question": e.prompt, "gold": ""} for e in examples]
        ref = {e.id: e for e in examples}

        def scorer(task_id, answer):
            e = ref[task_id]
            return spec.grader.score(answer, e.reference, e.metadata).passed

        return tasks, scorer, spec.grader.name

    # --mock must stay offline: a network-backed loader (e.g. frames -> HF) is replaced
    # by synthetic probes; file/synth suites keep their normal mock path.
    if mock and suite in LOADERS:
        tasks = synth_tasks(limit)
    else:
        tasks = load_tasks(suite, limit, mock)

    def scorer(task_id, answer, _by_id={t["id"]: t for t in tasks}):
        t = _by_id[task_id]
        return is_correct(answer, t["gold"], t.get("aliases"))

    return tasks, scorer, "ExactMatch@1"


async def evaluate(client, tasks, recipes, scorer):
    jobs = [(t, r) for t in tasks for r in recipes]
    results = await asyncio.gather(*[run_arm(client, t, r) for (t, r) in jobs])
    out: dict[str, dict[str, object]] = defaultdict(dict)
    for (t, r), ar in zip(jobs, results):
        ar.correct = scorer(t["id"], ar.answer)
        out[r.name][t["id"]] = ar
    return out


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="browsecomp")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--budget", type=int, default=0, help="target tokens to match self-moa to; 0 = match fusion-strong")
    ap.add_argument("--n-self-moa", type=int, default=5)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--out", default="runs/catalog.jsonl")
    ap.add_argument("--outputs", default="runs/outputs.jsonl", help="raw per-task outputs for CI re-grade")
    args = ap.parse_args()

    client = MockClient() if args.mock else OpenRouterClient()
    tasks, scorer, grader_name = load_suite(args.suite, args.limit, args.mock)
    by_type = defaultdict(list)
    for t in tasks:
        by_type[t["type"]].append(t)

    # --- matched-budget calibration: set self-moa N so its tokens ~ fusion-strong's ---
    recipes = build_v0_recipes(n_self_moa=args.n_self_moa)
    fstrong = next(r for r in recipes if r.name == "fusion-strong")
    best = next(r for r in recipes if r.name == "best-single")
    cal_f = await run_arm(client, tasks[0], fstrong)
    cal_b = await run_arm(client, tasks[0], best)
    target = args.budget or cal_f.usage.total
    n = n_for_budget(target, max(1, cal_b.usage.total))
    n = n if n % 2 == 1 else n + 1   # odd N avoids majority-vote ties
    recipes = build_v0_recipes(n_self_moa=n)
    print(f"matched budget: target≈{target} tok/task -> self-moa N={n}  ({len(tasks)} tasks, {'MOCK' if args.mock else 'LIVE'})\n")

    results = await evaluate(client, tasks, recipes, scorer)
    names = [r.name for r in recipes]

    # --- overall cost-quality table ---
    print(f"{'recipe':<14}{'acc':>7}{'tokens':>9}{'cost$':>10}{'lat_s':>8}")
    overall = {}
    for nm in names:
        ars = list(results[nm].values())
        acc = mean(a.correct for a in ars)
        tok = mean(a.usage.total for a in ars)
        cost = mean(a.cost_usd for a in ars)
        lat = mean(a.latency_s for a in ars)
        overall[nm] = acc
        print(f"{nm:<14}{acc:>7.3f}{tok:>9.0f}{cost:>10.4f}{lat:>8.3f}")

    # --- headline answers (coverage hypothesis tested on web-augmented types) ---
    cov_ids = [t["id"] for t in tasks if t["type"] in ("deep_research", "multihop_qa")]
    d_fs = overall["fusion-strong"] - overall["self-moa"]
    print(f"\nfusion-strong vs self-moa (matched compute, overall): {d_fs:+.3f}")
    if cov_ids:
        ca = {nm: mean(results[nm][i].correct for i in cov_ids) for nm in names}
        cov_lift = ca["source-pool"] - ca["best-single"]
        mix_lift = ca["fusion-strong"] - ca["best-single"]
        print(f"on coverage tasks: best-single {ca['best-single']:.3f} | fusion-cheap "
              f"{ca['fusion-cheap']:.3f} | fusion-strong {ca['fusion-strong']:.3f} | "
              f"source-pool {ca['source-pool']:.3f}")
        if cov_lift <= 0.01:
            print("coverage signal: none (source-pool ~ best-single)")
        elif mix_lift <= 0.01:
            print(f"coverage signal: source-pool {cov_lift:+.3f} while full fusion adds ~0 "
                  "-> the lift is COVERAGE, fusion captures no more")
        else:
            ratio = min(cov_lift / mix_lift, 1.0)
            print(f"source-pool recovers {ratio*100:.0f}% of fusion's lift -> "
                  f"coverage {'is the main driver' if ratio >= 0.5 else 'is not the whole story'}")

    # --- per-type complementarity (cheap-panel) + best recipe + catalog rows ---
    rows = []
    print(f"\n{'task_type':<14}{'best_recipe':<14}{'acc':>6}{'compl':>7}{'oracle':>8}")
    for ttype, ts in by_type.items():
        ids = [t["id"] for t in ts]
        tmap = {t["id"]: t for t in ts}
        # Per-model complementarity is defined via agreement with a gold answer; suites
        # without a gold string (constraint / synthetic types) don't support it.
        has_gold = any(tmap[i].get("gold") for i in ids)
        if has_gold:
            correctness = {
                m: [is_correct(results["fusion-cheap"][i].panel_answers.get(m, ""),
                               tmap[i]["gold"], tmap[i].get("aliases")) for i in ids]
                for m in CHEAP_PANEL
            }
            compl = C.panel_complementarity(correctness, CHEAP_PANEL)
            oracle = C.oracle_coverage(correctness, CHEAP_PANEL)
        else:
            compl = oracle = 0.0
        type_acc = {nm: mean(results[nm][i].correct for i in ids) for nm in names}
        best_recipe = max(names, key=lambda nm: type_acc[nm])
        print(f"{ttype:<14}{best_recipe:<14}{type_acc[best_recipe]:>6.2f}{compl:>7.2f}{oracle:>8.2f}")

        for r in recipes:
            ar0 = results[r.name][ids[0]]
            rows.append(CatalogRow(
                suite=args.suite, task_type=ttype, recipe=r.name, arm=r.arm, n_tasks=len(ids),
                accuracy=round(type_acc[r.name], 4),
                mean_tokens=round(mean(results[r.name][i].usage.total for i in ids), 1),
                mean_cost_usd=round(mean(results[r.name][i].cost_usd for i in ids), 6),
                mean_latency_s=round(mean(results[r.name][i].latency_s for i in ids), 4),
                worthiness_vs_best=worthiness(type_acc[r.name], type_acc["best-single"]),
                worthiness_vs_self_moa=worthiness(type_acc[r.name], type_acc["self-moa"]),
                panel=list(r.panel), judge=r.judge, synth=r.synth,
                complementarity=round(compl, 3) if r.arm in ("fusion", "source_pool") else None,
                oracle_coverage=round(oracle, 3) if r.arm in ("fusion", "source_pool") else None,
                notes="mock" if args.mock else "live",
            ))

    write_rows(args.out, rows)
    print(f"\nwrote {len(rows)} catalog rows -> {args.out}")

    # --- raw per-(task × recipe) outputs: the artifact CI re-grades without LLM calls ---
    run_id = f"{args.suite}_{'mock' if args.mock else 'live'}_{len(tasks)}"
    tmap_all = {t["id"]: t for t in tasks}
    records = []
    for r in recipes:
        for tid, ar in results[r.name].items():
            ex = Example(id=tid, prompt=tmap_all[tid]["question"], reference=tmap_all[tid]["gold"],
                         type=tmap_all[tid]["type"])
            verdict = Verdict(passed=bool(ar.correct), score=1.0 if ar.correct else 0.0)
            records.append(output_record(run_id, ex, r.name, ar, verdict, grader_name))
    write_outputs(args.outputs, records)
    print(f"wrote {len(records)} output records -> {args.outputs}")

    if not args.mock:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
