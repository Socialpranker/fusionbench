# Фаза 5 — HF Space-витрина Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить read-only Gradio-витрину (доска лидеров + табличный каталог с фильтрами + экспорт) поверх готовых `leaderboard.json`/`data.json`, запускаемую одним `app.py` локально и на HF Space, плюс CLI выгрузки results-dataset на HF.

**Architecture:** Тонкий `app.py` в корне (сборка Gradio Blocks) + пакет `webui/` рядом в корне (чистые loader/transform/export, тестируются без Gradio) + отдельный CLI `scripts/publish_datasets.py`. Данные читаются из локального файла с URL-fallback на Pages (сеть в retry). Следуем проектному паттерну «чистое ядро + I/O + CLI».

**Tech Stack:** Python ≥3.10, Gradio, huggingface_hub, httpx (уже есть), pytest. Интерпретатор — `.venv/bin/python`.

---

## Грабли проекта (читать перед стартом)

- **Интерпретатор — `.venv/bin/python`**, НЕ `python` (его нет на PATH). pytest: `.venv/bin/python -m pytest -q`.
- **Baseline сейчас:** 91 passed, 1 skipped, 1 xfailed. Новые тесты добавляются, старые остаются зелёными.
- **`webui/` кладём в КОРЕНЬ** рядом с `app.py` (не в `src/`). `app.py` обязан быть в корне — требование HF Space.
- **Тесты импортируют код вне `src/` через `sys.path.insert`** (паттерн `test_score_contributions.py`). Для `webui/` и `scripts/` — `sys.path.insert(0, str(ROOT))` / `str(ROOT / "scripts")`.
- **`conftest.py` в `tests/` НЕТ.** `pyproject.toml` даёт `pythonpath = ["src"]` только для `src/`-пакетов.
- **НЕ класть seed в `submissions/`** — ломает regrade-чек Фазы 2. Демо-данные — в `examples/` (вне submissions/, не в gitignore).
- **Даты/`now` — снаружи** (CLI/ENV), не генерим в Python (детерминизм).
- **Целостность/обязательные проверки — через `exit`/`raise SystemExit`, не `assert`** (assert снимается `python -O`).
- **Сеть — в retry** (HAPP рвёт TLS). `curl`/`sleep` могут быть недоступны в sandbox-bash — для веб-проверки Playwright MCP.
- **gitignore:** новые `app.py`, `webui/`, `examples/`, `requirements.txt` НЕ игнорируются. Осторожно только с `site/*`.
- **Ветка уже `phase5-hf-space`**, спек закоммичен (`6ee3754`). Коммиты на русском, conventional, `git add` по файлам. Co-Authored-By: `Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## Структура файлов

**Создаём:**
- `webui/__init__.py` — пустой маркер пакета
- `webui/data_loader.py` — `load_leaderboard()`, `load_catalog()`, `_fetch_json_with_retry()`
- `webui/transform.py` — `filter_catalog()`, `to_leaderboard_df()`, `to_catalog_df()`, `slider_bounds()`
- `webui/export.py` — `rows_to_csv_bytes()`, `rows_to_json_bytes()`
- `app.py` — Gradio Blocks UI, проводка событий, `demo.launch()`
- `scripts/publish_datasets.py` — `collect_dataset_files()`, `publish()`, `main()`
- `examples/leaderboard.json`, `examples/data.json` — демо-фикстуры
- `requirements.txt` — пины для HF Space
- `README_HF_SPACE.md` — заготовка README Space с YAML-хедером
- `tests/test_webui_data_loader.py`, `tests/test_webui_transform.py`, `tests/test_webui_export.py`, `tests/test_publish_datasets.py`

**Модифицируем:**
- `pyproject.toml:12-15` — добавить опц-группу `space`

---

# ЭТАП 1 — Read-only витрина

## Task 1: Опц-группа зависимостей `space` в pyproject.toml

**Files:**
- Modify: `pyproject.toml:12-15`

- [ ] **Step 1: Добавить группу `space` в optional-dependencies**

В `pyproject.toml` секцию `[project.optional-dependencies]` (строки 12-15) привести к:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0"]
# v1 scale-out: wrap the arms as Inspect solvers for parallelism + logging.
inspect = ["inspect-ai>=0.3"]
# Phase 5: HF Space showcase (Gradio leaderboard + HF Datasets export). httpx reused from core.
space = ["gradio>=4.44", "huggingface_hub>=0.25"]
```

