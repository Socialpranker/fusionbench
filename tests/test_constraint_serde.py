# tests/test_constraint_serde.py
from fusionbench.grading.constraint import (
    Constraint, constraint_to_dict, constraint_from_dict, make_constraint,
)


def test_make_constraint_exactly_words():
    c = make_constraint("exactly_words", n=3)
    assert c.check("one two three") is True
    assert c.check("one two") is False


def test_roundtrip_exactly_words():
    c = make_constraint("exactly_words", n=3)
    d = constraint_to_dict(c)
    assert d == {"kind": "exactly_words", "params": {"n": 3}}
    c2 = constraint_from_dict(d)
    # restored predicate behaves identically
    for s in ["a b c", "a b", "x y z w"]:
        assert c2.check(s) == c.check(s)


def test_roundtrip_contains():
    c = make_constraint("contains", word="moon")
    d = constraint_to_dict(c)
    assert d == {"kind": "contains", "params": {"word": "moon"}}
    c2 = constraint_from_dict(d)
    for s in ["the MOON is up", "sun only", ""]:
        assert c2.check(s) == c.check(s)


def test_roundtrip_all_caps():
    c = make_constraint("all_caps")
    d = constraint_to_dict(c)
    assert d == {"kind": "all_caps", "params": {}}
    c2 = constraint_from_dict(d)
    for s in ["HELLO", "Hello", "123"]:
        assert c2.check(s) == c.check(s)


def test_unknown_kind_raises():
    import pytest
    with pytest.raises(KeyError):
        make_constraint("no_such_kind")
    with pytest.raises(KeyError):
        constraint_from_dict({"kind": "no_such_kind", "params": {}})


def test_ifbench_loader_constraints_serializable():
    from fusionbench.tasks.ifbench import IFBenchLoader
    examples = IFBenchLoader().load(limit=3)
    assert len(examples) == 3
    # probes hit both branches of each kind: a 3-word lowercase string, an all-caps
    # string, and the literal "cat"/"ocean" words that make `contains` fire True.
    probes = ["HELLO WORLD", "one two three", "cat", "the ocean is wide"]
    for ex in examples:
        for c in ex.reference:
            d = constraint_to_dict(c)             # must not raise (kind present)
            c2 = constraint_from_dict(d)
            for s in probes:
                assert c2.check(s) == c.check(s)
