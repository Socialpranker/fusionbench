from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .base import Verdict


@dataclass(frozen=True)
class Constraint:
    """One checkable instruction-following rule. `describe_text` surfaces in the verdict
    so a failed submission shows *which* rule broke. `kind`/`params` let the constraint
    serialize to gold and rebuild its predicate via CONSTRAINT_FACTORIES — the predicate
    itself is a lambda and cannot be stored as JSON."""

    describe_text: str
    predicate: Callable[[str], bool]
    kind: str = ""
    params: dict = field(default_factory=dict)

    def check(self, prediction: str) -> bool:
        return self.predicate(prediction)

    def describe(self) -> str:
        return self.describe_text


def _exactly_words(n: int) -> Constraint:
    return Constraint(f"exactly {n} words", lambda p, n=n: len(p.split()) == n,
                      kind="exactly_words", params={"n": n})


def _contains(word: str) -> Constraint:
    return Constraint(f"contains '{word}'", lambda p, w=word: w.lower() in p.lower(),
                      kind="contains", params={"word": word})


def _all_caps() -> Constraint:
    return Constraint("all uppercase",
                      lambda p: p.strip() == p.strip().upper() and any(c.isalpha() for c in p),
                      kind="all_caps", params={})


# kind -> factory. Single source of truth for building and rebuilding constraints.
CONSTRAINT_FACTORIES: dict[str, Callable[..., Constraint]] = {
    "exactly_words": _exactly_words,
    "contains": _contains,
    "all_caps": _all_caps,
}


def make_constraint(kind: str, **params: Any) -> Constraint:
    """Build a constraint by registered kind. Raises KeyError on unknown kind."""
    return CONSTRAINT_FACTORIES[kind](**params)


def constraint_to_dict(c: Constraint) -> dict:
    """Serialize to gold form. Requires the constraint to carry a registered `kind`."""
    if not c.kind:
        raise ValueError(f"constraint {c.describe_text!r} has no kind; cannot serialize")
    return {"kind": c.kind, "params": dict(c.params)}


def constraint_from_dict(d: dict) -> Constraint:
    """Rebuild from gold form via the factory registry."""
    return make_constraint(d["kind"], **d.get("params", {}))


class ConstraintGrader:
    """IFBench-style: score = fraction of constraints satisfied; passed only if all are."""

    name = "Constraint@1"

    def score(self, prediction: str, reference: Any, metadata: dict) -> Verdict:
        constraints: list[Constraint] = list(reference or [])
        if not constraints:
            return Verdict(passed=True, score=1.0, detail="no constraints")

        failed = [c for c in constraints if not c.check(prediction)]
        score = (len(constraints) - len(failed)) / len(constraints)
        detail = "" if not failed else "failed: " + "; ".join(c.describe() for c in failed)
        return Verdict(passed=not failed, score=round(score, 4), detail=detail)