- [ ] **Step 2: Установить группу и проверить, что gradio импортируется**

Run: `.venv/bin/pip install -e ".[space]" && .venv/bin/python -c "import gradio, huggingface_hub; print(gradio.__version__, huggingface_hub.__version__)"`
Expected: печатает версии без ImportError (gradio ≥4.44, huggingface_hub ≥0.25).

- [ ] **Step 3: Прогнать baseline-тесты — ничего не сломалось**

Run: `.venv/bin/python -m pytest -q`
Expected: 91 passed, 1 skipped, 1 xfailed (как было).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: опц-группа зависимостей space (gradio + huggingface_hub) для Фазы 5"
```

---

## Task 2: `webui/transform.py` — фильтрация каталога

**Files:**
- Create: `webui/__init__.py`
- Create: `webui/transform.py`
- Test: `tests/test_webui_transform.py`

Контракт `data.json` cells (из `build_catalog.py`): `{type, recipe, arm, accuracy, cost_usd, latency_s, worthiness_vs_best, worthiness_vs_self_moa, complementarity (может null), recommended, n}`.

- [ ] **Step 1: Написать падающий тест фильтрации и сортировки**

Создать `tests/test_webui_transform.py`:

```python
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from webui import transform as tr  # noqa: E402


def _cells():
    return [
        {"type": "code", "recipe": "best-single", "arm": "best_single", "accuracy": 0.90,
         "cost_usd": 0.001, "worthiness_vs_best": 0.0, "complementarity": None, "n": 12},
        {"type": "code", "recipe": "fusion-strong", "arm": "fusion", "accuracy": 0.95,
         "cost_usd": 0.010, "worthiness_vs_best": 0.05, "complementarity": 0.9, "n": 12},
        {"type": "math", "recipe": "fusion-strong", "arm": "fusion", "accuracy": 0.70,
         "cost_usd": 0.004, "worthiness_vs_best": -0.02, "complementarity": 0.3, "n": 8},
    ]


def test_filter_by_type():
    out = tr.filter_catalog(_cells(), type="code", maxcost=1.0, minacc=0.0, sort="accuracy")
    assert {c["type"] for c in out} == {"code"}
    assert len(out) == 2


def test_filter_by_maxcost():
    out = tr.filter_catalog(_cells(), type="", maxcost=0.005, minacc=0.0, sort="cost")
    assert all(c["cost_usd"] <= 0.005 for c in out)
    assert len(out) == 2


def test_filter_by_minacc():
    out = tr.filter_catalog(_cells(), type="", maxcost=1.0, minacc=0.90, sort="accuracy")
    assert all(c["accuracy"] >= 0.90 for c in out)
    assert len(out) == 2


def test_sort_cost_ascending():
    out = tr.filter_catalog(_cells(), type="", maxcost=1.0, minacc=0.0, sort="cost")
    costs = [c["cost_usd"] for c in out]
    assert costs == sorted(costs)


def test_sort_worthiness_desc_nulls_last():
    # complementarity sort: None must land at the end, deterministically.
    out = tr.filter_catalog(_cells(), type="", maxcost=1.0, minacc=0.0, sort="worthiness")
    worth = [c["worthiness_vs_best"] for c in out]
    assert worth == sorted(worth, reverse=True)


def test_empty_input_returns_empty():
    assert tr.filter_catalog([], type="", maxcost=1.0, minacc=0.0, sort="accuracy") == []
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_webui_transform.py -q`
Expected: FAIL (ModuleNotFoundError: No module named 'webui').

- [ ] **Step 3: Создать пакет и реализовать `filter_catalog`**

Создать `webui/__init__.py` (пустой файл).

Создать `webui/transform.py`:

```python
"""Pure catalog transforms for the Gradio showcase: filter, sort, to-DataFrame.

No Gradio import here — everything is testable as plain functions.
"""
from __future__ import annotations

_SORT_KEYS = {
    "worthiness": ("worthiness_vs_best", True),
    "accuracy": ("accuracy", True),
    "cost": ("cost_usd", False),
    "recipe": ("recipe", False),
}


