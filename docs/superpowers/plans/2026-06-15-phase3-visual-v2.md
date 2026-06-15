# Фаза 3 — Визуал v2 (ядро): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переписать `scripts/build_catalog.py` так, чтобы он эмитил `site/data.json` и рисовал hero-Pareto + heatmap на ECharts из него, сохранив текущий SVG-рендер как `<noscript>`-фолбэк.

**Architecture:** Вариант A — данные (`site/data.json`, генерится `build_data(rows)`) ⊥ логика рендера (`site/app.js`, статичный, ECharts) ⊥ каркас+фолбэк (`site/index.html`, генерится `render_fallback`). Чистые расчёты (`pareto_frontier`, `recommended`-флаги) в Python; JS только рисует готовое.

**Tech Stack:** Python 3.10+ (stdlib: argparse/json/glob), ECharts 5 (CDN), статичный HTML/JS. Тесты — pytest (юнит на `build_data`/`pareto_frontier` + smoke через subprocess). Интерпретатор — `.venv/bin/python`.

**Источники:** спека `docs/superpowers/specs/2026-06-15-phase3-visual-v2-design.md`; требования `docs/PROPOSAL-community-v2.md` §2.

**Важные факты о данных (dict-ключи каталога `runs/*.jsonl`):** строки — это сериализованный `CatalogRow`. Ключи: `suite, task_type, recipe, arm, n_tasks, accuracy, mean_tokens, mean_cost_usd, mean_latency_s, worthiness_vs_best, worthiness_vs_self_moa, panel, judge, synth, complementarity, oracle_coverage, notes, ts`. `complementarity`/`oracle_coverage` могут быть `null`. Рецепты: best-single→best_single, self-moa→self_moa, fusion-cheap→fusion, fusion-strong→fusion, source-pool→source_pool. Task types: code, deep_research, multihop_qa, math, factual.

**Контракт `site/data.json`** (что эмитит `build_data`): ключи `generated, suites, recipes[], cells[], recipe_points[], pareto[], complementarity[]`. Маппинг полей ячейки: `task_type→type`, `mean_cost_usd→cost_usd`, `mean_latency_s→latency_s`, `n_tasks→n`; `worthiness_vs_best`, `worthiness_vs_self_moa`, `complementarity`, `recommended` (флаг).

---

## File Structure

- **Modify** `scripts/build_catalog.py`:
  - вынести `pareto_frontier(points)` из тела `svg_scatter` (чистая функция);
  - добавить `build_data(rows) -> dict` (эмит контракта);
  - переименовать `render` → `render_fallback` (каркас + `<noscript>` SVG+таблицы);
  - расширить `main`: писать `site/data.json` + `site/index.html`.
- **Create** `site/app.js` — статичный: `fetch('data.json')` → `renderPareto` + `renderHeatmap` на ECharts; проверка `typeof echarts === 'undefined'`.
- **Create** `tests/test_build_data.py` — юнит на `build_data`/`pareto_frontier` + smoke на сборку.
- `site/index.html` — генерится (не правится руками).
- `Makefile` / `.github/workflows/pages.yml` — не меняем (зовут `build_catalog`, тот пишет оба файла).

---

## Task 1: `pareto_frontier` — выделить чистую функцию

**Files:**
- Modify: `scripts/build_catalog.py` (блок frontier в `svg_scatter`, строки ~88-96)
- Test: `tests/test_build_data.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_build_data.py`:

```python
# tests/test_build_data.py
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "build_catalog.py"
sys.path.insert(0, str(ROOT / "scripts"))

import build_catalog as bc


def test_pareto_frontier_keeps_nondominated():
    # points: name -> {acc, cost, arm}. Frontier = sort by cost asc, keep rising accuracy.
    pts = {
        "cheap-weak":   {"acc": 0.50, "cost": 0.001, "arm": "best_single"},
        "mid":          {"acc": 0.70, "cost": 0.004, "arm": "fusion"},
        "dominated":    {"acc": 0.60, "cost": 0.005, "arm": "fusion"},  # costlier, less accurate than mid
        "top":          {"acc": 0.80, "cost": 0.009, "arm": "source_pool"},
    }
    front = bc.pareto_frontier(pts)
    # returns list of {"cost_usd", "accuracy"} sorted by cost asc, only non-dominated
    accs = [round(p["accuracy"], 2) for p in front]
    assert accs == [0.50, 0.70, 0.80]   # "dominated" dropped
    costs = [p["cost_usd"] for p in front]
    assert costs == sorted(costs)        # cost ascending
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_build_data.py::test_pareto_frontier_keeps_nondominated -v`
Expected: FAIL — `AttributeError: module 'build_catalog' has no attribute 'pareto_frontier'`.

