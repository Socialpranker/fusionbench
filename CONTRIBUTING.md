# Contributing

Thanks for looking. FusionBench is small and wants to stay legible.

## Dev setup

```bash
pip install -e ".[dev]"
pytest -q
```

## Common tasks (see `Makefile`)

```bash
make test     # run unit tests
make run      # mock v0 run -> runs/catalog.jsonl
make search   # mock prefilter recipe search
make site     # rebuild site/index.html from runs/*.jsonl
```

## Add a task suite

Drop `data/<name>.jsonl`, one object per line:

```json
{"id": "q1", "type": "deep_research", "question": "...", "gold": "...", "aliases": ["..."]}
```

Then `python scripts/run_v0.py --suite <name> --limit 150`. `type` groups catalog rows;
grading stays verifiable (no LLM judge) — keep golds short and checkable.

## Principles (please keep)

- **Matched compute.** Any "fusion beats X" claim compares at equal token budget.
- **No self-judging.** A judge must not share a model family with the panel it scores.
- **Verifiable first.** Prefer checkable grading over an LLM judge; when a judge is
  unavoidable, control position/verbosity/self-preference bias and meta-validate it.
- **Report when fusion is NOT worth it.** Negative results are the point, not a failure.