def filter_catalog(cells, type, maxcost, minacc, sort):
    """Filter catalog cells by type/maxcost/minacc, then sort.

    `type=""` means all types. Nulls in the sort key land last, deterministically.
    """
    rows = [
        c for c in cells
        if (not type or c.get("type") == type)
        and (c.get("cost_usd") is None or c["cost_usd"] <= maxcost)
        and (c.get("accuracy") is None or c["accuracy"] >= minacc)
    ]
    key_name, reverse = _SORT_KEYS.get(sort, _SORT_KEYS["worthiness"])

    def sort_key(c):
        v = c.get(key_name)
        missing = v is None
        # missing always sorts last regardless of direction; strings compare as-is.
        if isinstance(v, str):
            return (missing, v)
        return (missing, -(v or 0.0) if reverse else (v or 0.0))

    return sorted(rows, key=sort_key)
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `.venv/bin/python -m pytest tests/test_webui_transform.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add webui/__init__.py webui/transform.py tests/test_webui_transform.py
git commit -m "feat: webui.transform.filter_catalog — фильтр+сортировка каталога"
```

---

## Task 3: `webui/transform.py` — DataFrame-преобразования и границы слайдеров

**Files:**
- Modify: `webui/transform.py`
- Test: `tests/test_webui_transform.py`

- [ ] **Step 1: Дописать падающие тесты для to_*_df и slider_bounds**

Добавить в конец `tests/test_webui_transform.py`:

```python
def test_to_leaderboard_df_columns():
    lb = {"contributors": [
        {"user": "alice", "points": 20.0, "verified": 1, "cells": ["frames×fusion"]},
    ]}
    headers, rows = tr.to_leaderboard_df(lb)
    assert headers == ["#", "user", "points", "verified", "cells"]
    assert rows[0] == [1, "alice", 20.0, 1, "frames×fusion"]


def test_to_leaderboard_df_empty():
    headers, rows = tr.to_leaderboard_df({"contributors": []})
    assert headers == ["#", "user", "points", "verified", "cells"]
    assert rows == []


def test_to_catalog_df_columns_and_order():
    headers, rows = tr.to_catalog_df(_cells()[:1])
    assert headers == ["type", "recipe", "arm", "accuracy", "cost_usd",
                       "worthiness_vs_best", "complementarity", "n"]
    assert rows[0][0] == "code" and rows[0][1] == "best-single"


def test_slider_bounds_from_cells():
    b = tr.slider_bounds(_cells())
    assert b["maxcost"] == 0.010   # max cost across cells
    assert b["minacc"] == 0.0      # accuracy slider always starts at 0


def test_slider_bounds_empty_defaults():
    b = tr.slider_bounds([])
    assert b["maxcost"] == 1.0 and b["minacc"] == 0.0
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_webui_transform.py -q`
Expected: FAIL (AttributeError: module 'webui.transform' has no attribute 'to_leaderboard_df').

- [ ] **Step 3: Реализовать to_*_df и slider_bounds**

Добавить в `webui/transform.py`:

```python
_LEADERBOARD_HEADERS = ["#", "user", "points", "verified", "cells"]
_CATALOG_HEADERS = ["type", "recipe", "arm", "accuracy", "cost_usd",
                    "worthiness_vs_best", "complementarity", "n"]


def to_leaderboard_df(leaderboard):
    """(headers, rows) for the leaderboard Dataframe. Rank = 1-based row index."""
    rows = []
    for i, c in enumerate(leaderboard.get("contributors", []), start=1):
        rows.append([i, c.get("user", ""), c.get("points", 0.0),
                     c.get("verified", 0), ", ".join(c.get("cells", []))])
    return _LEADERBOARD_HEADERS, rows


def to_catalog_df(cells):
    """(headers, rows) for the catalog Dataframe, in fixed column order."""
    rows = [[c.get("type"), c.get("recipe"), c.get("arm"), c.get("accuracy"),
             c.get("cost_usd"), c.get("worthiness_vs_best"),
             c.get("complementarity"), c.get("n")] for c in cells]
    return _CATALOG_HEADERS, rows


def slider_bounds(cells):
    """Safe slider ranges from data: maxcost = max observed cost (or 1.0), minacc = 0.0."""
    costs = [c["cost_usd"] for c in cells if c.get("cost_usd") is not None]
    return {"maxcost": max(costs) if costs else 1.0, "minacc": 0.0}
```

