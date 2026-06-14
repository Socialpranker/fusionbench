"""Task loading.

A task is a dict: {id, type, question, gold}. `type` is one of presets.TASK_TYPES.
Real runs: drop a verifiable suite at data/<suite>.jsonl (same shape).
Mock runs: synthetic balanced probes so the pipeline + stats are exercised.
"""
from __future__ import annotations

import json
import string
from pathlib import Path

from ..presets import TASK_TYPES

DATA = Path(__file__).resolve().parents[3] / "data"


def _letters(i: int) -> str:
    """0->a, 1->b, ... 26->aa. Keeps synthetic gold non-numeric so the numeric
    grader can't false-positive on shared task-id digits."""
    i += 1
    s = ""
    while i:
        i, r = divmod(i - 1, 26)
        s = string.ascii_lowercase[r] + s
    return s


def synth_tasks(n: int) -> list[dict]:
    tasks = []
    for i in range(n):
        ttype = TASK_TYPES[i % len(TASK_TYPES)]
        tasks.append({
            "id": f"t{i:04d}",
            "type": ttype,
            "question": f"[{ttype}] synthetic probe #{i}",
            "gold": f"gold-{_letters(i)}",
        })
    return tasks


def load_tasks(suite: str, limit: int, mock: bool) -> list[dict]:
    path = DATA / f"{suite}.jsonl"
    if path.exists():
        rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return rows[:limit]
    if not mock:
        raise FileNotFoundError(
            f"no suite file at {path}. Add a verifiable suite there, or pass --mock for a dry run."
        )
    return synth_tasks(limit)
