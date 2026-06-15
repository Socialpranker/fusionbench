# tests/test_build_data.py
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "build_catalog.py"
sys.path.insert(0, str(ROOT / "scripts"))

import build_catalog as bc


def test_pareto_frontier_keeps_nondominated():
    # points: name -> {acc, cost, arm}. Frontier = sort by cost asc, keep rising accuracy.
    pts = {
        "cheap-weak":   {"acc": 0.50, "cost": 0.001, "arm": "best_single"},
        "mid":          {"acc": 0.70, "cost": 0.004, "arm": "fusion"},
        "dominated":    {"acc": 0.60, "cost": 0.005, "arm": "fusion"},  # costlier, less accurate than mid
        "top":          {"acc": 0.80, "cost": 0.009, "arm": "source_pool"},
    }
    front = bc.pareto_frontier(pts)
    # returns list of {"cost_usd", "accuracy"} sorted by cost asc, only non-dominated
    accs = [round(p["accuracy"], 2) for p in front]
    assert accs == [0.50, 0.70, 0.80]   # "dominated" dropped
    costs = [p["cost_usd"] for p in front]
    assert costs == sorted(costs)        # cost ascending
