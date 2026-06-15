from __future__ import annotations

import json

from fusionbench.config import ArmResult, Usage
from fusionbench.grading.base import Verdict
from fusionbench.runs import output_record, write_outputs
from fusionbench.tasks.base import Example

_REQUIRED_FIELDS = {
    "run_id", "task_id", "type", "recipe", "prediction", "panel", "judge",
    "claimed_correct", "prompt_tokens", "completion_tokens", "cost_usd", "grader", "gold_id",
}


def _fixture_record():
    ex = Example(id="frames-0007", prompt="q?", reference="1969", type="multihop_qa")
    res = ArmResult(
        recipe="fusion-strong",
        arm="fusion",
        answer="1969",
        usage=Usage(prompt_tokens=812, completion_tokens=143),
        cost_usd=0.0041,
        panel_answers={"a/b": "1969", "c/d": "1969"},
        judge={"best_answer": "1969"},
    )
    verdict = Verdict(passed=True, score=1.0)
    return output_record("2026-06-14T10-00Z_ab12", ex, "fusion-strong", res, verdict, "ExactMatch@1")


def test_record_has_all_spec_fields():
    rec = _fixture_record()
    assert _REQUIRED_FIELDS <= set(rec)


def test_record_values_mapped():
    rec = _fixture_record()
    assert rec["task_id"] == "frames-0007"
    assert rec["gold_id"] == "frames-0007"
    assert rec["type"] == "multihop_qa"
    assert rec["prediction"] == "1969"
    assert rec["panel"] == {"a/b": "1969", "c/d": "1969"}
    assert rec["claimed_correct"] is True
    assert rec["prompt_tokens"] == 812
    assert rec["completion_tokens"] == 143
    assert rec["cost_usd"] == 0.0041
    assert rec["grader"] == "ExactMatch@1"


def test_write_outputs_appends_valid_jsonl(tmp_path):
    path = tmp_path / "sub" / "outputs.jsonl"
    write_outputs(path, [_fixture_record()])
    write_outputs(path, [_fixture_record()])  # append, not overwrite
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["task_id"] == "frames-0007"