- [ ] **Step 3: Add `pareto_frontier` and call it from `svg_scatter`**

В `scripts/build_catalog.py` добавить функцию (над `svg_scatter`):

```python
def pareto_frontier(by_recipe: dict[str, dict]) -> list[dict]:
    """Non-dominated cost-quality points: sort by cost asc, keep strictly rising accuracy.
    Input: name -> {acc, cost, ...}. Output: [{"cost_usd", "accuracy"}] sorted by cost asc."""
    pts = sorted(by_recipe.values(), key=lambda v: v["cost"])
    front: list[dict] = []
    best_a = -1.0
    for v in pts:
        if v["acc"] > best_a + 1e-9:
            front.append({"cost_usd": v["cost"], "accuracy": v["acc"]})
            best_a = v["acc"]
    return front
```

Затем заменить инлайн-блок frontier в `svg_scatter` (строки ~88-96) на использование общей функции:

```python
    # frontier (upper-left envelope) via shared pareto_frontier
    front = [(p["cost_usd"], p["accuracy"]) for p in pareto_frontier(by_recipe)]
    if len(front) >= 2:
        poly = " ".join(f"{X(c):.1f},{Y(a):.1f}" for c, a in front)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="#9ca3af" '
                     f'stroke-dasharray="5 5" stroke-width="1.5"/>')
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_build_data.py -v`
Expected: PASS. Также прогнать smoke руками: `.venv/bin/python scripts/build_catalog.py --runs runs/catalog.jsonl --out /tmp/site_check.html` — должно по-прежнему писать HTML без ошибок (SVG-фронтир не сломан).

- [ ] **Step 5: Commit**

```bash
git add scripts/build_catalog.py tests/test_build_data.py
git commit -m "refactor: вынести pareto_frontier из svg_scatter (чистая функция)"
```

---

## Task 2: `build_data` — эмит контракта `data.json`

**Files:**
- Modify: `scripts/build_catalog.py` (добавить `build_data`)
- Test: `tests/test_build_data.py`

- [ ] **Step 1: Write the failing tests**

Добавить в `tests/test_build_data.py`:

```python
def _sample_rows():
    # two task types, a few recipes each; dict form as in runs/catalog.jsonl
    return [
        {"suite": "frames", "task_type": "multihop_qa", "recipe": "best-single", "arm": "best_single",
         "n_tasks": 10, "accuracy": 0.60, "mean_tokens": 100, "mean_cost_usd": 0.001,
         "mean_latency_s": 0.5, "worthiness_vs_best": 0.0, "worthiness_vs_self_moa": 0.0,
         "panel": [], "judge": None, "synth": None, "complementarity": None,
         "oracle_coverage": None, "notes": "mock", "ts": 1},
        {"suite": "frames", "task_type": "multihop_qa", "recipe": "fusion-strong", "arm": "fusion",
         "n_tasks": 10, "accuracy": 0.71, "mean_tokens": 400, "mean_cost_usd": 0.0044,
         "mean_latency_s": 1.6, "worthiness_vs_best": 0.11, "worthiness_vs_self_moa": 0.10,
         "panel": ["a", "b"], "judge": "j", "synth": "s", "complementarity": 0.79,
         "oracle_coverage": 0.9, "notes": "mock", "ts": 1},
        {"suite": "ruler", "task_type": "long_context", "recipe": "best-single", "arm": "best_single",
         "n_tasks": 12, "accuracy": 0.33, "mean_tokens": 90, "mean_cost_usd": 0.0009,
         "mean_latency_s": 0.4, "worthiness_vs_best": 0.0, "worthiness_vs_self_moa": 0.0,
         "panel": [], "judge": None, "synth": None, "complementarity": None,
         "oracle_coverage": None, "notes": "mock", "ts": 1},
    ]


def test_build_data_schema_keys():
    d = bc.build_data(_sample_rows())
    assert set(d) >= {"generated", "suites", "recipes", "cells", "recipe_points", "pareto", "complementarity"}
    assert d["suites"] == ["frames", "ruler"]               # sorted unique suites
    assert {r["name"] for r in d["recipes"]} == {"best-single", "fusion-strong"}


def test_build_data_cell_field_mapping():
    d = bc.build_data(_sample_rows())
    cell = next(c for c in d["cells"] if c["recipe"] == "fusion-strong")
    assert cell["type"] == "multihop_qa"          # task_type -> type
    assert cell["cost_usd"] == 0.0044             # mean_cost_usd -> cost_usd
    assert cell["latency_s"] == 1.6               # mean_latency_s -> latency_s
    assert cell["n"] == 10                        # n_tasks -> n
    assert cell["worthiness_vs_best"] == 0.11
    assert cell["complementarity"] == 0.79


def test_build_data_recommended_flag_one_per_type():
    d = bc.build_data(_sample_rows())
    by_type = {}
    for c in d["cells"]:
        by_type.setdefault(c["type"], []).append(c)
    for ttype, cells in by_type.items():
        recs = [c for c in cells if c["recommended"]]
        assert len(recs) == 1, ttype                     # exactly one recommended per type
    # in multihop_qa, fusion-strong (0.71) beats best-single (0.60)
    rec = next(c for c in d["cells"] if c["type"] == "multihop_qa" and c["recommended"])
    assert rec["recipe"] == "fusion-strong"


def test_build_data_recipe_points_and_pareto():
    d = bc.build_data(_sample_rows())
    # recipe_points: mean cost/accuracy per recipe across types
    bs = next(p for p in d["recipe_points"] if p["recipe"] == "best-single")
    assert bs["arm"] == "best_single"
    assert round(bs["accuracy"], 4) == round((0.60 + 0.33) / 2, 4)   # averaged across both types
    # pareto is a non-empty list of {cost_usd, accuracy}, cost ascending
    assert d["pareto"] and all({"cost_usd", "accuracy"} <= set(p) for p in d["pareto"])
    costs = [p["cost_usd"] for p in d["pareto"]]
    assert costs == sorted(costs)


def test_build_data_json_serializable_and_null_complementarity():
    d = bc.build_data(_sample_rows())
    s = json.dumps(d)                                       # must not raise
    cell = next(c for c in d["cells"] if c["recipe"] == "best-single" and c["type"] == "multihop_qa")
    assert cell["complementarity"] is None                 # null passthrough
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest tests/test_build_data.py -k build_data -v`
Expected: FAIL — `AttributeError: ... has no attribute 'build_data'`.

- [ ] **Step 3: Implement `build_data`**

Добавить в `scripts/build_catalog.py` (используя существующие `recommended`, `pareto_frontier`):

