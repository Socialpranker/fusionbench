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


def main():
    ap = argparse.ArgumentParser(description="Publish FusionBench results as an HF Dataset.")
    ap.add_argument("--repo", required=True, help="dataset repo id, e.g. user/fusionbench-results")
    ap.add_argument("--source", default="site", help="dir holding leaderboard.json + data.json")
    ap.add_argument("--dry-run", action="store_true", help="print plan, do not touch network")
    args = ap.parse_args()

    # collect first: a missing source file is a hard error in both modes.
    try:
        files = collect_dataset_files(args.source)
    except FileNotFoundError as e:
        raise SystemExit(str(e))  # non-zero exit, not assert (survives python -O)

    if args.dry_run:
        publish(None, args.repo, files, dry_run=True)
        return

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN not set — export it or use --dry-run")

    from huggingface_hub import HfApi  # imported lazily: dry-run needs no hub install
    publish(HfApi(token=token), args.repo, files, dry_run=False)
    print(f"published {len(files)} files to dataset {args.repo}")


if __name__ == "__main__":
    main()
