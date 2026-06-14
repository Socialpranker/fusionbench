from fusionbench.complementarity import (
    error_jaccard, pair_complementarity, focal_diversity,
    oracle_coverage, prefilter_panels,
)


def test_disjoint_errors_are_complementary():
    a = [True, False, True]
    b = [False, True, True]
    assert error_jaccard(a, b) == 0.0          # errors never overlap
    assert pair_complementarity(a, b) == 1.0


def test_identical_errors_are_redundant():
    a = [True, False, False]
    b = [True, False, False]
    assert error_jaccard(a, b) == 1.0
    assert pair_complementarity(a, b) == 0.0


def test_oracle_coverage():
    c = {"m1": [True, False, False], "m2": [False, True, False]}
    assert abs(oracle_coverage(c, ("m1", "m2")) - 2 / 3) < 1e-9


def test_focal_diversity_recovers_errors():
    c = {"m1": [True, False], "m2": [False, True]}
    assert focal_diversity(c, ("m1", "m2")) == 1.0


def test_prefilter_ranks_complementary_panel_first():
    c = {
        "a": [True, False, True, False],
        "b": [False, True, False, True],   # disjoint with a
        "d": [True, False, True, False],   # identical to a
    }
    ranked = prefilter_panels([("a", "d"), ("a", "b")], c, k=2)
    assert ranked[0][0] == ("a", "b")
