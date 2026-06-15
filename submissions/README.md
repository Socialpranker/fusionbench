# Submissions

Each submission is a directory `submissions/<github_user>/<run_id>/` with:

- `manifest.json` — claimed recipe, accuracy, cost_usd, n, suite, grader.
- `outputs.jsonl` — raw per-(task × recipe) outputs from your run.

On PR, `.github/workflows/submit.yml` re-grades your saved outputs against the
held-out gold answer key and **fails if the claimed accuracy does not match** the
re-graded value (tolerance ±1%). Cost is checked for plausibility (warning only).

Generate outputs with `scripts/run_v0.py` (writes `runs/outputs.jsonl`), then copy the
single recipe you're claiming into your submission directory along with a manifest.
