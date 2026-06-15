from __future__ import annotations

import importlib.util

import pytest

from fusionbench.grading import (
    Constraint,
    ConstraintGrader,
    ExactMatchGrader,
    NumericGrader,
    SyntheticGrader,
    Verdict,
)

_HAS_SYMPY = importlib.util.find_spec("sympy") is not None


class TestExactMatch:
    g = ExactMatchGrader()

    def test_name_is_versioned(self):
        assert self.g.name == "ExactMatch@1"

    def test_exact(self):
        v = self.g.score("Paris", "paris", {})
        assert v.passed and v.score == 1.0

    def test_alias(self):
        v = self.g.score("USA", "United States", {"aliases": ["USA", "US"]})
        assert v.passed

    def test_substring(self):
        v = self.g.score("The answer is 1969.", "1969", {})
        assert v.passed

    def test_wrong(self):
        v = self.g.score("Berlin", "Paris", {})
        assert not v.passed and v.score == 0.0


class TestNumeric:
    g = NumericGrader()

    def test_name_is_versioned(self):
        assert self.g.name == "Numeric@1"

    def test_boxed_match(self):
        v = self.g.score(r"so the result is \boxed{42}", "42", {})
        assert v.passed

    def test_last_number_match(self):
        v = self.g.score("after simplification we get 3.14", "3.14", {})
        assert v.passed

    def test_tolerance(self):
        v = self.g.score("approximately 2.0000001", "2", {})
        assert v.passed

    def test_wrong_number(self):
        v = self.g.score("the answer is 7", "8", {})
        assert not v.passed

    def test_no_number_fails(self):
        v = self.g.score("there is no number here", "5", {})
        assert not v.passed

    @pytest.mark.skipif(not _HAS_SYMPY, reason="sympy not installed")
    def test_symbolic_equivalence(self):
        v = self.g.score("1/2", "0.5", {})
        assert v.passed


class TestSynthetic:
    g = SyntheticGrader()

    def test_name_is_versioned(self):
        assert self.g.name == "Synthetic@1"

    def test_exact_needle(self):
        v = self.g.score("The magic word is BANANA.", "BANANA", {})
        assert v.passed

    def test_missing_needle(self):
        v = self.g.score("I could not find it.", "BANANA", {})
        assert not v.passed


class TestConstraint:
    g = ConstraintGrader()

    @staticmethod
    def _exactly_n_words(n: int) -> Constraint:
        return Constraint(
            describe_text=f"exactly {n} words",
            predicate=lambda p, n=n: len(p.split()) == n,
        )

    @staticmethod
    def _contains(word: str) -> Constraint:
        return Constraint(
            describe_text=f"contains '{word}'",
            predicate=lambda p, w=word: w.lower() in p.lower(),
        )

    def test_name_is_versioned(self):
        assert self.g.name == "Constraint@1"

    def test_all_satisfied(self):
        cons = [self._exactly_n_words(3), self._contains("cat")]
        v = self.g.score("a black cat", cons, {})
        assert v.passed and v.score == 1.0

    def test_partial(self):
        cons = [self._exactly_n_words(3), self._contains("dog")]
        v = self.g.score("a black cat", cons, {})
        assert not v.passed and v.score == 0.5

    def test_detail_names_failed_constraint(self):
        cons = [self._contains("dog")]
        v = self.g.score("a black cat", cons, {})
        assert "dog" in v.detail


def test_all_graders_return_verdict():
    for g, pred, ref, meta in [
        (ExactMatchGrader(), "x", "x", {}),
        (NumericGrader(), "1", "1", {}),
        (SyntheticGrader(), "x", "x", {}),
        (ConstraintGrader(), "x", [], {}),
    ]:
        assert isinstance(g.score(pred, ref, meta), Verdict)
