"""Per-(task × recipe) raw outputs — the artifact CI re-grades without re-calling LLMs.

Distinct from catalog.py (aggregate rows): this saves the raw prediction, the panel
answers and the grading verdict so a saved run can be scored again later against a
versioned grader (see grading.Grader.name).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import ArmResult
from .grading.base import Verdict
from .tasks.base import Example


def output_record(
    run_id: str,
    example: Example,
    recipe: str,
    res: ArmResult,
    verdict: Verdict,
    grader_name: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "task_id": example.id,
        "type": example.type,
        "recipe": recipe,
        "prediction": res.answer,
        "panel": res.panel_answers,
        "judge": res.judge,
        "claimed_correct": verdict.passed,
        "prompt_tokens": res.usage.prompt_tokens,
        "completion_tokens": res.usage.completion_tokens,
        "cost_usd": res.cost_usd,
        "grader": grader_name,
        "gold_id": example.id,
    }


def write_outputs(path: str | Path, records: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
