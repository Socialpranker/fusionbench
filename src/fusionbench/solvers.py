"""The five v0 arms as async functions. Panel members run in parallel."""
from __future__ import annotations

import asyncio
import time

from .config import ArmResult, RecipeConfig, Usage
from . import judge as J
from .budget import cost_usd
from .presets import MODELS


def _cost(model: str, usage: Usage) -> float:
    spec = MODELS.get(model)
    return cost_usd(usage, spec) if spec else 0.0


def _q(question: str):
    return [{"role": "user", "content": question}]


async def run_best_single(client, task, recipe: RecipeConfig) -> ArmResult:
    t0 = time.perf_counter()
    r = await client.chat(recipe.single, _q(task["question"]), kind="answer", mock_ctx={"task": task})
    u = Usage(); u.add(r.usage)
    return ArmResult(recipe.name, recipe.arm, r.text, usage=u,
                     cost_usd=_cost(recipe.single, r.usage), latency_s=time.perf_counter() - t0)


async def run_self_moa(client, task, recipe: RecipeConfig) -> ArmResult:
    t0 = time.perf_counter()
    samples = await asyncio.gather(*[
        client.chat(recipe.single, _q(task["question"]), temperature=0.9, kind="answer", mock_ctx={"task": task})
        for _ in range(recipe.n_samples)
    ])
    u, cost = Usage(), 0.0
    for s in samples:
        u.add(s.usage); cost += _cost(recipe.single, s.usage)
    texts = [s.text for s in samples]
    agg = await client.chat(recipe.single, J.build_aggregate_messages(task["question"], texts),
                            kind="aggregate", mock_ctx={"task": task, "samples": texts})
    u.add(agg.usage); cost += _cost(recipe.single, agg.usage)
    return ArmResult(recipe.name, recipe.arm, agg.text, usage=u, cost_usd=cost,
                     latency_s=time.perf_counter() - t0,
                     panel_answers={f"sample_{i}": t for i, t in enumerate(texts)})


async def _panel(client, task, panel):
    resps = await asyncio.gather(*[
        client.chat(m, _q(task["question"]), kind="answer", mock_ctx={"task": task}) for m in panel
    ])
    answers = {m: r.text for m, r in zip(panel, resps)}
    u, cost = Usage(), 0.0
    for m, r in zip(panel, resps):
        u.add(r.usage); cost += _cost(m, r.usage)
    return answers, u, cost


async def run_fusion(client, task, recipe: RecipeConfig) -> ArmResult:
    t0 = time.perf_counter()
    J.check_judge_family(recipe.judge, recipe.panel)
    answers, u, cost = await _panel(client, task, recipe.panel)

    jr = await client.chat(recipe.judge, J.build_judge_messages(task["question"], answers),
                           kind="judge", mock_ctx={"task": task, "panel": answers})
    u.add(jr.usage); cost += _cost(recipe.judge, jr.usage)
    jstruct = J.parse_judge(jr.text)

    sr = await client.chat(recipe.synth, J.build_synth_messages(task["question"], jstruct, answers),
                           kind="synth", mock_ctx={"task": task, "judge": jstruct, "panel": answers})
    u.add(sr.usage); cost += _cost(recipe.synth, sr.usage)

    return ArmResult(recipe.name, recipe.arm, sr.text, usage=u, cost_usd=cost,
                     latency_s=time.perf_counter() - t0, panel_answers=answers, judge=jstruct)


async def run_source_pool(client, task, recipe: RecipeConfig) -> ArmResult:
    t0 = time.perf_counter()
    answers, u, cost = await _panel(client, task, recipe.panel)
    r = await client.chat(recipe.single, J.build_source_pool_messages(task["question"], answers),
                          kind="source_pool",
                          mock_ctx={"task": task, "panel": answers, "single": recipe.single})
    u.add(r.usage); cost += _cost(recipe.single, r.usage)
    return ArmResult(recipe.name, recipe.arm, r.text, usage=u, cost_usd=cost,
                     latency_s=time.perf_counter() - t0, panel_answers=answers)


_DISPATCH = {
    "best_single": run_best_single,
    "self_moa": run_self_moa,
    "fusion": run_fusion,
    "source_pool": run_source_pool,
}


async def run_arm(client, task, recipe: RecipeConfig) -> ArmResult:
    return await _DISPATCH[recipe.arm](client, task, recipe)
