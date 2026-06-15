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
