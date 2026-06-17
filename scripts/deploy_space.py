"""Deploy the FusionBench showcase to a Hugging Face Space.

The Space runtime is app.py + webui/ + requirements.txt; data is NOT bundled —
the Space pulls leaderboard.json + data.json over HTTP from FUSIONBENCH_DATA_URL
(the GitHub Pages base), set here as a Space variable. README_HF_SPACE.md is
uploaded as the Space's README.md so HF reads the YAML config (sdk, sdk_version,
app_file) from it.

Token comes from the HF_TOKEN env var only — never an argument, never committed.
Use --dry-run to print the plan without touching the network.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# (local_path, path_in_repo). The HF Space README must be README.md so HF parses
# its YAML front-matter; we keep the source as README_HF_SPACE.md to avoid clashing
# with the project README.md. webui/*.py are the runtime modules app.py imports.
def collect_space_files():
    """[(local_path, path_in_repo)] for the Space runtime. Raises if anything is missing."""
    mapping = [
        ("app.py", "app.py"),
        ("requirements.txt", "requirements.txt"),
        ("README_HF_SPACE.md", "README.md"),
    ]
    out = []
    for local_rel, repo_path in mapping:
        local = _REPO_ROOT / local_rel
        if not local.exists():
            raise FileNotFoundError(f"{local} not found — cannot deploy Space")
        out.append((str(local), repo_path))

    webui = _REPO_ROOT / "webui"
    py_files = sorted(p for p in webui.glob("*.py"))  # skip __pycache__, only sources
    if not py_files:
        raise FileNotFoundError(f"no webui/*.py under {webui} — cannot deploy Space")
    for p in py_files:
        out.append((str(p), f"webui/{p.name}"))
    return out


def _retry(fn, what, attempts=3):
    """Call fn() with N attempts + exponential backoff (HAPP flaky TLS to HF/GitHub)."""
    delay = 0.5
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — network, retry then re-raise
            print(f"{what} attempt {i + 1}/{attempts} failed: {e}", file=sys.stderr)
            if i == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2


def deploy(api, repo_id, files, data_url, dry_run):
    """Create the Space (idempotent), set FUSIONBENCH_DATA_URL, upload runtime files."""
    if dry_run:
        print(f"[dry-run] would deploy Space {repo_id} (sdk=gradio):")
        print(f"  variable FUSIONBENCH_DATA_URL = {data_url}")
        for local, repo_path in files:
            print(f"  {local} -> {repo_path}")
        return

    _retry(lambda: api.create_repo(repo_id, repo_type="space", space_sdk="gradio",
                                   exist_ok=True), "create_repo")
    # public URL, not a secret -> a Space variable (visible in Settings), not a secret.
    _retry(lambda: api.add_space_variable(repo_id, "FUSIONBENCH_DATA_URL", data_url),
           "add_space_variable")
    for local, repo_path in files:
        _retry(lambda lo=local, rp=repo_path: api.upload_file(
            path_or_fileobj=lo, path_in_repo=rp, repo_id=repo_id, repo_type="space"),
            f"upload {repo_path}")


def main():
    ap = argparse.ArgumentParser(description="Deploy the FusionBench showcase to an HF Space.")
    ap.add_argument("--repo", required=True, help="space repo id, e.g. user/fusionbench")
    ap.add_argument("--data-url", required=True,
                    help="FUSIONBENCH_DATA_URL the Space fetches data.json/leaderboard.json from")
    ap.add_argument("--dry-run", action="store_true", help="print plan, do not touch network")
    args = ap.parse_args()

    # collect first: a missing runtime file is a hard error in both modes.
    try:
        files = collect_space_files()
    except FileNotFoundError as e:
        raise SystemExit(str(e))  # non-zero exit, not assert (survives python -O)

    if args.dry_run:
        deploy(None, args.repo, files, args.data_url, dry_run=True)
        return

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN not set — export it or use --dry-run")

    from huggingface_hub import HfApi  # lazy: dry-run needs no hub install
    deploy(HfApi(token=token), args.repo, files, args.data_url, dry_run=False)
    print(f"deployed {len(files)} files to Space {args.repo} "
          f"-> https://huggingface.co/spaces/{args.repo}")


if __name__ == "__main__":
    main()
