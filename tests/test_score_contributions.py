# tests/test_score_contributions.py
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import score_contributions as sc  # noqa: E402


def _man(user, suite, recipe, run_id, accuracy=0.7, cost_usd=0.004, n=100):
    # shape of submissions/<user>/<run_id>/manifest.json (claimed nested as in real manifests)
    return {"schema_version": 1, "run_id": run_id, "submitted_by": user, "suite": suite,
            "claimed": {"recipe": recipe, "accuracy": accuracy, "cost_usd": cost_usd, "n": n}}


def test_single_cell_single_user():
    subs = [_man("alice", "frames", "fusion-strong", "r1")]
    lb = sc.score_contributions(subs, now="2026-06-15")
    assert lb["updated"] == "2026-06-15"
    assert lb["contributors"] == [
        {"user": "alice", "points": 20.0, "verified": 1, "cells": ["frames×fusion-strong"]}
    ]


def test_decay_across_users():
    # same cell submitted by 3 users, ordered by run_id → 20 / 10 / 5
    subs = [_man("a", "frames", "fusion", "r3"),
            _man("b", "frames", "fusion", "r1"),
            _man("c", "frames", "fusion", "r2")]
    lb = sc.score_contributions(subs, now="2026-06-15")
    pts = {c["user"]: c["points"] for c in lb["contributors"]}
    assert pts == {"b": 20.0, "c": 10.0, "a": 5.0}   # r1=20, r2=10, r3=5


def test_decay_same_user_accumulates():
    # one user, same cell ×3 → 20+10+5 = 35 (prior counted per cell globally)
    subs = [_man("alice", "frames", "fusion", "r1"),
            _man("alice", "frames", "fusion", "r2"),
            _man("alice", "frames", "fusion", "r3")]
    lb = sc.score_contributions(subs, now="2026-06-15")
    assert lb["contributors"][0] == {
        "user": "alice", "points": 35.0, "verified": 3, "cells": ["frames×fusion"]
    }


def test_sort_points_desc_then_user_asc():
    subs = [_man("zoe", "frames", "a", "r1"),         # zoe 20
            _man("amy", "ruler", "b", "r2"),          # amy 20
            _man("amy", "code", "c", "r3")]           # amy +20 = 40
    lb = sc.score_contributions(subs, now="2026-06-15")
    assert [c["user"] for c in lb["contributors"]] == ["amy", "zoe"]   # 40 > 20
    assert lb["contributors"][0]["points"] == 40.0


def test_empty_input():
    lb = sc.score_contributions([], now="2026-06-15")
    assert lb == {"updated": "2026-06-15", "contributors": []}


def test_malformed_manifest_skipped():
    subs = [_man("alice", "frames", "fusion", "r1"),
            {"submitted_by": "bob"},                  # no suite/claimed → skipped
            {"suite": "frames", "claimed": {"recipe": "x"}}]  # no submitted_by → skipped
    lb = sc.score_contributions(subs, now="2026-06-15")
    assert [c["user"] for c in lb["contributors"]] == ["alice"]


def test_null_run_id_sorts_as_empty():
    # explicit JSON null run_id must normalise to "" (lowest), not "None".
    # null sorts before "r1" → gets full 20; alice (r1) is second on the cell → 10.
    null_man = _man("ned", "frames", "fusion", "r1")
    null_man["run_id"] = None
    subs = [_man("alice", "frames", "fusion", "r1"), null_man]
    lb = sc.score_contributions(subs, now="2026-06-15")
    pts = {c["user"]: c["points"] for c in lb["contributors"]}
    assert pts == {"ned": 20.0, "alice": 10.0}


def test_load_submissions_reads_manifests(tmp_path):
    # build a fake submissions tree in tmp_path (hermetic — no real submissions/)
    d = tmp_path / "submissions" / "alice" / "r1"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps(_man("alice", "frames", "fusion", "r1")))
    bad = tmp_path / "submissions" / "bob" / "r2"
    bad.mkdir(parents=True)
    (bad / "manifest.json").write_text("{ not json")        # malformed → skipped, no crash
    subs = sc.load_submissions(tmp_path / "submissions")
    users = sorted(m["submitted_by"] for m in subs)
    assert users == ["alice"]                                # bob's broken json dropped


def test_load_submissions_missing_dir(tmp_path):
    subs = sc.load_submissions(tmp_path / "nope")            # absent dir → empty, no crash
    assert subs == []