```python
def build_data(rows: list[dict]) -> dict:
    """Emit the site/data.json contract from catalog rows. Pure: no I/O."""
    from collections import defaultdict

    suites = sorted({r["suite"] for r in rows if r.get("suite")})

    # recipes: name -> arm (first seen), stable by name
    recipe_arm: dict[str, str] = {}
    for r in rows:
        recipe_arm.setdefault(r["recipe"], r["arm"])
    recipes = [{"name": n, "arm": a} for n, a in sorted(recipe_arm.items())]

    # recommended flag: best (-accuracy, mean_cost_usd) per task_type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_type[r["task_type"]].append(r)
    rec_keys: set[tuple] = set()
    for ttype, rs in by_type.items():
        rec = recommended(rs)
        rec_keys.add((ttype, rec["recipe"]))

    cells = []
    for r in rows:
        cells.append({
            "type": r["task_type"],
            "recipe": r["recipe"],
            "arm": r["arm"],
            "accuracy": r["accuracy"],
            "cost_usd": r["mean_cost_usd"],
            "latency_s": r["mean_latency_s"],
            "worthiness_vs_best": r["worthiness_vs_best"],
            "worthiness_vs_self_moa": r["worthiness_vs_self_moa"],
            "complementarity": r.get("complementarity"),
            "recommended": (r["task_type"], r["recipe"]) in rec_keys,
            "n": r["n_tasks"],
        })

    # recipe_points: mean cost/accuracy per recipe across task types (hero scatter)
    agg: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        agg[r["recipe"]].append(r)
    recipe_points = []
    by_recipe_for_front: dict[str, dict] = {}
    for nm, rs in sorted(agg.items()):
        acc = sum(x["accuracy"] for x in rs) / len(rs)
        cost = sum(x["mean_cost_usd"] for x in rs) / len(rs)
        arm = rs[0]["arm"]
        recipe_points.append({"recipe": nm, "arm": arm, "accuracy": acc, "cost_usd": cost})
        by_recipe_for_front[nm] = {"acc": acc, "cost": cost, "arm": arm}

    pareto = pareto_frontier(by_recipe_for_front)

    # complementarity passthrough (emitted for the next stage; not drawn in core)
    complementarity = []
    for r in rows:
        if r.get("complementarity") is not None:
            complementarity.append({"type": r["task_type"], "recipe": r["recipe"],
                                    "value": r["complementarity"]})

    return {
        "generated": time.strftime("%Y-%m-%d"),
        "suites": suites,
        "recipes": recipes,
        "cells": cells,
        "recipe_points": recipe_points,
        "pareto": pareto,
        "complementarity": complementarity,
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_build_data.py -v`
Expected: PASS (all build_data + pareto tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/build_catalog.py tests/test_build_data.py
git commit -m "feat: build_data — эмит контракта site/data.json из каталога"
```

---

## Task 3: `main` пишет `data.json`, `render` → `render_fallback`

**Files:**
- Modify: `scripts/build_catalog.py` (`render`→`render_fallback`, `main`)
- Test: `tests/test_build_data.py`

- [ ] **Step 1: Write the failing smoke test**

Добавить в `tests/test_build_data.py`:

```python
def test_main_writes_data_json_and_index(tmp_path):
    out_html = tmp_path / "index.html"
    out_json = tmp_path / "data.json"
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--runs", str(ROOT / "runs" / "catalog.jsonl"),
         "--out", str(out_html)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert out_html.exists() and out_json.exists()          # data.json sits next to index.html
    data = json.loads(out_json.read_text())                 # valid JSON
    assert data["cells"] and data["recipe_points"]
    html = out_html.read_text()
    assert "<noscript>" in html                             # SVG fallback present
    assert "echarts" in html.lower()                        # ECharts wired
    assert "app.js" in html                                 # app.js referenced
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest tests/test_build_data.py::test_main_writes_data_json_and_index -v`
Expected: FAIL — `data.json` не пишется и/или нет `<noscript>`/`echarts`/`app.js` в HTML.

- [ ] **Step 3: Rename `render`→`render_fallback`, wrap SVG in `<noscript>`, extend `main`**

В `scripts/build_catalog.py`:

(a) переименовать `def render(` → `def render_fallback(` и обновить единственный вызов в `main`.

(b) В шаблоне `PAGE` заменить хвост (от `<h2>Cost vs quality</h2>` до закрывающих `</div></body></html>`) так, чтобы ECharts-контейнеры стали основными, а таблицы (`{sections}`), SVG-scatter (`{scatter}`+`{legend}`) и complementarity-бары (`{bars}`) ушли в `<noscript>`:

```python
<h2>Cost vs quality</h2>
<div id="hero" class="card" style="height:420px"></div>
<h2>Worthiness — recipe × task type</h2>
<div id="heatmap" class="card" style="height:420px"></div>
<noscript>
{sections}
<h2>Cost vs quality (static)</h2>
<div class="card">{scatter}<div class="legend">{legend}</div></div>
<h2>Panel complementarity by task type</h2>
<div class="card">{bars}</div>
</noscript>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<script src="app.js"></script>
<p class="foot">{foot}</p>
</div></body></html>
```

Примечание: `{sections}` (таблицы) переносится из позиции до графиков внутрь `<noscript>` — убрать прежнее вхождение `{sections}` выше. Все именованные поля `.format(...)` в `render_fallback` остаются те же (title, meta, verdict, sections, scatter, legend, bars, foot) — сигнатуру `.format` не менять.

(c) Расширить `main` — писать `data.json` рядом с `--out`:

```python
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*", default=["runs/*.jsonl"])
    ap.add_argument("--out", default="site/index.html")
    ap.add_argument("--title", default="FusionBench — fusion recipe catalog")
    args = ap.parse_args()

    rows = dedupe(load_rows(args.runs))
    if not rows:
        raise SystemExit("no catalog rows found; run scripts/run_v0.py first")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_fallback(rows, args.title), encoding="utf-8")
    data_path = out.parent / "data.json"
    data_path.write_text(json.dumps(build_data(rows), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} and {data_path} from {len(rows)} deduped rows across "
          f"{len(set(r['task_type'] for r in rows))} task types")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_build_data.py -v`
Expected: PASS (включая smoke).

- [ ] **Step 5: Commit**

```bash
git add scripts/build_catalog.py tests/test_build_data.py
git commit -m "feat: build_catalog пишет data.json + index.html; SVG в noscript-фолбэк"
```

---

## Task 4: `site/app.js` — ECharts hero-Pareto + heatmap

**Files:**
- Create: `site/app.js`

(JS не покрывается автотестами — проверяется smoke-наличием ссылки в HTML (Task 3) и ручным Playwright-прогоном в Task 5. Сообщения об ошибке выставляются через `textContent` — никакого `innerHTML`, чтобы не триггерить XSS-предупреждение и быть безопасным по умолчанию.)

- [ ] **Step 1: Создать `site/app.js`**

```javascript
// site/app.js — renders hero-Pareto and heatmap from data.json via ECharts.
// Pure view layer: all numbers are precomputed in data.json by build_catalog.py.
(function () {
  var ARM_COLOR = {
    best_single: "#6b7280", self_moa: "#2563eb",
    fusion: "#0d9488", source_pool: "#7c3aed"
  };

  function fail(msg) {
    var h = document.getElementById("hero");
    if (h) { h.textContent = msg; h.style.color = "#6b7280"; h.style.padding = "16px"; }
  }

  if (typeof echarts === "undefined") {
    // CDN unavailable while JS is on: <noscript> won't fire, so just message the container.
    fail("Charts unavailable (ECharts failed to load).");
    return;
  }

  fetch("data.json")
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(render)
    .catch(function (e) { fail("Could not load data.json: " + e.message); });

  function render(data) {
    renderHero(data);
    renderHeatmap(data);
  }

  function renderHero(data) {
    var pts = data.recipe_points || [];
    var hero = echarts.init(document.getElementById("hero"));
    hero.setOption({
      grid: { left: 56, right: 24, top: 24, bottom: 48 },
      xAxis: { type: "log", name: "cost per task ($)", nameLocation: "middle", nameGap: 30 },
      yAxis: {
        type: "value", name: "accuracy", min: 0, max: 1,
        axisLabel: { formatter: function (v) { return Math.round(v * 100) + "%"; } }
      },
      tooltip: {
        formatter: function (p) {
          if (p.seriesType !== "scatter") return "";
          return p.data.name + ": $" + p.data.value[0].toFixed(4) +
                 " · " + Math.round(p.data.value[1] * 100) + "%";
        }
      },
      series: [
        {
          type: "scatter", symbolSize: 16,
          data: pts.map(function (c) {
            return { name: c.recipe, value: [c.cost_usd, c.accuracy],
                     itemStyle: { color: ARM_COLOR[c.arm] || "#6b7280" } };
          }),
          label: { show: true, position: "top",
                   formatter: function (p) { return p.data.name; }, fontSize: 11 }
        },
        {
          type: "line", symbol: "none", silent: true,
          lineStyle: { type: "dashed", color: "#9ca3af" },
          data: (data.pareto || []).map(function (p) { return [p.cost_usd, p.accuracy]; })
        }
      ]
    });
  }

  function renderHeatmap(data) {
    var cells = data.cells || [];
    var types = [];
    var recipes = [];
    cells.forEach(function (c) {
      if (types.indexOf(c.type) < 0) types.push(c.type);
      if (recipes.indexOf(c.recipe) < 0) recipes.push(c.recipe);
    });
    var matrix = cells.map(function (c) {
      return [recipes.indexOf(c.recipe), types.indexOf(c.type), c.worthiness_vs_best];
    });
    var hm = echarts.init(document.getElementById("heatmap"));
    hm.setOption({
      grid: { left: 120, right: 24, top: 24, bottom: 60 },
      tooltip: { position: "top" },
      xAxis: { type: "category", data: recipes, axisLabel: { rotate: 30 } },
      yAxis: { type: "category", data: types },
      visualMap: {
        min: -0.1, max: 0.1, calculable: true, orient: "horizontal",
        left: "center", bottom: 0,
        inRange: { color: ["#b91c1c", "#f1f5f9", "#15803d"] }
      },
      series: [{
        type: "heatmap", data: matrix,
        label: {
          show: true,
          formatter: function (p) {
            var v = p.value[2];
            return (v > 0 ? "+" : "") + Math.round(v * 100);
          }
        }
      }]
    });
  }
})();
```

- [ ] **Step 2: Commit**

```bash
git add site/app.js
git commit -m "feat: site/app.js — hero-Pareto + heatmap на ECharts из data.json"
```

---

## Task 5: Регенерация сайта + ручная проверка рендера

**Files:**
- Modify (generated): `site/index.html`, `site/data.json`

- [ ] **Step 1: Сгенерировать сайт из mock-каталога**

Run: `.venv/bin/python scripts/build_catalog.py --runs "runs/*.jsonl" --out site/index.html`
Expected: `wrote site/index.html and site/data.json from N deduped rows ...`. Проверить валидность: `.venv/bin/python -c "import json; json.load(open('site/data.json'))"`.

- [ ] **Step 2: Поднять локальный сервер и проверить рендер (Playwright / webapp-testing)**

Run (фон): `.venv/bin/python -m http.server 8765 --directory site`.
Через webapp-testing/Playwright открыть `http://localhost:8765/`, убедиться:
- два `<canvas>` (hero + heatmap) отрисованы (ECharts создаёт canvas);
- нет console-ошибок (network к jsdelivr ECharts успешен; `data.json` загружен 200);
- точки hero подписаны рецептами, heatmap показывает сетку recipe×type.
Остановить сервер после проверки.

- [ ] **Step 3: Прогнать весь тест-набор + проверить отсутствие регрессий**

Run: `.venv/bin/python -m pytest -q`
Expected: все тесты зелёные (прежние и новые из `test_build_data.py`).

- [ ] **Step 4: Commit регенерированного сайта**

```bash
git add site/index.html site/data.json
git commit -m "chore: регенерировать site/ из mock-каталога (data.json + ECharts)"
```

---

## Verification (перед «готово»)

- [ ] `.venv/bin/python -m pytest -q` — всё зелёное.
- [ ] `site/data.json` валиден, содержит `cells/recipe_points/pareto`.
- [ ] `site/index.html` содержит ECharts-CDN, `app.js`, `<noscript>`-SVG-фолбэк.
- [ ] Ручной Playwright-прогон: оба графика рисуются, нет console-ошибок.
- [ ] `Makefile`/`pages.yml` не тронуты и по-прежнему зовут `build_catalog`.
- [ ] Перечитать спеку построчно — каждый пункт ядра реализован; explorer/deep-links/темы/download НЕ делались (вне объёма).

## Примечания по деплою (не в этом плане)

- Перед push: включить GitHub Pages (см. память [[pages-enable-before-push]]) иначе deploy-job 404.
- Сетевые git/gh вызовы оборачивать в retry (см. [[happ-flaky-github-tls]]).
