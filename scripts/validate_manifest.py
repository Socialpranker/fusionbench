#!/usr/bin/env python3
"""Validate a submission manifest: required fields, types, and cost plausibility (WARN).

    python scripts/validate_manifest.py submissions/<user>/<run_id>/manifest.json

Structural problems (missing/wrong-typed fields, unknown suite) -> exit 1.
Cost implausibility -> WARN, exit 0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fusionbench.tasks.registry import REGISTRY

_REQUIRED = ["schema_version", "run_id", "submitted_by", "suite", "claimed"]
_CLAIMED_REQUIRED = {"recipe": str, "accuracy": (int, float), "cost_usd": (int, float), "n": int}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    args = ap.parse_args()

    try:
        man = json.loads(Path(args.manifest).read_text())
    except Exception as e:
        sys.exit(f"cannot parse manifest: {e}")

    for key in _REQUIRED:
        if key not in man:
            sys.exit(f"manifest missing required field {key!r}")

    if man["suite"] not in REGISTRY:
        sys.exit(f"unknown suite {man['suite']!r} (not in REGISTRY)")

    claimed = man["claimed"]
    for key, typ in _CLAIMED_REQUIRED.items():
        if key not in claimed:
            sys.exit(f"manifest.claimed missing {key!r}")
        # bool is a subclass of int, so isinstance(True, int) and isinstance(True, float)
        # are both True — a JSON `true` would slip past the type and range gates below
        # ("n": true -> True > 0, "accuracy": true -> 0 <= True <= 1). Reject it explicitly.
        if isinstance(claimed[key], bool):
            sys.exit(f"manifest.claimed.{key} must not be a boolean")
        if not isinstance(claimed[key], typ):
            sys.exit(f"manifest.claimed.{key} must be {typ}, got {type(claimed[key]).__name__}")

    if not (0.0 <= claimed["accuracy"] <= 1.0):
        sys.exit(f"accuracy out of range: {claimed['accuracy']}")
    if claimed["n"] <= 0:
        sys.exit(f"n must be positive: {claimed['n']}")

    # cost plausibility — WARN only
    if claimed["cost_usd"] < 0:
        print(f"WARN cost: negative cost_usd {claimed['cost_usd']}")
    elif claimed["cost_usd"] == 0:
        print("WARN cost: claimed cost_usd is 0 (implausible for a real run)")

    print(f"OK manifest valid: suite={man['suite']} recipe={claimed['recipe']} n={claimed['n']}")


if __name__ == "__main__":
    main()
