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
