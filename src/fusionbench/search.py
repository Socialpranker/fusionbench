"""Prefilter-driven recipe search — the trick that makes the catalog cheap.

Brute force = evaluate every {panel x judge x synth} on the full set. Instead:
  stage 1 (cheap)  run each candidate MODEL once on a small probe slice -> per-model
                   correctness -> complementarity of each candidate panel.
  stage 2 (paid)   fully evaluate ONLY the top-k panels by complementarity, plus the
                   best-single / self-moa baselines.

Per task type the shortlist differs, because complementarity is task-dependent.
"""
from __future__ import annotations

import asyncio
from itertools import combinations

from .config import RecipeConfig, Usage
from .scoring import is_correct
from .judge import family_of
from .presets import MODELS
from . import complementarity as C


def candidate_panels(pool, size: int = 3) -> list[tuple[str, ...]]:
    return list(combinations(tuple(pool), size))


def pick_judge(panel: tuple[str, ...],
               preferred=("anthropic/claude-opus-4.8", "openai/gpt-5.5", "google/gemini-3-pro")) -> str:
    """A capable judge whose family is NOT in the panel (self-preference control).
    Falls back to any other-family model in the registry before ever returning a
    same-family judge."""
    panel_fams = {family_of(p) for p in panel}
    for j in preferred:
        if family_of(j) not in panel_fams:
            return j
    for slug in MODELS:                       # registry fallback: clean but maybe weaker
        if family_of(slug) not in panel_fams:
            return slug
    return preferred[0]                        # panel spans every known family


async def probe_correctness(client, probe_tasks, pool):
    """Stage 1: one call per (model, probe task). Returns
    {task_type: {model: [bool, ...]}} (aligned by task order) and total Usage."""
    from .solvers import _q
    jobs = [(t, m) for t in probe_tasks for m in pool]
    resps = await asyncio.gather(*[
        client.chat(m, _q(t["question"]), kind="answer", mock_ctx={"task": t}) for (t, m) in jobs
    ])
    by_type: dict[str, dict[str, list[bool]]] = {}
    usage = Usage()
    for (t, m), r in zip(jobs, resps):
        usage.add(r.usage)
        ok = is_correct(r.text, t["gold"], t.get("aliases"))
        by_type.setdefault(t["type"], {}).setdefault(m, []).append(ok)
    return by_type, usage


def shortlist_for_type(correctness, pool, *, panel_size=3, k=2, synth, best, n_self_moa):
    """Return (recipes, ranked_panels, n_candidates) for one task type."""
    panels = candidate_panels(pool, panel_size)
    ranked = C.prefilter_panels(panels, correctness, k=k)
    recipes = [
        RecipeConfig("best-single", "best_single", single=best, topology="single"),
        RecipeConfig("self-moa", "self_moa", single=best, n_samples=n_self_moa, topology="self_moa"),
    ]
    for idx, (panel, _score) in enumerate(ranked):
        recipes.append(RecipeConfig(
            f"fusion-top{idx + 1}", "fusion", panel=panel,
            judge=pick_judge(panel), synth=synth, topology="panel_judge_synth",
        ))
    if ranked:
        recipes.append(RecipeConfig(
            "source-pool", "source_pool", panel=ranked[0][0], single=best, topology="source_pool",
        ))
    return recipes, ranked, len(panels)
