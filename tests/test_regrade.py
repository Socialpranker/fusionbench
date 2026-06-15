# tests/test_regrade.py
import json
import subprocess
import sys
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "regrade"
SCRIPT = Path(__file__).parent.parent / "scripts" / "regrade.py"
GOLD = FIX / "gold_ruler.jsonl"


def _run(manifest, outputs):
    return subprocess.run(
        [sys.executable, str(SCRIPT),
         "--manifest", str(FIX / manifest),
         "--outputs", str(FIX / outputs),
         "--gold", str(GOLD)],
        capture_output=True, text=True,
    )


def _run_paths(manifest_path, outputs_path):
    return subprocess.run(
        [sys.executable, str(SCRIPT),
         "--manifest", str(manifest_path),
         "--outputs", str(outputs_path),
         "--gold", str(GOLD)],
        capture_output=True, text=True,
    )


def _honest_rows():
    return [json.loads(ln) for ln in (FIX / "outputs_honest.jsonl").read_text().splitlines() if ln.strip()]


def _honest_manifest():
    return json.loads((FIX / "manifest_honest.json").read_text())


def _write(tmp_path, manifest, rows):
    mp = tmp_path / "manifest.json"
    op = tmp_path / "outputs.jsonl"
    mp.write_text(json.dumps(manifest))
    op.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return mp, op


def test_honest_submission_passes():
    r = _run("manifest_honest.json", "outputs_honest.jsonl")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_tampered_accuracy_fails():
    # outputs_tampered.jsonl is byte-identical to honest — the cheat is the inflated
    # accuracy in the manifest, not altered outputs (you can't fake the graded reference).
    r = _run("manifest_tampered.json", "outputs_tampered.jsonl")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "accuracy" in (r.stdout + r.stderr).lower()


def test_cost_anomaly_is_warning_not_failure(tmp_path):
    # honest outputs, but manifest claims an absurdly low cost -> WARN, still exit 0
    import json
    man = json.loads((FIX / "manifest_honest.json").read_text())
    man["claimed"]["cost_usd"] = man["claimed"]["cost_usd"] / 100.0
    p = tmp_path / "manifest_low_cost.json"
    p.write_text(json.dumps(man))
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--manifest", str(p),
         "--outputs", str(FIX / "outputs_honest.jsonl"),
         "--gold", str(FIX / "gold_ruler.jsonl")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "WARN" in (r.stdout + r.stderr)


def test_validate_manifest_accepts_honest():
    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "scripts" / "validate_manifest.py"),
         str(FIX / "manifest_honest.json")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_validate_manifest_rejects_missing_field(tmp_path):
    bad = {"schema_version": 1, "suite": "ruler"}  # no "claimed"
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "scripts" / "validate_manifest.py"), str(p)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0


# --- Anti-cheat coverage: re-grade must score the FULL held-out slice, not a
# submitter-chosen subset, and must reject duplicate gold_ids. Without these guards a
# submitter cherry-picks the rows their run got right (or pads with duplicates of one
# correct row) and forges any accuracy. gold_ruler.jsonl has 12 ids; honest run is 4/12.


def test_cherry_picked_subset_fails(tmp_path):
    # Keep only the 4 correct rows, claim 4/4 = 100%. Each row grades passed and its
    # gold_id exists, so the old gate passed — but the slice is incomplete (4 of 12).
    correct = [r for r in _honest_rows() if r["gold_id"] in
               {"ruler-0000", "ruler-0003", "ruler-0006", "ruler-0009"}]
    assert len(correct) == 4
    man = _honest_manifest()
    man["claimed"]["accuracy"] = 1.0
    man["claimed"]["n"] = 4
    mp, op = _write(tmp_path, man, correct)
    r = _run_paths(mp, op)
    assert r.returncode != 0, "cherry-picked subset must be rejected\n" + r.stdout + r.stderr
    assert "coverage" in (r.stdout + r.stderr).lower()


def test_duplicate_gold_ids_rejected(tmp_path):
    # One correct row repeated 12x: claims n=12, accuracy=1.0. Every gid exists in gold,
    # so the old per-row counting passed. Duplicate gold_ids must be rejected.
    one = next(r for r in _honest_rows() if r["gold_id"] == "ruler-0000")
    rows = [dict(one) for _ in range(12)]
    man = _honest_manifest()
    man["claimed"]["accuracy"] = 1.0
    man["claimed"]["n"] = 12
    mp, op = _write(tmp_path, man, rows)
    r = _run_paths(mp, op)
    assert r.returncode != 0, "duplicate gold_ids must be rejected\n" + r.stdout + r.stderr
    assert "duplicate" in (r.stdout + r.stderr).lower()


def test_full_coverage_no_duplicates_still_passes(tmp_path):
    # Guard against over-zealous rejection: the honest full 12/12 run (no dups, complete
    # coverage) must still pass after the coverage/dedup checks are added.
    rows = _honest_rows()
    man = _honest_manifest()
    mp, op = _write(tmp_path, man, rows)
    r = _run_paths(mp, op)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


@pytest.mark.xfail(
    strict=True,
    reason="KNOWN LIMITATION: prediction is submitter-controlled and graders are lenient "
    "by design, so a submitter who knows the gold answer forges a pass. Defeating this "
    "needs client-signed outputs or server-side execution, not a check in regrade.py. "
    "If this test starts XPASSing, a real defense was added — update the trust-model "
    "docstring in scripts/regrade.py.",
)
def test_forged_prediction_is_a_known_limitation(tmp_path):
    # Full coverage, no duplicates, but every prediction is set to its own gold needle —
    # a forged 100%. The honest run scored 4/12; this forges 12/12. regrade cannot tell a
    # real answer from a copied one, so it passes (returncode 0) — which xfail records as
    # the accepted residual risk, NOT a regression.
    gold = {json.loads(ln)["id"]: json.loads(ln)
            for ln in GOLD.read_text().splitlines() if ln.strip()}
    rows = []
    for r in _honest_rows():
        forged = dict(r)
        forged["prediction"] = gold[r["gold_id"]]["reference"]  # write in the gold needle
        rows.append(forged)
    man = _honest_manifest()
    man["claimed"]["accuracy"] = 1.0  # forged perfect score
    mp, op = _write(tmp_path, man, rows)
    r = _run_paths(mp, op)
    # The assertion encodes the DESIRED behavior (forgery rejected); xfail records that
    # the current design does not achieve it.
    assert r.returncode != 0, "forged prediction was not caught\n" + r.stdout + r.stderr
