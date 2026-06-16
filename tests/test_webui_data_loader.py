import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from webui import data_loader as dl  # noqa: E402


def test_loads_local_file(tmp_path, monkeypatch):
    (tmp_path / "leaderboard.json").write_text(
        json.dumps({"contributors": [{"user": "a", "points": 1.0}]}))
    monkeypatch.setenv("FUSIONBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FUSIONBENCH_DATA_URL", raising=False)
    out = dl.load_leaderboard()
    assert out["contributors"][0]["user"] == "a"


def test_missing_local_falls_back_to_url(tmp_path, monkeypatch):
    monkeypatch.setenv("FUSIONBENCH_DATA_DIR", str(tmp_path))  # empty dir
    monkeypatch.setenv("FUSIONBENCH_DATA_URL", "https://example.test/fb")
    calls = []

    def fake_fetch(url, attempts=3):
        calls.append(url)
        return {"contributors": [{"user": "url", "points": 2.0}]}

    monkeypatch.setattr(dl, "_fetch_json_with_retry", fake_fetch)
    out = dl.load_leaderboard()
    assert out["contributors"][0]["user"] == "url"
    assert calls == ["https://example.test/fb/leaderboard.json"]


def test_both_sources_unavailable_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("FUSIONBENCH_DATA_DIR", str(tmp_path))  # empty
    monkeypatch.setenv("FUSIONBENCH_DATA_URL", "https://example.test/fb")
    monkeypatch.setattr(dl, "_fetch_json_with_retry", lambda url, attempts=3: None)
    assert dl.load_leaderboard() == {"contributors": []}
    assert dl.load_catalog() == {"cells": []}


def test_broken_json_returns_empty(tmp_path, monkeypatch, capsys):
    (tmp_path / "data.json").write_text("{not valid json")
    monkeypatch.setenv("FUSIONBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FUSIONBENCH_DATA_URL", raising=False)
    assert dl.load_catalog() == {"cells": []}
    assert "data.json" in capsys.readouterr().err  # logged to stderr


def test_fetch_retries_then_gives_up(monkeypatch):
    attempts_made = []

    class Boom(Exception):
        pass

    def always_fail(url, timeout):
        attempts_made.append(1)
        raise Boom("net down")

    monkeypatch.setattr(dl, "_http_get_json", always_fail)
    monkeypatch.setattr(dl.time, "sleep", lambda s: None)  # no real backoff in tests
    out = dl._fetch_json_with_retry("https://example.test/x.json", attempts=3)
    assert out is None
    assert len(attempts_made) == 3


def test_no_data_dir_uses_url(monkeypatch):
    # prod/HF Space case: no local dir, only the Pages URL is set.
    monkeypatch.delenv("FUSIONBENCH_DATA_DIR", raising=False)
    monkeypatch.setenv("FUSIONBENCH_DATA_URL", "https://example.test/fb")
    monkeypatch.setattr(dl, "_fetch_json_with_retry",
                        lambda url, attempts=3: {"cells": [{"type": "code"}]})
    out = dl.load_catalog()
    assert out["cells"][0]["type"] == "code"
