"""Judge + prompt builders, with bias controls baked in.

Bias controls (Zheng et al. 2023; self-preference literature):
- order shuffle  -> position bias
- anonymized labels ("Candidate A") -> brand/self-preference bias
- cross-family judge check -> never let a model judge its own family
"""
from __future__ import annotations

import json
import random
import warnings

from .presets import MODELS


def family_of(slug: str) -> str:
    return MODELS[slug].family if slug in MODELS else slug.split("/")[0]


def check_judge_family(judge: str | None, panel: tuple[str, ...]) -> None:
    if judge and family_of(judge) in {family_of(p) for p in panel}:
        warnings.warn(
            f"judge {judge} shares a family with the panel -> self-preference risk; "
            "pick a cross-family judge.",
            stacklevel=2,
        )


def _labeled(question: str, panel_answers: dict[str, str], shuffle=True, anonymize=True):
    items = list(panel_answers.items())
    if shuffle:
        random.Random(question).shuffle(items)
    lines, mapping = [], {}
    for i, (model, ans) in enumerate(items):
        label = f"Candidate {chr(65 + i)}" if anonymize else model
        mapping[label] = model
        lines.append(f"{label}: {ans}")
    return "\n".join(lines), mapping


def build_judge_messages(question, panel_answers):
    body, _ = _labeled(question, panel_answers)
    sys = ("You are an impartial judge. Compare the candidate answers and return ONLY JSON "
           'with keys: best_answer, consensus, contradictions (list), unique_insights (list), '
           "blind_spots (list).")
    user = f"Question: {question}\n\nCandidates:\n{body}\n\nReturn only JSON."
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def build_aggregate_messages(question, samples):
    body = "\n".join(f"Sample {i+1}: {s}" for i, s in enumerate(samples))
    sys = "Given multiple samples from the same model, output the single most consistent final answer only."
    return [{"role": "system", "content": sys},
            {"role": "user", "content": f"Question: {question}\n\n{body}"}]


def build_synth_messages(question, judge_struct, panel_answers):
    sys = "Write the final answer, using the judge's analysis. Output only the answer."
    return [{"role": "system", "content": sys},
            {"role": "user", "content": f"Question: {question}\n\nJudge: {json.dumps(judge_struct)}"}]


def build_source_pool_messages(question, panel_answers):
    pooled = "\n".join(f"- {a}" for a in panel_answers.values())
    sys = "You are given the pooled findings of several models. Answer using them. Output only the answer."
    return [{"role": "system", "content": sys},
            {"role": "user", "content": f"Question: {question}\n\nPooled findings:\n{pooled}"}]


def parse_judge(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        return {"best_answer": text.strip(), "consensus": text.strip(),
                "contradictions": [], "unique_insights": [], "blind_spots": []}