Заметь: `test_to_leaderboard_df_columns` ожидает `cells` как одну строку `"frames×fusion"` — это результат `", ".join` одного элемента.

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `.venv/bin/python -m pytest tests/test_webui_transform.py -q`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add webui/transform.py tests/test_webui_transform.py
git commit -m "feat: webui.transform — to_leaderboard_df/to_catalog_df/slider_bounds"
```

---

## Task 4: `webui/export.py` — CSV/JSON экспорт среза

**Files:**
- Create: `webui/export.py`
- Test: `tests/test_webui_export.py`

- [ ] **Step 1: Написать падающий тест экспорта**

Создать `tests/test_webui_export.py`:

```python
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from webui import export as ex  # noqa: E402


def _rows():
    return [
        {"type": "code", "recipe": "best-single", "accuracy": 0.90, "cost_usd": 0.001},
        {"type": "math", "recipe": "fusion-strong", "accuracy": 0.70, "cost_usd": 0.004},
    ]


def test_csv_has_header_and_rows():
    data = ex.rows_to_csv_bytes(_rows())
    text = data.decode("utf-8")
    reader = list(csv.reader(io.StringIO(text)))
    assert reader[0] == ["type", "recipe", "accuracy", "cost_usd"]
    assert len(reader) == 3  # header + 2 rows


def test_csv_empty_rows_is_empty_string():
    assert ex.rows_to_csv_bytes([]) == b""


def test_json_round_trip():
    data = ex.rows_to_json_bytes(_rows())
    assert json.loads(data.decode("utf-8")) == _rows()
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_webui_export.py -q`
Expected: FAIL (ModuleNotFoundError: No module named 'webui.export').

- [ ] **Step 3: Реализовать export.py**

Создать `webui/export.py`:

```python
"""Serialize the currently-filtered catalog slice to CSV / JSON bytes."""
from __future__ import annotations

import csv
import io
import json


