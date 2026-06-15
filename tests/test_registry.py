from __future__ import annotations

import pytest

from fusionbench.grading.base import Grader, Verdict
from fusionbench.tasks.base import Example, Loader
from fusionbench.tasks.registry import REGISTRY


def test_phase1_suites_present():
    assert {"frames", "ruler", "ifbench"} <= set(REGISTRY)


@pytest.mark.parametrize("suite", ["frames", "ruler", "ifbench"])
def test_spec_shape(suite):
    spec = REGISTRY[suite]
    assert isinstance(spec.loader, Loader)
    assert isinstance(spec.grader, Grader)
    assert "@" in spec.grader.name  # versioned
    assert spec.type and spec.license and spec.contamination_policy


@pytest.mark.parametrize("suite", ["ruler", "ifbench"])
def test_synthetic_loaders_offline(suite):
    """ruler/ifbench must load without network or `datasets` (phase-1 mock criterion)."""
    spec = REGISTRY[suite]
    examples = spec.loader.load(limit=4)
    assert len(examples) == 4
    assert all(isinstance(e, Example) and e.type == spec.type for e in examples)


def test_ruler_graded_by_its_grader():
    spec = REGISTRY["ruler"]
    ex = spec.loader.load(limit=1)[0]
    # the answer that contains the needle should pass
    v = spec.grader.score(f"the token is {ex.reference}", ex.reference, ex.metadata)
    assert isinstance(v, Verdict) and v.passed


def test_ifbench_graded_by_its_grader():
    spec = REGISTRY["ifbench"]
    ex = spec.loader.load(limit=1)[0]
    v = spec.grader.score("a black cat", ex.reference, ex.metadata)
    assert isinstance(v, Verdict)  # constraints evaluated, returns a verdict
