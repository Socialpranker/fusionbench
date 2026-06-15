# tests/test_submit_workflow.py
"""Behavioural tests for the shell logic in .github/workflows/submit.yml.

The workflow's `run:` block is shell, not Python, so we can't import it. Instead we
extract the exact command lines from the YAML and execute them under bash with adversarial
inputs, asserting on real side effects (a marker file the injection would create, the diff
revision the anti-cheat actually resolves). A regression that reintroduces a hole turns the
relevant test red because the test runs the workflow's own text.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "submit.yml"


def _workflow_text():
    return WORKFLOW.read_text()


def _extract_suite_assignment():
    """The `suite=$(python ... manifest.json ...)` line that reads the claimed suite."""
    for line in _workflow_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("suite=") and "manifest.json" in stripped:
            return stripped
    raise AssertionError("no `suite=...manifest.json...` line found in submit.yml")


def _extract_sed_pipe():
    """The `sed -E ...` line that collapses changed file paths to submission dirs."""
    for line in _workflow_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("| sed -E") or stripped.startswith("sed -E"):
            return stripped.lstrip("| ").rstrip(")")
    raise AssertionError("no `sed -E` line found in submit.yml")


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_suite_extraction_is_not_command_injectable(tmp_path):
    # An attacker controls the submission path. They commit a directory whose name closes
    # the Python string literal and runs code. If $dir is interpolated into `python -c`,
    # this touches the marker (RCE on a runner that holds GOLD_DECRYPT_KEY). The fixed form
    # passes the path via argv, so the name is inert data and no marker appears.
    marker = tmp_path / "PWNED"
    evil_dir = (
        "submissions/a/run'+__import__('os').system('touch "
        + str(marker)
        + "')+'"
    )
    # Give the literal path a real manifest too, so a *fixed* (argv) command still finds a
    # file to open — the test must isolate "injection fires" from "file missing".
    honest_dir = tmp_path / "submissions" / "a" / "run"
    honest_dir.mkdir(parents=True)
    (honest_dir / "manifest.json").write_text('{"suite": "ruler"}')

    # The workflow calls the interpreter as bare `python`; this host only has python3 in a
    # venv. Bind `python` to the real interpreter so the test exercises the injection itself,
    # not a "python: command not found" that would mask it (a false green).
    suite_line = _extract_suite_assignment()
    script = f'python() {{ {sys.executable} "$@"; }}\ndir="{evil_dir}"\n{suite_line}\n'
    subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=tmp_path)

    assert not marker.exists(), (
        "command injection fired: $dir was interpolated into `python -c`.\n"
        f"line under test: {suite_line}"
    )


def _invocation_line(script_name):
    """Line index of the actual `python scripts/<name>` call, ignoring comment mentions."""
    for i, line in enumerate(_workflow_text().splitlines()):
        stripped = line.lstrip()
        if stripped.startswith("python ") and f"scripts/{script_name}" in stripped:
            return i
    raise AssertionError(f"no `python scripts/{script_name}` invocation in submit.yml")


def test_suite_is_validated_against_registry_before_decrypt():
    # decrypt_gold.py runs with GOLD_DECRYPT_KEY in env. A claimed suite must be checked
    # against the allowlist (validate_manifest / REGISTRY) BEFORE decrypt, so an unknown or
    # crafted suite never reaches the key-bearing step. Compare the real invocation lines,
    # not bare substring mentions (a comment naming decrypt would skew text.index).
    validate_line = _invocation_line("validate_manifest.py")
    decrypt_line = _invocation_line("decrypt_gold.py")
    assert validate_line < decrypt_line, (
        "validate_manifest.py (suite allowlist) must run before decrypt_gold.py — "
        "otherwise an unvetted suite reaches the GOLD_DECRYPT_KEY step"
    )


def test_checkout_fetches_full_history():
    # The diff uses three-dot `origin/$BASE_REF...HEAD`, which needs the merge-base. With the
    # default shallow checkout (depth=1) the merge-base is unreachable: the diff either dies
    # (set -e kills the job on a valid PR) or returns empty (anti-cheat SILENTLY skipped, a
    # padded submission merges green). checkout must fetch full history.
    text = _workflow_text()
    assert "fetch-depth: 0" in text, (
        "actions/checkout must use fetch-depth: 0 — three-dot diff needs the merge-base, "
        "unreachable on a shallow clone"
    )


def test_base_fetch_is_not_shallow():
    # `git fetch origin "$BASE_REF" --depth=1` re-narrows the base to a single commit even if
    # checkout fetched everything, again breaking the merge-base. The base fetch must be full.
    for line in _workflow_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("git fetch") and "BASE_REF" in stripped:
            assert "--depth" not in stripped, (
                "base fetch must not be shallow (--depth) — it breaks the three-dot "
                f"merge-base: {stripped}"
            )
            break
    else:
        raise AssertionError("no `git fetch ... BASE_REF` line found in submit.yml")


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_three_dot_diff_needs_merge_base(tmp_path):
    # Behavioural proof of why full history matters: a shallow clone of only the PR branch
    # cannot resolve origin/main...HEAD (no merge-base), while a full clone can. This is the
    # mechanism the two config tests above guard against.
    def git(*a, cwd, check=True):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=check)

    origin = tmp_path / "origin"
    origin.mkdir()
    git("init", "-q", "-b", "main", cwd=origin)
    git("config", "user.email", "t@t.t", cwd=origin)
    git("config", "user.name", "t", cwd=origin)
    (origin / "README.md").write_text("base\n")
    git("add", "-A", cwd=origin)
    git("commit", "-q", "-m", "base1", cwd=origin)
    git("checkout", "-q", "-b", "pr", cwd=origin)
    sub = origin / "submissions" / "b" / "run2"
    sub.mkdir(parents=True)
    (sub / "manifest.json").write_text("{}")
    git("add", "-A", cwd=origin)
    git("commit", "-q", "-m", "pr adds submission", cwd=origin)
    git("checkout", "-q", "main", cwd=origin)
    (origin / "README.md").write_text("base\nmore\n")  # base moves ahead independently
    git("add", "-A", cwd=origin)
    git("commit", "-q", "-m", "base2", cwd=origin)

    url = f"file://{origin}"

    # Shallow clone of just the PR branch — like actions/checkout default + fetch --depth=1.
    shallow = tmp_path / "shallow"
    git("clone", "-q", "--depth=1", "--branch", "pr", url, str(shallow), cwd=tmp_path)
    git("fetch", "-q", "origin", "main", "--depth=1", cwd=shallow)
    r = git("diff", "--name-only", "origin/main...HEAD", "--", "submissions/**",
            cwd=shallow, check=False)
    assert r.returncode != 0, "expected shallow three-dot diff to fail on the missing merge-base"

    # Full clone — like fetch-depth: 0.
    full = tmp_path / "full"
    git("clone", "-q", "--branch", "pr", url, str(full), cwd=tmp_path)
    git("fetch", "-q", "origin", "main", cwd=full)
    r = git("diff", "--name-only", "origin/main...HEAD", "--", "submissions/**", cwd=full)
    assert r.stdout.strip() == "submissions/b/run2/manifest.json", (
        "full-history three-dot diff should list exactly the PR's submission, got: "
        + repr(r.stdout)
    )


def test_loop_guards_against_missing_manifest():
    # The loop body must skip a $dir with no manifest.json. Without the guard, a docs PR
    # touching submissions/README.md (3 segments — sed's >=4-segment pattern leaves it
    # untouched) or a deleted/renamed submission (stale path in the diff) makes the loop
    # open a nonexistent manifest, and set -e fails CI on otherwise-valid input.
    text = _workflow_text()
    in_loop = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("for dir in"):
            in_loop = True
        if in_loop and "manifest.json" in stripped and "-f" in stripped and "continue" in stripped:
            return
    raise AssertionError(
        "loop must guard `[ -f \"$dir/manifest.json\" ] || continue` — otherwise a "
        "short path (submissions/README.md) or a deleted submission crashes CI under set -e"
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_sed_plus_guard_filters_non_submission_paths(tmp_path):
    # Behavioural: run the workflow's own sed pipe over a realistic changed-files list, then
    # apply the guard, and confirm only real submission dirs survive. README.md and a deleted
    # submission must drop out without error; the valid submission must be kept.
    (tmp_path / "submissions" / "a" / "run1").mkdir(parents=True)
    (tmp_path / "submissions" / "a" / "run1" / "manifest.json").write_text("{}")
    (tmp_path / "submissions" / "README.md").write_text("docs")
    # submissions/old/gone/manifest.json is NOT created — simulates a deleted submission whose
    # path still appears in `git diff --name-only`.

    changed_files = (
        "submissions/README.md\n"
        "submissions/a/run1/manifest.json\n"
        "submissions/a/run1/outputs.jsonl\n"
        "submissions/old/gone/manifest.json\n"
    )
    sed_pipe = _extract_sed_pipe()
    script = (
        f"set -euo pipefail\n"
        f'changed=$(printf %s "$1" | {sed_pipe} | sort -u)\n'
        f"for dir in $changed; do\n"
        f'  [ -f "$dir/manifest.json" ] || continue\n'
        f'  echo "$dir"\n'
        f"done\n"
    )
    r = subprocess.run(["bash", "-c", script, "bash", changed_files],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, "guarded loop must not fail on README/deleted paths\n" + r.stderr
    processed = r.stdout.split()
    assert processed == ["submissions/a/run1"], (
        "only the real submission dir should be processed, got: " + repr(processed)
    )
