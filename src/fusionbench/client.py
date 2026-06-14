"""LLM access. One real client (OpenRouter), one deterministic mock for offline runs.

Both expose the same coroutine:
    chat(model, messages, *, temperature, max_tokens, kind, mock_ctx) -> ChatResponse

`kind` and `mock_ctx` are ignored by the real client; the mock uses them to produce
deterministic, skill-weighted outputs so the whole harness runs with no API key.
"""
from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass

from .config import Usage
from . import presets


@dataclass
class ChatResponse:
    text: str
    usage: Usage


def _seed(*parts: object) -> random.Random:
    """Stable across processes (unlike builtin hash) so mock runs are reproducible."""
    digest = hashlib.md5("::".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(digest[:12], 16))


def _short(model: str) -> str:
    return model.split("/")[-1]


def _distractor(task: dict, model: str) -> str:
    return f"WRONG[{task['id']}:{_short(model)}]"


class MockClient:
    """Deterministic, dependency-free. Skill table lives in presets (illustrative)."""

    async def chat(self, model, messages, *, temperature=0.7, max_tokens=512,
                   kind="answer", mock_ctx=None) -> ChatResponse:
        ctx = mock_ctx or {}
        task = ctx.get("task", {"id": "x", "type": "factual", "gold": "GOLD", "question": ""})
        ttype, gold = task["type"], task["gold"]
        prompt_tok = 20 + len(str(task.get("question", ""))) // 4

        if kind == "answer":
            p = presets.SKILL.get(model, {}).get(ttype, 0.5)
            ok = _seed(model, task["id"], "ans").random() < p
            text = gold if ok else _distractor(task, model)
            return ChatResponse(text, Usage(prompt_tok, 70 + _seed(model, task["id"]).randint(0, 40)))

        if kind == "aggregate":  # self-moa: majority vote over samples
            samples = ctx.get("samples", [])
            text = _majority(samples) if samples else gold
            return ChatResponse(text, Usage(30, 25))

        if kind == "judge":  # fusion: pick best_answer + structured analysis
            panel: dict[str, str] = ctx.get("panel", {})
            vals = list(panel.values())
            consensus = _majority(vals)
            gold_present = gold in vals
            jp = presets.SKILL.get(model, {}).get(ttype, 0.5)
            if gold_present and _seed(model, task["id"], "judge").random() < jp:
                best = gold
            else:
                best = consensus
            import json
            struct = {
                "best_answer": best,
                "consensus": consensus,
                "contradictions": sorted({v for v in vals if v != consensus}),
                "unique_insights": [],
                "blind_spots": [],
            }
            return ChatResponse(json.dumps(struct), Usage(prompt_tok + 60, 140))

        if kind == "synth":  # fusion final: write the chosen answer
            judge = ctx.get("judge", {})
            best = judge.get("best_answer", gold)
            sp = presets.SKILL.get(model, {}).get(ttype, 0.6)
            text = best if _seed(model, task["id"], "synth").random() < sp else _distractor(task, model)
            return ChatResponse(text, Usage(prompt_tok + 40, 110))

        if kind == "source_pool":  # union of panel finds, one strong generation
            panel: dict[str, str] = ctx.get("panel", {})
            best_model = ctx.get("single", presets.BEST_SINGLE)
            gold_present = gold in panel.values()
            base = presets.SKILL.get(best_model, {}).get(ttype, 0.6)
            if gold_present:
                p = min(0.98, base + presets.COVERAGE_BOOST.get(ttype, 0.0))
            else:
                p = base * 0.6  # sources didn't surface it -> best model mostly alone
            text = gold if _seed(best_model, task["id"], "sp").random() < p else _distractor(task, best_model)
            return ChatResponse(text, Usage(prompt_tok + 30, 90))

        raise ValueError(f"unknown kind: {kind}")


class OpenRouterClient:
    """Real calls. One key, all models. Requires httpx + OPENROUTER_API_KEY."""

    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set (use --mock to run offline)")
        import httpx
        self._http = httpx.AsyncClient(timeout=120)

    async def chat(self, model, messages, *, temperature=0.7, max_tokens=512,
                   kind="answer", mock_ctx=None) -> ChatResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": os.environ.get("OPENROUTER_APP_URL", "https://localhost"),
            "X-Title": os.environ.get("OPENROUTER_APP_TITLE", "FusionBench"),
        }
        payload = {"model": model, "messages": messages,
                   "temperature": temperature, "max_tokens": max_tokens}
        r = await self._http.post(self.URL, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        u = data.get("usage", {})
        return ChatResponse(text, Usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0)))

    async def aclose(self) -> None:
        await self._http.aclose()


def _majority(items: list[str]) -> str:
    if not items:
        return ""
    counts: dict[str, int] = {}
    for it in items:
        counts[it] = counts.get(it, 0) + 1
    best = max(items, key=lambda it: (counts[it], -items.index(it)))
    return best
