# FusionBench

![CI](https://github.com/Socialpranker/fusionbench/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)

**When is multi-model "fusion" actually worth it — and which combo, for which task?**

Most "council of models" tools assume mixing models beats a single strong model. The literature says otherwise: aggregating *N* samples of the best single model (Self-MoA) often beats mixing weaker ones at equal compute. FusionBench measures this honestly, then turns the answer into a maintained, public **recipe catalog** for model *combinations* per task type.

## The bet (what's actually new)

The insight "fusion configs vary by task" is already published (FusionFactory), and config search exists (ARCHON). FusionBench's two contributions, which *compose*:

1. A transparent, maintained **catalog of fusion recipes per task type** — "Artificial Analysis for ensembles." Routers hide this; academia buries it in trained policies.
2. A cheap **complementarity prefilter** (error-decorrelation) that prunes the candidate combos so the catalog is affordable to keep fresh. ARCHON has no such prefilter.

## v0 — the contrarian result (this skeleton)

One verifiable suite, five arms at a **matched token budget**:

| arm | what |
|---|---|
| `best-single` | strongest single model, 1 pass |
| `self-moa` | same model × N samples, aggregated — **the control** |
| `fusion-cheap` | panel of 3 cheap models → judge → synthesizer |
| `fusion-strong` | panel of strong models → judge → synthesizer |
| `source-pool` | union of the panel's sources → fed to `best-single` (isolates the *coverage* hypothesis) |

Headline outputs: a cost-quality Pareto point per arm, and two yes/no answers — *does fusion beat self-moa at matched compute?* and *does source-pooling close the gap?* (If yes to the second, fusion's win is web coverage, not collective reasoning.)

## Run

```bash
# 1) offline dry run — no key, canned responses, proves the pipeline + stats
python scripts/run_v0.py --mock --limit 40

# 2) real run — one key, all models via OpenRouter
pip install -e ".[dev]"              # add the `datasets` package too for --suite frames
cp .env.example .env                 # add OPENROUTER_API_KEY
python scripts/check_setup.py --live # verify key + one cheap live call
python scripts/run_v0.py --suite frames --budget 6000 --limit 150          # HF FRAMES
python scripts/run_v0.py --suite mysuite --limit 150                       # or data/mysuite.jsonl
```

Suites: `frames` (HuggingFace), or any `data/<name>.jsonl` of `{id, type, question, gold, aliases?}`.
Output: catalog rows in `runs/catalog.jsonl` + a cost-quality summary and the two headline answers.

## Layout

```
src/fusionbench/
  config.py          recipe + result dataclasses
  presets.py         model slugs, cheap/strong panels, the 5 v0 recipes
  client.py          async OpenRouter client (+ deterministic mock)
  budget.py          token accounting, matched-budget (picks N for self-moa)
  solvers.py         the 5 arms (async)
  judge.py           structured judge with order-shuffle + anonymize bias controls
  scoring.py         verifiable grader (normalized match)
  complementarity.py error-decorrelation / focal-diversity prefilter (pure, tested)
  catalog.py         catalog row schema + JSONL writer
  tasks/browsecomp.py  loader (ships a tiny sample; swap in the real set)
scripts/run_v0.py    orchestrates the arms, scores, writes catalog
tests/               pure-function unit tests (budget, complementarity)
```

## Develop & ship

```bash
make install   # editable install + dev deps
make test      # unit tests (also run in CI on Python 3.10/3.11/3.12)
make run       # mock catalog -> runs/catalog.jsonl
make site      # rebuild site/index.html from runs/*.jsonl
```

- `.github/workflows/ci.yml` runs the test matrix on every push / PR.
- `.github/workflows/pages.yml` rebuilds the catalog and deploys `site/` to GitHub Pages
  on push to `main` (enable Pages → "GitHub Actions" in repo settings). With no committed
  `runs/*.jsonl` it publishes an illustrative mock catalog; commit real runs to replace it.

## Honest caveats

- **Mock numbers are illustrative.** The mock client returns canned text so the pipeline runs offline; it does not say anything about real models.
- **Runner.** v0 uses a small custom async runner — fine for one number. At v1 scale, wrap the arms as Inspect AI solvers (`[inspect]` extra) for parallelism, cost logging, and CIs instead of growing this.
- **Grading.** v0 sticks to *verifiable* suites (no LLM judge) so the result is unarguable. Rubric/judge grading for deep-research reports is a v1 addition — and when added, never let a model judge its own family (self-preference bias).
- **The prefilter** currently needs a small labeled probe slice (focal diversity / error Jaccard). A label-free predictor for generation tasks is the open research stretch.

See `docs/DESIGN.md` for the full reasoning and sources.

## Submitting a run

See [submissions/README.md](submissions/README.md). CI re-grades your saved
`outputs.jsonl` against a private gold key; an inflated accuracy fails the check.
