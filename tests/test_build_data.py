# tests/test_build_data.py
import json  # noqa: F401  # used by later tasks
import subprocess  # noqa: F401  # used by later tasks
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "build_catalog.py"
sys.path.insert(0, str(ROOT / "scripts"))

import build_catalog as bc  # noqa: E402


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


def _sample_rows():
    # two task types, a few recipes each; dict form as in runs/catalog.jsonl
    return [
        {"suite": "frames", "task_type": "multihop_qa", "recipe": "best-single", "arm": "best_single",
         "n_tasks": 10, "accuracy": 0.60, "mean_tokens": 100, "mean_cost_usd": 0.001,
         "mean_latency_s": 0.5, "worthiness_vs_best": 0.0, "worthiness_vs_self_moa": 0.0,
         "panel": [], "judge": None, "synth": None, "complementarity": None,
         "oracle_coverage": None, "notes": "mock", "ts": 1},
        {"suite": "frames", "task_type": "multihop_qa", "recipe": "fusion-strong", "arm": "fusion",
         "n_tasks": 10, "accuracy": 0.71, "mean_tokens": 400, "mean_cost_usd": 0.0044,
         "mean_latency_s": 1.6, "worthiness_vs_best": 0.11, "worthiness_vs_self_moa": 0.10,
         "panel": ["a", "b"], "judge": "j", "synth": "s", "complementarity": 0.79,
         "oracle_coverage": 0.9, "notes": "mock", "ts": 1},
        {"suite": "ruler", "task_type": "long_context", "recipe": "best-single", "arm": "best_single",
         "n_tasks": 12, "accuracy": 0.33, "mean_tokens": 90, "mean_cost_usd": 0.0009,
         "mean_latency_s": 0.4, "worthiness_vs_best": 0.0, "worthiness_vs_self_moa": 0.0,
         "panel": [], "judge": None, "synth": None, "complementarity": None,
         "oracle_coverage": None, "notes": "mock", "ts": 1},
    ]


def test_build_data_schema_keys():
    d = bc.build_data(_sample_rows())
    assert set(d) >= {"generated", "suites", "recipes", "cells", "recipe_points", "pareto", "complementarity"}
    assert d["suites"] == ["frames", "ruler"]               # sorted unique suites
    assert {r["name"] for r in d["recipes"]} == {"best-single", "fusion-strong"}


def test_build_data_cell_field_mapping():
    d = bc.build_data(_sample_rows())
    cell = next(c for c in d["cells"] if c["recipe"] == "fusion-strong")
    assert cell["type"] == "multihop_qa"          # task_type -> type
    assert cell["cost_usd"] == 0.0044             # mean_cost_usd -> cost_usd
    assert cell["latency_s"] == 1.6               # mean_latency_s -> latency_s
    assert cell["n"] == 10                        # n_tasks -> n
    assert cell["worthiness_vs_best"] == 0.11
    assert cell["complementarity"] == 0.79


def test_build_data_recommended_flag_one_per_type():
    d = bc.build_data(_sample_rows())
    by_type = {}
    for c in d["cells"]:
        by_type.setdefault(c["type"], []).append(c)
    for ttype, cells in by_type.items():
        recs = [c for c in cells if c["recommended"]]
        assert len(recs) == 1, ttype                     # exactly one recommended per type
    # in multihop_qa, fusion-strong (0.71) beats best-single (0.60)
    rec = next(c for c in d["cells"] if c["type"] == "multihop_qa" and c["recommended"])
    assert rec["recipe"] == "fusion-strong"


def test_build_data_recipe_points_and_pareto():
    d = bc.build_data(_sample_rows())
    # recipe_points: mean cost/accuracy per recipe across types
    bs = next(p for p in d["recipe_points"] if p["recipe"] == "best-single")
    assert bs["arm"] == "best_single"
    assert round(bs["accuracy"], 4) == round((0.60 + 0.33) / 2, 4)   # averaged across both types
    # pareto is a non-empty list of {cost_usd, accuracy}, cost ascending
    assert d["pareto"] and all({"cost_usd", "accuracy"} <= set(p) for p in d["pareto"])
    costs = [p["cost_usd"] for p in d["pareto"]]
    assert costs == sorted(costs)


def test_build_data_json_serializable_and_null_complementarity():
    d = bc.build_data(_sample_rows())
    json.dumps(d)                                           # must not raise
    cell = next(c for c in d["cells"] if c["recipe"] == "best-single" and c["type"] == "multihop_qa")
    assert cell["complementarity"] is None                 # null passthrough


def test_main_writes_data_json_and_index(tmp_path):
    out_html = tmp_path / "index.html"
    out_json = tmp_path / "data.json"
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--runs", str(ROOT / "runs" / "catalog.jsonl"),
         "--out", str(out_html)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert out_html.exists() and out_json.exists()          # data.json sits next to index.html
    data = json.loads(out_json.read_text())                 # valid JSON
    assert data["cells"] and data["recipe_points"]
    html_text = out_html.read_text()
    assert "<noscript>" in html_text                        # SVG fallback present
    assert "echarts" in html_text.lower()                   # ECharts wired
    assert "app.js" in html_text                            # app.js referenced