def rows_to_csv_bytes(rows):
    """CSV bytes with header from the first row's keys. Empty input -> b''."""
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def rows_to_json_bytes(rows):
    """Pretty JSON bytes of the row dicts."""
    return (json.dumps(rows, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
```

Заметь: `test_json_round_trip` сравнивает с `_rows()` — поэтому `json.loads` без trailing newline парсится корректно (newline игнорируется парсером).

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `.venv/bin/python -m pytest tests/test_webui_export.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add webui/export.py tests/test_webui_export.py
git commit -m "feat: webui.export — CSV/JSON экспорт отфильтрованного среза"
```

---

## Task 5: `webui/data_loader.py` — загрузка с retry и fallback

**Files:**
- Create: `webui/data_loader.py`
- Test: `tests/test_webui_data_loader.py`

ENV: `FUSIONBENCH_DATA_DIR` (локальная папка с json), `FUSIONBENCH_DATA_URL` (база Pages-URL).

- [ ] **Step 1: Написать падающие тесты загрузчика**

Создать `tests/test_webui_data_loader.py`:

```python
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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_webui_data_loader.py -q`
Expected: FAIL (ModuleNotFoundError: No module named 'webui.data_loader').

- [ ] **Step 3: Реализовать data_loader.py**

Создать `webui/data_loader.py`:

```python
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
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `.venv/bin/python -m pytest tests/test_webui_data_loader.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add webui/data_loader.py tests/test_webui_data_loader.py
git commit -m "feat: webui.data_loader — локальный файл + URL-fallback с retry"
```

---

## Task 6: Демо-фикстуры в `examples/`

**Files:**
- Create: `examples/leaderboard.json`
- Create: `examples/data.json`

- [ ] **Step 1: Создать examples/leaderboard.json**

```json
{
  "updated": "2026-06-16",
  "contributors": [
    {"user": "mira_k", "points": 40.0, "verified": 2, "cells": ["frames×fusion-strong", "ruler×best-single"]},
    {"user": "alex_p", "points": 20.0, "verified": 1, "cells": ["browsecomp×fusion-strong"]}
  ]
}
```

- [ ] **Step 2: Создать examples/data.json**

```json
{
  "generated": "2026-06-16",
  "suites": ["browsecomp", "frames"],
  "recipes": [
    {"name": "best-single", "arm": "best_single"},
    {"name": "fusion-strong", "arm": "fusion"}
  ],
  "cells": [
    {"type": "code", "recipe": "best-single", "arm": "best_single", "accuracy": 0.9167,
     "cost_usd": 0.001437, "latency_s": 0.0, "worthiness_vs_best": 0.0,
     "worthiness_vs_self_moa": 0.0, "complementarity": null, "recommended": true, "n": 12},
    {"type": "code", "recipe": "fusion-strong", "arm": "fusion", "accuracy": 0.9583,
     "cost_usd": 0.010220, "latency_s": 0.0, "worthiness_vs_best": 0.0417,
     "worthiness_vs_self_moa": 0.02, "complementarity": 0.917, "recommended": false, "n": 12},
    {"type": "math", "recipe": "best-single", "arm": "best_single", "accuracy": 0.70,
     "cost_usd": 0.002100, "latency_s": 0.0, "worthiness_vs_best": 0.0,
     "worthiness_vs_self_moa": 0.0, "complementarity": null, "recommended": true, "n": 8}
  ],
  "recipe_points": [
    {"recipe": "best-single", "arm": "best_single", "accuracy": 0.78, "cost_usd": 0.0017},
    {"recipe": "fusion-strong", "arm": "fusion", "accuracy": 0.86, "cost_usd": 0.0102}
  ],
  "pareto": [
    {"cost_usd": 0.0017, "accuracy": 0.78},
    {"cost_usd": 0.0102, "accuracy": 0.86}
  ],
  "complementarity": [
    {"type": "code", "recipe": "fusion-strong", "value": 0.917}
  ]
}
```

- [ ] **Step 3: Проверить, что чистые функции читают фикстуры**

Run: `.venv/bin/python -c "import sys; sys.path.insert(0,'.'); import os; os.environ['FUSIONBENCH_DATA_DIR']='examples'; from webui import data_loader as dl, transform as tr; lb=dl.load_leaderboard(); cat=dl.load_catalog(); print(tr.to_leaderboard_df(lb)[1]); print(len(tr.filter_catalog(cat['cells'],type='code',maxcost=1.0,minacc=0.0,sort='cost')))"`
Expected: печатает 2 строки доски и `2` (две code-ячейки).

- [ ] **Step 4: Commit**

```bash
git add examples/leaderboard.json examples/data.json
git commit -m "test: демо-фикстуры examples/ для Gradio-витрины (вне submissions/)"
```

---

## Task 7: `app.py` — Gradio Blocks UI

**Files:**
- Create: `app.py`

Нет автотеста на Gradio-сборку (UI-проводка) — верифицируем вручную через Playwright в Task 8. Чистая логика уже покрыта в Task 2-5.

- [ ] **Step 1: Создать app.py**

```python
"""FusionBench showcase — Gradio leaderboard + filterable catalog table.

Runs locally (`python app.py`) and on a Hugging Face Space unchanged: data is read
from FUSIONBENCH_DATA_DIR (local json) with a FUSIONBENCH_DATA_URL Pages fallback.
Set FUSIONBENCH_DATA_DIR=examples for the bundled demo fixtures.
"""
from __future__ import annotations

import gradio as gr

from webui import data_loader as dl
from webui import export as ex
from webui import transform as tr

TYPE_CHOICES = ["", "code", "deep_research", "multihop_qa", "math", "factual"]
SORT_CHOICES = ["worthiness", "accuracy", "cost", "recipe"]


def _catalog_view(cells, type, maxcost, minacc, sort):
    rows = tr.filter_catalog(cells, type=type, maxcost=maxcost, minacc=minacc, sort=sort)
    _, df_rows = tr.to_catalog_df(rows)
    return rows, df_rows


def build_demo():
    leaderboard = dl.load_leaderboard()
    catalog = dl.load_catalog()
    cells = catalog.get("cells", [])
    bounds = tr.slider_bounds(cells)
    lb_headers, lb_rows = tr.to_leaderboard_df(leaderboard)
    cat_headers, _ = tr.to_catalog_df(cells)
    init_rows, init_df = _catalog_view(cells, "", bounds["maxcost"], 0.0, "worthiness")

    with gr.Blocks(title="FusionBench — showcase") as demo:
        gr.Markdown("# FusionBench — when is multi-model fusion worth it?")
        with gr.Tabs():
            with gr.Tab("Leaderboard"):
                if lb_rows:
                    gr.Dataframe(value=lb_rows, headers=lb_headers,
                                 interactive=False, label="Contributors")
                else:
                    gr.Markdown("_Пока нет верифицированных вкладов._")
            with gr.Tab("Catalog"):
                if not cells:
                    gr.Markdown("_Каталог пуст — сгенерируйте data.json (scripts/build_catalog.py)._")
                else:
                    state = gr.State(cells)
                    filtered = gr.State(init_rows)
                    with gr.Row():
                        f_type = gr.Dropdown(TYPE_CHOICES, value="", label="task type")
                        f_sort = gr.Dropdown(SORT_CHOICES, value="worthiness", label="sort")
                    with gr.Row():
                        f_maxcost = gr.Slider(0.0, bounds["maxcost"], value=bounds["maxcost"],
                                              label="max cost $")
                        f_minacc = gr.Slider(0.0, 1.0, value=0.0, label="min accuracy")
                    table = gr.Dataframe(value=init_df, headers=cat_headers,
                                         interactive=False, label="Recipes")
                    with gr.Row():
                        dl_csv = gr.DownloadButton("Download CSV")
                        dl_json = gr.DownloadButton("Download JSON")

                    def on_filter(cells_, type_, maxcost_, minacc_, sort_):
                        rows_, df_ = _catalog_view(cells_, type_, maxcost_, minacc_, sort_)
                        return rows_, df_

                    inputs = [state, f_type, f_maxcost, f_minacc, f_sort]
                    for ctrl in (f_type, f_sort, f_maxcost, f_minacc):
                        ctrl.change(on_filter, inputs=inputs, outputs=[filtered, table])

                    def make_csv(rows_):
                        path = "fusionbench_catalog.csv"
                        with open(path, "wb") as fh:
                            fh.write(ex.rows_to_csv_bytes(rows_))
                        return path

                    def make_json(rows_):
                        path = "fusionbench_catalog.json"
                        with open(path, "wb") as fh:
                            fh.write(ex.rows_to_json_bytes(rows_))
                        return path

                    dl_csv.click(make_csv, inputs=[filtered], outputs=[dl_csv])
                    dl_json.click(make_json, inputs=[filtered], outputs=[dl_json])
    return demo


if __name__ == "__main__":
    build_demo().launch()
```

- [ ] **Step 2: Проверить, что модуль импортируется и Blocks собирается без запуска сервера**

Run: `FUSIONBENCH_DATA_DIR=examples .venv/bin/python -c "import sys; sys.path.insert(0,'.'); import app; d=app.build_demo(); print(type(d).__name__)"`
Expected: печатает `Blocks` без исключений.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: app.py — Gradio-витрина (доска лидеров + каталог с фильтрами + экспорт)"
```

---

## Task 8: Ручная верификация витрины через Playwright

**Files:** нет (верификация).

- [ ] **Step 1: Поднять app.py локально в фоне на демо-фикстурах**

Run (background): `FUSIONBENCH_DATA_DIR=examples .venv/bin/python app.py`
Дождаться строки `Running on local URL: http://127.0.0.1:7860`.

- [ ] **Step 2: Открыть в Playwright MCP и снять снапшот**

Через Playwright MCP: navigate `http://127.0.0.1:7860`, снять `browser_snapshot`.
Expected: видна вкладка Leaderboard с таблицей (mira_k, alex_p) и вкладка Catalog.

- [ ] **Step 3: Проверить фильтр каталога**

Через Playwright MCP: переключить на Catolog, выбрать type=code, проверить снапшот таблицы.
Expected: в таблице остаются только code-строки (2 шт).

- [ ] **Step 4: Остановить сервер**

Остановить фоновый процесс app.py.

- [ ] **Step 5: Прогнать весь pytest — Этап 1 зелёный целиком**

Run: `.venv/bin/python -m pytest -q`
Expected: baseline (91) + новые тесты transform/export/data_loader, всё passed, 1 skipped, 1 xfailed.

---

# ЭТАП 2 — Выгрузка results-dataset на HF

## Task 9: `scripts/publish_datasets.py` — сбор файлов (чистое ядро)

**Files:**
- Create: `scripts/publish_datasets.py`
- Test: `tests/test_publish_datasets.py`

results dataset = `leaderboard.json` + `data.json`. Манифесты `submissions/` — заложить layout, публиковать позже.

- [ ] **Step 1: Написать падающий тест collect_dataset_files**

Создать `tests/test_publish_datasets.py`:

```python
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import publish_datasets as pd  # noqa: E402


def test_collect_picks_existing_json(tmp_path):
    src = tmp_path / "site"
    src.mkdir()
    (src / "leaderboard.json").write_text("{}")
    (src / "data.json").write_text("{}")
    files = pd.collect_dataset_files(str(src))
    paths_in_repo = {repo for _, repo in files}
    assert paths_in_repo == {"leaderboard.json", "data.json"}
    for local, _ in files:
        assert Path(local).exists()


def test_collect_missing_source_raises(tmp_path):
    src = tmp_path / "site"
    src.mkdir()
    (src / "leaderboard.json").write_text("{}")
    # data.json missing -> incomplete results dataset, must raise
    with pytest.raises(FileNotFoundError):
        pd.collect_dataset_files(str(src))
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_publish_datasets.py -q`
Expected: FAIL (ModuleNotFoundError: No module named 'publish_datasets').

- [ ] **Step 3: Реализовать collect_dataset_files**

Создать `scripts/publish_datasets.py`:

```python
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
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `.venv/bin/python -m pytest tests/test_publish_datasets.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/publish_datasets.py tests/test_publish_datasets.py
git commit -m "feat: publish_datasets.collect_dataset_files — сбор results-файлов"
```

---

## Task 10: `scripts/publish_datasets.py` — publish() с dry-run и retry

**Files:**
- Modify: `scripts/publish_datasets.py`
- Test: `tests/test_publish_datasets.py`

- [ ] **Step 1: Дописать падающие тесты publish()**

Добавить в конец `tests/test_publish_datasets.py`:

```python
def test_dry_run_does_not_touch_api(capsys):
    uploaded = []

    class FakeApi:
        def create_repo(self, *a, **k):
            uploaded.append("create")

        def upload_file(self, *a, **k):
            uploaded.append("upload")

    pd.publish(FakeApi(), "user/fb-results",
               [("/tmp/leaderboard.json", "leaderboard.json")], dry_run=True)
    assert uploaded == []  # network untouched
    assert "leaderboard.json" in capsys.readouterr().out  # plan printed


def test_real_publish_calls_create_and_upload():
    calls = []

    class FakeApi:
        def create_repo(self, repo_id, repo_type, exist_ok):
            calls.append(("create", repo_id, repo_type, exist_ok))

        def upload_file(self, path_or_fileobj, path_in_repo, repo_id, repo_type):
            calls.append(("upload", path_in_repo))

    pd.publish(FakeApi(), "user/fb-results",
               [("/tmp/data.json", "data.json")], dry_run=False)
    assert ("create", "user/fb-results", "dataset", True) in calls
    assert ("upload", "data.json") in calls
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_publish_datasets.py -q`
Expected: FAIL (AttributeError: module 'publish_datasets' has no attribute 'publish').

- [ ] **Step 3: Реализовать publish()**

Добавить в `scripts/publish_datasets.py`:

```python
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
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `.venv/bin/python -m pytest tests/test_publish_datasets.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/publish_datasets.py tests/test_publish_datasets.py
git commit -m "feat: publish_datasets.publish — dry-run + create_repo + upload с retry"
```

---

## Task 11: `scripts/publish_datasets.py` — main() и токен-гейт

**Files:**
- Modify: `scripts/publish_datasets.py`
- Test: `tests/test_publish_datasets.py`

- [ ] **Step 1: Дописать падающие E2E-тесты main()**

Добавить в конец `tests/test_publish_datasets.py`:

```python
def test_main_no_token_not_dryrun_exits(tmp_path, monkeypatch):
    src = tmp_path / "site"
    src.mkdir()
    (src / "leaderboard.json").write_text("{}")
    (src / "data.json").write_text("{}")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", [
        "publish_datasets.py", "--repo", "user/fb", "--source", str(src)])
    with pytest.raises(SystemExit) as e:
        pd.main()
    assert e.value.code != 0


def test_main_dry_run_succeeds_without_token(tmp_path, monkeypatch, capsys):
    src = tmp_path / "site"
    src.mkdir()
    (src / "leaderboard.json").write_text("{}")
    (src / "data.json").write_text("{}")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", [
        "publish_datasets.py", "--repo", "user/fb", "--source", str(src), "--dry-run"])
    pd.main()  # no SystemExit, no token needed
    assert "[dry-run]" in capsys.readouterr().out


def test_main_missing_source_exits(tmp_path, monkeypatch):
    src = tmp_path / "site"
    src.mkdir()
    (src / "leaderboard.json").write_text("{}")  # data.json missing
    monkeypatch.setattr(sys, "argv", [
        "publish_datasets.py", "--repo", "user/fb", "--source", str(src), "--dry-run"])
    with pytest.raises(SystemExit) as e:
        pd.main()
    assert e.value.code != 0
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_publish_datasets.py -q`
Expected: FAIL (AttributeError: module 'publish_datasets' has no attribute 'main').

- [ ] **Step 3: Реализовать main()**

Добавить в `scripts/publish_datasets.py`:

```python
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
```

Заметь: `publish(None, ...)` в dry-run безопасен — функция не трогает `api` до `create_repo`, а в dry-run выходит раньше.

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `.venv/bin/python -m pytest tests/test_publish_datasets.py -q`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/publish_datasets.py tests/test_publish_datasets.py
git commit -m "feat: publish_datasets.main — CLI + токен-гейт через HF_TOKEN ENV (exit не assert)"
```

---

## Task 12: Артефакты HF Space (requirements.txt + README Space)

**Files:**
- Create: `requirements.txt`
- Create: `README_HF_SPACE.md`

HF Space не читает опц-группы pyproject — нужен явный requirements.txt. Деплой/реальный push — НЕ в этой задаче (по запросу с токеном).

- [ ] **Step 1: Создать requirements.txt с теми же пинами, что в группе space**

```
gradio>=4.44
huggingface_hub>=0.25
httpx>=0.27
```

- [ ] **Step 2: Создать README_HF_SPACE.md с YAML-хедером Space**

```markdown
---
title: FusionBench
emoji: 🔭
colorFrom: indigo
colorTo: blue
sdk: gradio
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
```

- [ ] **Step 3: Проверить, что requirements.txt парсится pip-ом (dry, без установки)**

Run: `.venv/bin/python -m pip install --dry-run -r requirements.txt 2>&1 | head -5`
Expected: pip разбирает файл без синтаксических ошибок (already satisfied — ок).

- [ ] **Step 4: Commit**

```bash
git add requirements.txt README_HF_SPACE.md
git commit -m "chore: артефакты HF Space — requirements.txt + README с YAML-хедером (без деплоя)"
```

---

## Task 13: Финальная верификация всей фазы

**Files:** нет (верификация).

- [ ] **Step 1: Полный прогон тестов**

Run: `.venv/bin/python -m pytest -q`
Expected: всё passed (baseline 91 + новые webui/publish), 1 skipped, 1 xfailed. Записать точное число.

- [ ] **Step 2: Dry-run выгрузки на демо-фикстурах (без токена)**

Run: `.venv/bin/python scripts/publish_datasets.py --repo demo/fb-results --source examples --dry-run`
Expected: `[dry-run] would publish dataset demo/fb-results:` + 2 строки (leaderboard.json, data.json). Ненулевого exit нет.

- [ ] **Step 3: Перечитать спек построчно — отметить покрытие**

Открыть `docs/superpowers/specs/2026-06-16-phase5-hf-space-design.md`, пройти по разделам, убедиться, что каждое требование реализовано (витрина, фильтры, экспорт, empty-state, retry, токен-гейт, examples/, requirements.txt). Отметить в ответе выполнено/нет.

- [ ] **Step 4: Обновить handoff и память**

Обновить `.claude/handoffs/phase5-hf-space.md` (статус → реализовано) и записать в `MEMORY.md` факт о Фазе 5, если есть неочевидное (напр. webui/ в корне, app.py для HF Space). Это делает главная сессия, не субагент.

- [ ] **Step 5: Решить финиш ветки**

Через `superpowers:finishing-a-development-branch`: предложить пользователю merge/PR/cleanup. Push/PR — только по явному запросу (outward-facing).

---

## Self-Review плана (заполняется автором перед хендоффом)

**Spec coverage:** объём (read-only + datasets) → Task 1-13; источник JSON + fallback → Task 5; UX доска+каталог+фильтры+экспорт → Task 2-4,7; empty-state → Task 5,7; демо вне submissions/ → Task 6; structure A (app.py+webui/+publish_datasets) → все; токен через ENV + exit не assert → Task 11; requirements.txt + README Space → Task 12; границы (не деплоить) → Task 12,13.

**Placeholder scan:** все шаги с кодом содержат полный код; команды с ожидаемым выводом; нет TBD/«handle errors».

**Type consistency:** `filter_catalog(cells, type, maxcost, minacc, sort)` единообразно в Task 2/3/7; `to_leaderboard_df`/`to_catalog_df` возвращают `(headers, rows)` везде; `collect_dataset_files(source_dir)→[(local, repo_path)]` и `publish(api, repo_id, files, dry_run)` согласованы Task 9/10/11; `_fetch_json_with_retry(url, attempts)` совпадает в реализации и моках Task 5.
