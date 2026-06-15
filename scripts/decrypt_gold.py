#!/usr/bin/env python3
"""CI tool: decrypt gold/<suite>.jsonl.enc -> gold/<suite>.jsonl using GOLD_DECRYPT_KEY.

    GOLD_DECRYPT_KEY=<key> python scripts/decrypt_gold.py --suite ruler

Exits non-zero (loudly) if the key is missing or wrong — never proceeds without gold.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fusionbench.crypto import decrypt_bytes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True)
    args = ap.parse_args()

    key = os.environ.get("GOLD_DECRYPT_KEY")
    if not key:
        sys.exit("GOLD_DECRYPT_KEY not set — cannot decrypt gold")

    enc = Path(f"gold/{args.suite}.jsonl.enc")
    if not enc.exists():
        sys.exit(f"{enc} not found")
    out = enc.with_suffix("")  # drops .enc -> gold/<suite>.jsonl
    try:
        out.write_bytes(decrypt_bytes(enc.read_bytes(), key.encode()))
    except Exception as e:
        sys.exit(f"decrypt failed (wrong key or tampered file): {e}")
    print(f"decrypted {enc} -> {out}")


if __name__ == "__main__":
    main()
