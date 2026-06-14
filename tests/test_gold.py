# tests/test_gold.py
import json

from fusionbench.gold import example_to_gold, gold_to_reference
from fusionbench.tasks.registry import REGISTRY


def _roundtrip_suite(suite):
    spec = REGISTRY[suite]
    examples = spec.loader.load(limit=3)
    for ex in examples:
        row = example_to_gold(ex)
        # row must be JSON-serializable
        json.dumps(row)
        assert row["id"] == ex.id
        assert row["type"] == ex.type
        reference, metadata = gold_to_reference(suite, row)
        # grading with the restored reference matches grading with the original
        for pred in ["NEEDLE-AAA", "HELLO WORLD", "one two three", "anything else"]:
            v1 = spec.grader.score(pred, ex.reference, ex.metadata)
            v2 = spec.grader.score(pred, reference, metadata)
            assert v1.passed == v2.passed, (suite, ex.id, pred)


def test_gold_roundtrip_ruler():
    _roundtrip_suite("ruler")


def test_gold_roundtrip_ifbench():
    _roundtrip_suite("ifbench")


def test_gold_roundtrip_frames_string_reference():
    # frames loader hits the network; build a synthetic string-reference Example instead.
    from fusionbench.tasks.base import Example
    from fusionbench.gold import example_to_gold, gold_to_reference
    ex = Example(id="frames-0001", prompt="q", reference="Paris",
                 type="multihop_qa", metadata={"aliases": ["paris, france"]})
    row = example_to_gold(ex)
    assert row["reference"] == "Paris"
    assert row["metadata"] == {"aliases": ["paris, france"]}
    reference, metadata = gold_to_reference("frames", row)
    assert reference == "Paris"
    assert metadata == {"aliases": ["paris, france"]}
