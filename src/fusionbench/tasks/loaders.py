"""Suite loading: built-in datasets + generic JSONL + mock synth.

A task is {id, type, question, gold, aliases?}. `type` groups catalog rows and (mock
only) selects skill; the real client ignores it.

    --suite frames           -> HuggingFace google/frames-benchmark (needs `datasets`)
    --suite <name>           -> data/<name>.jsonl (drop your own verifiable suite)
    --mock (no file)         -> synthetic balanced probes
"""
from __future__ import annotations

import json
from pathlib import Path

from .browsecomp import synth_tasks, DATA


def load_jsonl(path: Path, limit: int) -> list[dict]:
    rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return rows[:limit]


def load_frames(limit: int, split: str = "test") -> list[dict]:
    """FRAMES: multi-hop retrieval+reasoning, near exact-match answers. HF-hosted."""
    try:
        from datasets import load_dataset
    except ImportError as e:
        raise RuntimeError("`pip install datasets` to use --suite frames") from e
    ds = load_dataset("google/frames-benchmark", split=split)
    out = []
    for i, r in enumerate(ds):
        if i >= limit:
            break
        out.append({
            "id": f"frames-{i:04d}",
            "type": "multihop_qa",
            "question": r.get("Prompt") or r.get("prompt") or r.get("question"),
            "gold": str(r.get("Answer") or r.get("answer") or "").strip(),
            "aliases": [],
        })
    return out


LOADERS = {"frames": load_frames}


def load_tasks(suite: str, limit: int, mock: bool) -> list[dict]:
    if suite in LOADERS:
        return LOADERS[suite](limit)
    path = DATA / f"{suite}.jsonl"
    if path.exists():
        return load_jsonl(path, limit)
    if not mock:
        raise FileNotFoundError(
            f"no loader or file for suite '{suite}'. Known: {sorted(LOADERS)} or data/{suite}.jsonl. "
            "Pass --mock for a dry run."
        )
    return synth_tasks(limit)
