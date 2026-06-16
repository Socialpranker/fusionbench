"""Publish FusionBench results as a Hugging Face Dataset.

results dataset = leaderboard.json + data.json (snapshot of Phase 4 outputs).
Token comes from the HF_TOKEN env var only — never an argument, never committed.
Use --dry-run to print the upload plan without touching the network.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_RESULTS_FILES = ["leaderboard.json", "data.json"]


def collect_dataset_files(source_dir):
    """[(local_path, path_in_repo)] for the results dataset. Raises if any file missing."""
    out = []
    for name in _RESULTS_FILES:
        local = Path(source_dir) / name
        if not local.exists():
            raise FileNotFoundError(
                f"{local} not found — generate artifacts first "
                f"(scripts/score_contributions.py, scripts/build_catalog.py)")
        out.append((str(local), name))
    return out


def publish(api, repo_id, files, dry_run, attempts=3):
    """Create the dataset repo (idempotent) and upload each file. dry_run prints only."""
    if dry_run:
        print(f"[dry-run] would publish dataset {repo_id}:")
        for local, repo_path in files:
            print(f"  {local} -> {repo_path}")
        return
    api.create_repo(repo_id, repo_type="dataset", exist_ok=True)
    for local, repo_path in files:
        delay = 0.5
        for i in range(attempts):
            try:
                api.upload_file(path_or_fileobj=local, path_in_repo=repo_path,
                                repo_id=repo_id, repo_type="dataset")
                break
            except Exception as e:  # noqa: BLE001 — network, retry then re-raise
                print(f"upload {repo_path} attempt {i + 1}/{attempts} failed: {e}",
                      file=sys.stderr)
                if i == attempts - 1:
                    raise
                time.sleep(delay)
                delay *= 2
