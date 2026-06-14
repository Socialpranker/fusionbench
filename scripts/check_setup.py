#!/usr/bin/env python3
"""Pre-flight before a live run.

    python scripts/check_setup.py          # checks key + available suites
    python scripts/check_setup.py --live   # also makes ONE cheap real call
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from fusionbench.tasks.browsecomp import DATA
from fusionbench.tasks.loaders import LOADERS


def main() -> None:
    key = os.environ.get("OPENROUTER_API_KEY")
    print("OPENROUTER_API_KEY:", "set" if key else "MISSING (real runs need it; use --mock otherwise)")
    print("built-in suites:", sorted(LOADERS), "(needs `pip install datasets`)")
    files = sorted(p.name for p in DATA.glob("*.jsonl")) if DATA.exists() else []
    print("local suite files in data/:", files or "(none)")

    if "--live" in sys.argv:
        if not key:
            print("cannot do --live without OPENROUTER_API_KEY")
            return
        from fusionbench.client import OpenRouterClient

        async def ping() -> None:
            c = OpenRouterClient()
            try:
                r = await c.chat("google/gemini-3-flash",
                                 [{"role": "user", "content": "Reply with the single word OK."}],
                                 max_tokens=5)
                print(f"live call ok | tokens={r.usage.total} | text={r.text[:40]!r}")
            finally:
                await c.aclose()

        asyncio.run(ping())


if __name__ == "__main__":
    main()
