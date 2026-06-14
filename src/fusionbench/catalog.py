"""Catalog schema + writer. Each row = one (task_type, recipe) verdict.

This is the v1 product surface: a public, versioned table of fusion recipes per task
type. v0 writes the first rows so the schema is locked from day one.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class CatalogRow:
    suite: str
    task_type: str
    recipe: str
    arm: str
    n_tasks: int
    accuracy: float
    mean_tokens: float
    mean_cost_usd: float
    mean_latency_s: float
    worthiness_vs_best: float          # accuracy - best_single accuracy
    worthiness_vs_self_moa: float      # accuracy - self_moa accuracy (the real control)
    panel: list[str] = field(default_factory=list)
    judge: str | None = None
    synth: str | None = None
    complementarity: float | None = None
    oracle_coverage: float | None = None
    notes: str = ""
    ts: float = field(default_factory=lambda: round(time.time()))


def write_rows(path: str | Path, rows: list[CatalogRow]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")


def worthiness(acc: float, baseline: float) -> float:
    return round(acc - baseline, 4)
