"""Load leaderboard.json / data.json: local file first, then Pages-URL fallback.

Network is wrapped in retry (HAPP flaky TLS). Any failure degrades to an empty
structure so the UI shows an honest empty-state instead of crashing.
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

_EMPTY = {"leaderboard.json": {"contributors": []}, "data.json": {"cells": []}}


def _http_get_json(url, timeout):
    """Single HTTP GET returning parsed JSON. Raises on any failure."""
    resp = httpx.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _fetch_json_with_retry(url, attempts=3):
    """GET url with N attempts and exponential backoff. Returns dict or None."""
    delay = 0.5
    for i in range(attempts):
        try:
            return _http_get_json(url, timeout=10.0)
        except Exception as e:  # noqa: BLE001 — network/parse, degrade gracefully
            print(f"fetch {url} attempt {i + 1}/{attempts} failed: {e}", file=sys.stderr)
            if i < attempts - 1:
                time.sleep(delay)
                delay *= 2
    return None


def _load(filename):
    """Local FUSIONBENCH_DATA_DIR/<file>, else FUSIONBENCH_DATA_URL/<file>, else empty."""
    empty = _EMPTY[filename]
    data_dir = os.environ.get("FUSIONBENCH_DATA_DIR")
    if data_dir:
        path = os.path.join(data_dir, filename)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:  # noqa: BLE001
                print(f"{filename}: bad local JSON ({e}); using empty", file=sys.stderr)
                return empty
    base_url = os.environ.get("FUSIONBENCH_DATA_URL")
    if base_url:
        fetched = _fetch_json_with_retry(f"{base_url.rstrip('/')}/{filename}")
        if fetched is not None:
            return fetched
    return empty


def load_leaderboard():
    return _load("leaderboard.json")


def load_catalog():
    return _load("data.json")
