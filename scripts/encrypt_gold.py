#!/usr/bin/env python3
"""Maintainer tool: encrypt gold/<suite>.jsonl -> gold/<suite>.jsonl.enc with Fernet.

    GOLD_DECRYPT_KEY=<base64-key> python scripts/encrypt_gold.py --suite ruler

Run after dump_gold.py. Commit ONLY the .enc file. Generate a key once with:
    python -c "from fusionbench.crypto import generate_key; print(generate_key().decode())"
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fusionbench.crypto import encrypt_bytes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True)
    args = ap.parse_args()

    key = os.environ.get("GOLD_DECRYPT_KEY")
    if not key:
        sys.exit("GOLD_DECRYPT_KEY not set")

    src = Path(f"gold/{args.suite}.jsonl")
    if not src.exists():
        sys.exit(f"{src} not found (run dump_gold.py first)")
    dst = src.with_suffix(".jsonl.enc")
    dst.write_bytes(encrypt_bytes(src.read_bytes(), key.encode()))
    print(f"encrypted {src} -> {dst}")


if __name__ == "__main__":
    main()
