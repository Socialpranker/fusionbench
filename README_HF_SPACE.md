---
title: FusionBench
emoji: 🔭
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 6.18.0
app_file: app.py
pinned: false
---

# FusionBench — showcase

Read-only leaderboard + filterable recipe catalog over FusionBench results.

Data source (env): set `FUSIONBENCH_DATA_URL` to the Pages base URL, or
`FUSIONBENCH_DATA_DIR` to a local dir holding `leaderboard.json` + `data.json`.
Bundled demo fixtures live in `examples/` (`FUSIONBENCH_DATA_DIR=examples`).

> When deploying to a Space, this file becomes the Space `README.md`. The
> `gradio` + `huggingface_hub` + `httpx` deps come from `requirements.txt`.
