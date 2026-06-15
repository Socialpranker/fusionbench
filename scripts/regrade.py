#!/usr/bin/env python3
"""Re-grade a submission: recompute accuracy from saved outputs against held-out gold.

    python scripts/regrade.py --manifest <m.json> --outputs <o.jsonl> --gold <g.jsonl>

Accuracy mismatch is a HARD failure (exit 1) — this is the anti-cheat core. Cost is a
soft plausibility check (WARN, exit 0): model prices drift, so a hard cost gate would
red-flag honest submissions. Uses sys.exit, never assert (assert is stripped by python -O).

Trust model — what this gate DOES and does NOT stop:
  - STOPS accuracy inflation in the manifest (re-grade vs gold catches it).
  - STOPS cherry-picking: outputs must cover the ENTIRE gold slice (coverage check),
    so a submitter cannot grade only the rows their run got right.
  - STOPS padding: each gold_id may be graded at most once (duplicate check).
  - Does NOT stop a forged `prediction`: the prediction string comes from the submitter
    and graders are lenient by design (e.g. SyntheticGrader is a substring match), so a
    submitter who knows the gold answer can write it into every prediction and forge a
    pass. Defeating this needs a different trust root (client-signed outputs or
    server-side execution), not a check here. Tracked as a known limitation; see
    tests/test_regrade.py::test_forged_prediction_is_a_known_limitation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fusionbench.gold import gold_to_reference
from fusionbench.tasks.registry import REGISTRY

ACCURACY_TOL = 0.01
COST_WARN_TOL = 0.15


def _load_jsonl(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--outputs", required=True)
    ap.add_argument("--gold", required=True)
    args = ap.parse_args()

    man = json.loads(Path(args.manifest).read_text())
    claimed = man["claimed"]
    suite = man["suite"]

    spec = REGISTRY.get(suite)
    if spec is None:
        sys.exit(f"unknown suite {suite!r} (not in REGISTRY)")
    # "grader" is an optional manifest field; REGISTRY[suite] is authoritative either way.
    if man.get("grader") and man["grader"] != spec.grader.name:
        sys.exit(f"grader mismatch: manifest {man['grader']!r} vs registry {spec.grader.name!r}")

    gold = {row["id"]: row for row in _load_jsonl(args.gold)}
    outputs = [r for r in _load_jsonl(args.outputs) if r.get("recipe") == claimed["recipe"]]
    if not outputs:
        sys.exit(f"no outputs for claimed recipe {claimed['recipe']!r}")

    n = ok = 0
    recomputed_cost = 0.0
    seen: set[str] = set()
    for r in outputs:
        gid = r["gold_id"]
        if gid not in gold:
            sys.exit(f"gold_id {gid!r} from outputs not found in gold file")
        # HARD: a gold_id may be graded at most once. Without this a submitter pads the
        # output set with copies of one correct row to hit any claimed n/accuracy.
        if gid in seen:
            sys.exit(f"duplicate gold_id {gid!r} in outputs (each may appear at most once)")
        seen.add(gid)
        reference, metadata = gold_to_reference(suite, gold[gid])
        v = spec.grader.score(r["prediction"], reference, metadata)
        ok += int(v.passed)
        n += 1
        recomputed_cost += float(r.get("cost_usd", 0.0))

    # HARD: the re-grade must cover the ENTIRE held-out slice, not a submitter-chosen
    # subset. Accuracy over a cherry-picked set (only the rows the run got right) is the
    # core cheat this gate exists to stop, so coverage is checked against gold, never
    # against the manifest's own n.
    missing = set(gold) - seen
    if missing:
        sample = ", ".join(sorted(missing)[:5])
        more = "" if len(missing) <= 5 else f" (+{len(missing) - 5} more)"
        sys.exit(f"coverage gap: {len(missing)} gold id(s) not graded by outputs: {sample}{more}")

    if n != claimed["n"]:
        sys.exit(f"n mismatch: manifest says {claimed['n']}, found {n} outputs")

    acc = ok / n
    # HARD: accuracy must match within tolerance
    if abs(acc - claimed["accuracy"]) > ACCURACY_TOL:
        sys.exit(f"FAIL accuracy mismatch: re-graded {acc:.4f} vs claimed "
                 f"{claimed['accuracy']:.4f} (tol {ACCURACY_TOL})")

    # SOFT: cost plausibility (WARN only). Prices drift, so this never fails the build.
    claimed_total = claimed["cost_usd"] * n
    if recomputed_cost > 0:
        rel = abs(recomputed_cost - claimed_total) / recomputed_cost
        if rel > COST_WARN_TOL:
            print(f"WARN cost: re-summed ${recomputed_cost:.4f} vs claimed "
                  f"${claimed_total:.4f} (off by {rel*100:.0f}%)")
    elif claimed_total > 0:
        # outputs carry no cost but the manifest claims one — can't corroborate.
        print(f"WARN cost: outputs sum to $0.0000 but manifest claims "
              f"${claimed_total:.4f} (cannot corroborate)")

    print(f"OK re-graded acc={acc:.4f} (claimed {claimed['accuracy']:.4f}), "
          f"cost=${recomputed_cost:.4f}, n={n}")


if __name__ == "__main__":
    main()
