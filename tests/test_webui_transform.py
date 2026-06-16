import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from webui import transform as tr  # noqa: E402


def _cells():
    return [
        {"type": "code", "recipe": "best-single", "arm": "best_single", "accuracy": 0.90,
         "cost_usd": 0.001, "worthiness_vs_best": 0.0, "complementarity": None, "n": 12},
        {"type": "code", "recipe": "fusion-strong", "arm": "fusion", "accuracy": 0.95,
         "cost_usd": 0.010, "worthiness_vs_best": 0.05, "complementarity": 0.9, "n": 12},
        {"type": "math", "recipe": "fusion-strong", "arm": "fusion", "accuracy": 0.70,
         "cost_usd": 0.004, "worthiness_vs_best": -0.02, "complementarity": 0.3, "n": 8},
    ]


def test_filter_by_type():
    out = tr.filter_catalog(_cells(), type="code", maxcost=1.0, minacc=0.0, sort="accuracy")
    assert {c["type"] for c in out} == {"code"}
    assert len(out) == 2


def test_filter_by_maxcost():
    out = tr.filter_catalog(_cells(), type="", maxcost=0.005, minacc=0.0, sort="cost")
    assert all(c["cost_usd"] <= 0.005 for c in out)
    assert len(out) == 2


def test_filter_by_minacc():
    out = tr.filter_catalog(_cells(), type="", maxcost=1.0, minacc=0.90, sort="accuracy")
    assert all(c["accuracy"] >= 0.90 for c in out)
    assert len(out) == 2


def test_sort_cost_ascending():
    out = tr.filter_catalog(_cells(), type="", maxcost=1.0, minacc=0.0, sort="cost")
    costs = [c["cost_usd"] for c in out]
    assert costs == sorted(costs)


def test_sort_worthiness_desc_nulls_last():
    # worthiness sort: None must land at the end, deterministically.
    out = tr.filter_catalog(_cells(), type="", maxcost=1.0, minacc=0.0, sort="worthiness")
    worth = [c["worthiness_vs_best"] for c in out]
    assert worth == sorted(worth, reverse=True)


def test_empty_input_returns_empty():
    assert tr.filter_catalog([], type="", maxcost=1.0, minacc=0.0, sort="accuracy") == []


def test_to_leaderboard_df_columns():
    lb = {"contributors": [
        {"user": "alice", "points": 20.0, "verified": 1, "cells": ["frames×fusion"]},
    ]}
    headers, rows = tr.to_leaderboard_df(lb)
    assert headers == ["#", "user", "points", "verified", "cells"]
    assert rows[0] == [1, "alice", 20.0, 1, "frames×fusion"]


def test_to_leaderboard_df_empty():
    headers, rows = tr.to_leaderboard_df({"contributors": []})
    assert headers == ["#", "user", "points", "verified", "cells"]
    assert rows == []


def test_to_catalog_df_columns_and_order():
    headers, rows = tr.to_catalog_df(_cells()[:1])
    assert headers == ["type", "recipe", "arm", "accuracy", "cost_usd",
                       "worthiness_vs_best", "complementarity", "n"]
    assert rows[0] == ["code", "best-single", "best_single", 0.90, 0.001, 0.0, None, 12]


def test_slider_bounds_from_cells():
    b = tr.slider_bounds(_cells())
    assert b["maxcost"] == 0.010   # max cost across cells
    assert b["minacc"] == 0.0      # accuracy slider always starts at 0


def test_slider_bounds_empty_defaults():
    b = tr.slider_bounds([])
    assert b["maxcost"] == 1.0 and b["minacc"] == 0.0
