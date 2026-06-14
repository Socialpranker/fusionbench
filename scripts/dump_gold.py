#!/usr/bin/env python3
"""Maintainer tool: dump a suite's gold references to gold/<suite>.jsonl.

    python scripts/dump_gold.py --suite ruler --limit 150

The output is the held-out answer key. Encrypt it with encrypt_gold.py before committing;
never commit the plaintext gold/<suite>.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fusionbench.gold import example_to_gold
from fusionbench.tasks.registry import REGISTRY


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True, choices=sorted(REGISTRY))
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--out", default=None, help="default: gold/<suite>.jsonl")
    args = ap.parse_args()

    spec = REGISTRY[args.suite]
    examples = spec.loader.load(args.limit)
    out = Path(args.out or f"gold/{args.suite}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(example_to_gold(ex), ensure_ascii=False) + "\n")
    print(f"wrote {len(examples)} gold rows -> {out}")


if __name__ == "__main__":
    main()
