# tests/test_regrade.py
import subprocess
import sys
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "regrade"
SCRIPT = Path(__file__).parent.parent / "scripts" / "regrade.py"


def _run(manifest, outputs):
    return subprocess.run(
        [sys.executable, str(SCRIPT),
         "--manifest", str(FIX / manifest),
         "--outputs", str(FIX / outputs),
         "--gold", str(FIX / "gold_ruler.jsonl")],
        capture_output=True, text=True,
    )


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
    import json
    bad = {"schema_version": 1, "suite": "ruler"}  # no "claimed"
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "scripts" / "validate_manifest.py"), str(p)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
