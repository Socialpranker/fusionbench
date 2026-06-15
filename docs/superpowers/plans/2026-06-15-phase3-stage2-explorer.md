# Фаза 3 этап 2 — explorer + deep-links + темы + download: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Достроить `site/app.js` до полного UX визуала v2: глобальные фильтры с deep-links (URL-hash), explorer-вид (scatter + таблица), авто dark/light-темы, экспорт CSV/JSON — всё чисто фронтовое, `data.json`/`build_data` не меняются.

**Architecture:** Один `site/app.js` (вариант A, без сборки), разбитый на секции-замыкания: STATE (фильтры+тема) → DERIVE (чистые `applyFilters`/`aggregateRecipePoints`/`paretoFrontierJS`/`toCSV`) → VIEWS (renderHero/Heatmap/Explorer) → CONTROLS (фильтр-UI + hash) → THEME. Глобальный фильтр питает все 3 вида; `update()` — единый цикл пересчёта+рендера. Чистые DERIVE-функции экспортируются UMD-стилем (`module.exports`) для node-тестов.

**Tech Stack:** ECharts 5.5.1 (CDN), ванильный JS (без сборки), node для юнит-тестов чистых функций. `build_catalog.py` — только CSS dark-блок. Интерпретатор Python для smoke: `.venv/bin/python`. node: `node` из PATH.

**Источники:** спека `docs/superpowers/specs/2026-06-15-phase3-stage2-explorer-design.md`; proposal §2.4.

---

## Контекст: текущий `site/app.js` (ядро, уже в ветке)

Сейчас `app.js` — IIFE с `ARM_COLOR`, `fail()`, проверкой ECharts, `fetch('data.json').then(render)`, `render()` (зовёт renderHero+renderHeatmap+resize), `renderHero(data)` (scatter из `data.recipe_points` + dashed-фронт из `data.pareto`), `renderHeatmap(data)` (из `data.cells`). Этап 2 ПЕРЕСТРАИВАЕТ этот файл: добавляет state/derive/controls/theme/explorer/export, при этом hero/heatmap начинают питаться ОТФИЛЬТРОВАННЫМИ данными (пересчитанными в JS), а не сырыми `data.recipe_points`/`data.pareto`.

**Контракт `data.json` (не меняется):** `cells[]` элемент = `{type, recipe, arm, accuracy, cost_usd, latency_s, worthiness_vs_best, worthiness_vs_self_moa, complementarity, recommended, n}`. Также `recipe_points[]`, `pareto[]`, `recipes[]`, `suites`, `complementarity[]`, `generated`.

---

## File Structure

- **Modify** `site/app.js` — основной объём (секции + UMD-экспорт чистых функций).
- **Modify** `scripts/build_catalog.py` — ТОЛЬКО CSS-блок в шаблоне `PAGE` (dark-режим) + добавить в body контейнеры фильтр-панели и explorer.
- **Create** `tests/site_logic.test.mjs` — node-юниты на 4 чистые функции.
- `site/index.html` — генерится (не правится руками).

---

## Task 1: DERIVE — чистые функции фильтрации/агрегации (UMD + node-тесты)

**Files:**
- Modify: `site/app.js` (добавить чистые функции + UMD-экспорт)
- Create: `tests/site_logic.test.mjs`

- [ ] **Step 1: Написать падающий node-тест**

Создать `tests/site_logic.test.mjs`:

```javascript
// tests/site_logic.test.mjs — node unit tests for the pure DERIVE functions in site/app.js.
// Run: node tests/site_logic.test.mjs
import assert from "node:assert";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const app = require(path.join(here, "..", "site", "app.js"));

const CELLS = [
  { type: "math", recipe: "best-single", arm: "best_single", accuracy: 0.60, cost_usd: 0.001, worthiness_vs_best: 0.0, complementarity: null, recommended: false, n: 10 },
  { type: "math", recipe: "fusion-strong", arm: "fusion", accuracy: 0.80, cost_usd: 0.004, worthiness_vs_best: 0.20, complementarity: 0.7, recommended: true, n: 10 },
  { type: "code", recipe: "best-single", arm: "best_single", accuracy: 0.90, cost_usd: 0.0009, worthiness_vs_best: 0.0, complementarity: null, recommended: true, n: 8 },
];

// applyFilters: type filter
let r = app.applyFilters(CELLS, { type: "math", maxcost: Infinity, minacc: 0, sort: "worthiness" });
assert.strictEqual(r.length, 2, "type=math keeps 2");
assert.ok(r.every(c => c.type === "math"));

// applyFilters: maxcost + minacc
r = app.applyFilters(CELLS, { type: "", maxcost: 0.002, minacc: 0.7, sort: "worthiness" });
assert.deepStrictEqual(r.map(c => c.recipe), ["best-single"], "code/best-single passes cost<=0.002 & acc>=0.7");

// applyFilters: sort by accuracy desc
r = app.applyFilters(CELLS, { type: "", maxcost: Infinity, minacc: 0, sort: "accuracy" });
assert.deepStrictEqual(r.map(c => c.accuracy), [0.90, 0.80, 0.60], "sorted by accuracy desc");

// aggregateRecipePoints: mean cost/accuracy per recipe across kept cells
const pts = app.aggregateRecipePoints(CELLS);
const bs = pts.find(p => p.recipe === "best-single");
assert.strictEqual(bs.arm, "best_single");
assert.ok(Math.abs(bs.accuracy - (0.60 + 0.90) / 2) < 1e-9, "best-single avg accuracy");
assert.ok(Math.abs(bs.cost_usd - (0.001 + 0.0009) / 2) < 1e-9, "best-single avg cost");

// paretoFrontierJS: non-dominated, cost ascending
const front = app.paretoFrontierJS(pts);
const fcosts = front.map(p => p.cost_usd);
assert.deepStrictEqual(fcosts, [...fcosts].sort((a, b) => a - b), "pareto cost ascending");
assert.ok(front.length >= 1);

// toCSV: header + escaping of commas/quotes
const csv = app.toCSV([{ type: "math", recipe: 'a,b', arm: 'q"x', accuracy: 0.5, cost_usd: 0.001, latency_s: 0, worthiness_vs_best: 0.1, worthiness_vs_self_moa: 0, complementarity: null, recommended: true, n: 5 }]);
const lines = csv.trim().split("\n");
assert.ok(lines[0].startsWith("type,recipe,arm,accuracy,cost_usd"), "csv header");
assert.ok(lines[1].includes('"a,b"'), "comma value quoted");
assert.ok(lines[1].includes('"q""x"'), "quote value escaped & doubled");

console.log("site_logic: all assertions passed");
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `node tests/site_logic.test.mjs`
Expected: FAIL — `Cannot find module` или `app.applyFilters is not a function` (функций и экспорта ещё нет).

- [ ] **Step 3: Добавить чистые функции + UMD-экспорт в `site/app.js`**

В `site/app.js`, ВЫШЕ строки `(function () {` (в самом верху файла, после комментария-шапки), добавить чистые функции и UMD-экспорт. Вставить блок:

```javascript
// ===== DERIVE: pure functions (filter / aggregate / pareto / csv) =====
// Shared by the browser IIFE below and by node unit tests (UMD export at EOF).
function applyFilters(cells, f) {
  var out = cells.filter(function (c) {
    return (!f.type || c.type === f.type) &&
           c.cost_usd <= f.maxcost &&
           c.accuracy >= f.minacc;
  });
  var sort = f.sort || "worthiness";
  out.sort(function (a, b) {
    if (sort === "recipe") return a.recipe < b.recipe ? -1 : a.recipe > b.recipe ? 1 : 0;
    if (sort === "cost") return a.cost_usd - b.cost_usd;            // cheapest first
    if (sort === "accuracy") return b.accuracy - a.accuracy;        // best first
    return b.worthiness_vs_best - a.worthiness_vs_best;             // worthiness: best first
  });
  return out;
}

function aggregateRecipePoints(cells) {
  var byRecipe = {};
  cells.forEach(function (c) {
    (byRecipe[c.recipe] = byRecipe[c.recipe] || []).push(c);
  });
  return Object.keys(byRecipe).sort().map(function (name) {
    var rs = byRecipe[name];
    var acc = rs.reduce(function (s, c) { return s + c.accuracy; }, 0) / rs.length;
    var cost = rs.reduce(function (s, c) { return s + c.cost_usd; }, 0) / rs.length;
    return { recipe: name, arm: rs[0].arm, accuracy: acc, cost_usd: cost };
  });
}

function paretoFrontierJS(points) {
  var pts = points.slice().sort(function (a, b) { return a.cost_usd - b.cost_usd; });
  var front = [];
  var bestA = -1;
  pts.forEach(function (v) {
    if (v.accuracy > bestA + 1e-9) {
      front.push({ cost_usd: v.cost_usd, accuracy: v.accuracy });
      bestA = v.accuracy;
    }
  });
  return front;
}

var CSV_COLS = ["type", "recipe", "arm", "accuracy", "cost_usd", "latency_s",
  "worthiness_vs_best", "worthiness_vs_self_moa", "complementarity", "recommended", "n"];

function csvCell(v) {
  if (v === null || v === undefined) return "";
  var s = String(v);
  if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
  return s;
}

function toCSV(cells) {
  var head = CSV_COLS.join(",");
  var rows = cells.map(function (c) {
    return CSV_COLS.map(function (k) { return csvCell(c[k]); }).join(",");
  });
  return head + "\n" + rows.join("\n") + "\n";
}
```

В САМОМ КОНЦЕ файла (после закрывающей `})();` IIFE) добавить UMD-экспорт:

```javascript
// UMD export for node unit tests (browser ignores this).
if (typeof module !== "undefined" && module.exports) {
  module.exports = { applyFilters: applyFilters, aggregateRecipePoints: aggregateRecipePoints,
                     paretoFrontierJS: paretoFrontierJS, toCSV: toCSV };
}
```

ВАЖНО: функции объявлены через `function name(){}` в области файла (вне IIFE), поэтому видны и IIFE, и UMD-экспорту. IIFE (браузерная часть) пока их не использует — это Task 2+.

- [ ] **Step 4: Прогнать тест — PASS**

Run: `node tests/site_logic.test.mjs`
Expected: `site_logic: all assertions passed`.
Также: `node --check site/app.js` → синтаксис ок. И существующий Python smoke не затронут: `.venv/bin/python -m pytest tests/test_build_data.py -q` → 7 passed.

- [ ] **Step 5: Commit**

```bash
git add site/app.js tests/site_logic.test.mjs
git commit -m "feat: DERIVE-функции app.js (filter/aggregate/pareto/csv) + node-тесты"
```

---

## Task 2: STATE + update() + hero/heatmap от отфильтрованных данных

**Files:**
- Modify: `site/app.js` (IIFE: state, update, переключить renderHero/Heatmap на derived)

- [ ] **Step 1: Перестроить IIFE на единый цикл update()**

Внутри IIFE (после `fail()` и проверки echarts) заменить блок `fetch(...).then(render)` и функцию `render` на state-driven цикл. Сохранить `renderHero`/`renderHeatmap`, но они теперь принимают УЖЕ вычисленные `recipePoints`/`pareto`/`cells`, а не сырой `data`.

Заменить текущее:
```javascript
  fetch("data.json")
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(render)
    .catch(function (e) { fail("Could not load data.json: " + e.message); });

  function render(data) {
    var charts = [renderHero(data), renderHeatmap(data)];
    window.addEventListener("resize", function () {
      charts.forEach(function (c) { if (c) c.resize(); });
    });
  }
```
на:
```javascript
  var ALL = [];                        // all cells from data.json
  var state = { filters: { type: "", maxcost: Infinity, minacc: 0, sort: "worthiness" } };
  var charts = [];

  fetch("data.json")
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) {
      ALL = data.cells || [];
      update();
      window.addEventListener("resize", function () {
        charts.forEach(function (c) { if (c) c.resize(); });
      });
    })
    .catch(function (e) { fail("Could not load data.json: " + e.message); });

  function update() {
    var cells = applyFilters(ALL, state.filters);
    var pts = aggregateRecipePoints(cells);
    var pareto = paretoFrontierJS(pts);
    charts = [renderHero(pts, pareto), renderHeatmap(cells)];
  }
```

- [ ] **Step 2: Переписать сигнатуры renderHero/renderHeatmap на derived-вход**

`renderHero(data)` → `renderHero(recipePoints, pareto)`. Внутри заменить `var pts = data.recipe_points || [];` на `var pts = recipePoints || [];`, а dashed-линию — на `(pareto || [])`. Тело (фильтр cost>0, scatter, ось) — без изменений, кроме источника данных:

```javascript
  function renderHero(recipePoints, pareto) {
    var pts = (recipePoints || []).filter(function (c) { return c.cost_usd > 0; });
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
          data: (pareto || []).filter(function (p) { return p.cost_usd > 0; })
                  .map(function (p) { return [p.cost_usd, p.accuracy]; })
        }
      ]
    });
    return hero;
  }
```

`renderHeatmap(data)` → `renderHeatmap(cells)`: заменить первую строку `var cells = data.cells || [];` на `cells = cells || [];`. Остальное тело без изменений.

- [ ] **Step 2b: Пустой фильтр → сообщение, не пустой холст**

В начало `update()` добавить guard:
```javascript
  function update() {
    var cells = applyFilters(ALL, state.filters);
    if (!cells.length) {
      fail("Нет данных под текущий фильтр. Сбросьте фильтры.");
      charts = [];
      return;
    }
    var pts = aggregateRecipePoints(cells);
    var pareto = paretoFrontierJS(pts);
    charts = [renderHero(pts, pareto), renderHeatmap(cells)];
  }
```

- [ ] **Step 3: Проверить рендер вручную**

Run (фон): `.venv/bin/python -m http.server 8770 --directory site` (предварительно сгенерить сайт: `.venv/bin/python scripts/build_catalog.py --runs "runs/*.jsonl" --out site/index.html`).
Открыть `http://localhost:8770/` — hero и heatmap должны рисоваться как раньше (фильтр пустой → все данные). `node --check site/app.js` → ок. Остановить сервер.

- [ ] **Step 4: Тесты не сломаны**

Run: `node tests/site_logic.test.mjs` (PASS) и `.venv/bin/python -m pytest tests/test_build_data.py -q` (7 passed).

- [ ] **Step 5: Commit**

```bash
git add site/app.js
git commit -m "feat: app.js — глобальный state + update(), hero/heatmap от отфильтрованных данных"
```

---

## Task 3: Фильтр-UI + deep-links (URL-hash)

**Files:**
- Modify: `scripts/build_catalog.py` (добавить фильтр-панель в body шаблона PAGE)
- Modify: `site/app.js` (CONTROLS: построить UI, parseHash/writeHash, debounce)

- [ ] **Step 1: Добавить контейнер фильтр-панели в шаблон PAGE**

В `scripts/build_catalog.py`, в шаблоне `PAGE`, ПЕРЕД `<h2>Cost vs quality</h2>` (которое идёт перед `<div id="hero">`) вставить контейнер панели:
```python
<div id="filters" class="card" style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-top:8px"></div>
```
(app.js наполнит его контролами; пустой div до загрузки JS — ок, в noscript его нет.)

- [ ] **Step 2: Реализовать CONTROLS в app.js**

Добавить в IIFE функции построения UI и hash-синка. После `update`:

```javascript
  var TASK_TYPES = ["code", "deep_research", "multihop_qa", "math", "factual"];
  var SORTS = ["worthiness", "accuracy", "cost", "recipe"];
  var applyingHash = false;
  var hashTimer = null;

  function parseHash() {
    var h = (location.hash || "").replace(/^#/, "");
    var p = {};
    h.split("&").forEach(function (kv) {
      var i = kv.indexOf("=");
      if (i > 0) p[decodeURIComponent(kv.slice(0, i))] = decodeURIComponent(kv.slice(i + 1));
    });
    var f = { type: "", maxcost: Infinity, minacc: 0, sort: "worthiness" };
    if (TASK_TYPES.indexOf(p.type) >= 0) f.type = p.type;
    if (p.maxcost && !isNaN(parseFloat(p.maxcost))) f.maxcost = parseFloat(p.maxcost);
    if (p.minacc && !isNaN(parseFloat(p.minacc))) f.minacc = parseFloat(p.minacc);
    if (SORTS.indexOf(p.sort) >= 0) f.sort = p.sort;
    return f;
  }

  function writeHash() {
    if (applyingHash) return;                 // don't write back while applying a hash
    var f = state.filters, parts = [];
    if (f.type) parts.push("type=" + f.type);
    if (f.maxcost !== Infinity) parts.push("maxcost=" + f.maxcost);
    if (f.minacc > 0) parts.push("minacc=" + f.minacc);
    if (f.sort !== "worthiness") parts.push("sort=" + f.sort);
    var hash = parts.length ? "#" + parts.join("&") : "";
    if (location.hash !== hash) {
      history.replaceState(null, "", hash || (location.pathname + location.search));
    }
  }

  function writeHashDebounced() {
    if (hashTimer) clearTimeout(hashTimer);
    hashTimer = setTimeout(writeHash, 200);
  }

  function costBounds() {
    var costs = ALL.map(function (c) { return c.cost_usd; }).filter(function (x) { return x > 0; });
    return { min: Math.min.apply(null, costs), max: Math.max.apply(null, costs) };
  }

  function buildControls() {
    var box = document.getElementById("filters");
    if (!box) return;
    box.textContent = "";
    var cb = costBounds();

    var typeSel = document.createElement("select");
    [""].concat(TASK_TYPES).forEach(function (t) {
      var o = document.createElement("option"); o.value = t; o.textContent = t || "all types";
      if (t === state.filters.type) o.selected = true; typeSel.appendChild(o);
    });
    typeSel.onchange = function () { state.filters.type = typeSel.value; update(); writeHash(); };

    var maxc = document.createElement("input");
    maxc.type = "range"; maxc.min = cb.min; maxc.max = cb.max;
    maxc.step = (cb.max - cb.min) / 100 || 0.0001;
    maxc.value = state.filters.maxcost === Infinity ? cb.max : state.filters.maxcost;
    var maxcLbl = document.createElement("span");
    maxcLbl.textContent = "≤ $" + Number(maxc.value).toFixed(4);
    maxc.oninput = function () {
      state.filters.maxcost = parseFloat(maxc.value);
      maxcLbl.textContent = "≤ $" + parseFloat(maxc.value).toFixed(4);
      update(); writeHashDebounced();
    };

    var minacc = document.createElement("input");
    minacc.type = "range"; minacc.min = 0; minacc.max = 1; minacc.step = 0.01;
    minacc.value = state.filters.minacc;
    var minaccLbl = document.createElement("span");
    minaccLbl.textContent = "acc ≥ " + Math.round(state.filters.minacc * 100) + "%";
    minacc.oninput = function () {
      state.filters.minacc = parseFloat(minacc.value);
      minaccLbl.textContent = "acc ≥ " + Math.round(parseFloat(minacc.value) * 100) + "%";
      update(); writeHashDebounced();
    };

    var sortSel = document.createElement("select");
    SORTS.forEach(function (s) {
      var o = document.createElement("option"); o.value = s; o.textContent = "sort: " + s;
      if (s === state.filters.sort) o.selected = true; sortSel.appendChild(o);
    });
    sortSel.onchange = function () { state.filters.sort = sortSel.value; update(); writeHash(); };

    var reset = document.createElement("button");
    reset.textContent = "Reset";
    reset.onclick = function () {
      state.filters = { type: "", maxcost: Infinity, minacc: 0, sort: "worthiness" };
      buildControls(); update(); writeHash();
    };

    [labelWrap("type", typeSel), labelWrap("max cost", maxc, maxcLbl),
     labelWrap("min acc", minacc, minaccLbl), labelWrap("", sortSel), reset]
      .forEach(function (el) { box.appendChild(el); });
  }

  function labelWrap(text) {
    var wrap = document.createElement("label");
    wrap.style.display = "inline-flex"; wrap.style.alignItems = "center";
    wrap.style.gap = "6px"; wrap.style.fontSize = "13px"; wrap.style.color = "#6b7280";
    if (text) { var t = document.createElement("span"); t.textContent = text; wrap.appendChild(t); }
    for (var i = 1; i < arguments.length; i++) wrap.appendChild(arguments[i]);
    return wrap;
  }
```

Подключить hash к загрузке: в `.then(function (data) {...})` после `ALL = data.cells || [];` добавить:
```javascript
      state.filters = parseHash();
      buildControls();
      update();
      window.addEventListener("hashchange", function () {
        applyingHash = true;                  // suppress writeHash while applying external hash
        state.filters = parseHash(); buildControls(); update();
        applyingHash = false;
      });
```
(заменив прежний одиночный `update();` + resize-listener; resize-listener оставить).

- [ ] **Step 3: Проверить вручную (фильтры + hash)**

Сгенерить сайт, поднять `http.server 8770`. Проверить: select type меняет графики; слайдеры двигают порог; URL обновляется (`#type=math` и т.п.); открыть `http://localhost:8770/#type=math&minacc=0.5` — фильтры восстановлены. `node --check site/app.js` ок. Остановить сервер.

- [ ] **Step 4: Тесты не сломаны**

Run: `node tests/site_logic.test.mjs` (PASS); `.venv/bin/python -m pytest tests/test_build_data.py -q` (7 passed — smoke проверит, что HTML теперь содержит `id="filters"`; если smoke это не проверяет — просто остаётся зелёным).

- [ ] **Step 5: Commit**

```bash
git add scripts/build_catalog.py site/app.js
git commit -m "feat: фильтр-панель + deep-links (URL-hash) для всех видов"
```

---

## Task 4: Explorer-вид (scatter + таблица) + export CSV/JSON

**Files:**
- Modify: `scripts/build_catalog.py` (контейнеры explorer + кнопки в PAGE)
- Modify: `site/app.js` (renderExplorer, downloadCSV/JSON, подключить в update)

- [ ] **Step 1: Добавить explorer-контейнеры в PAGE**

В `scripts/build_catalog.py`, в шаблоне `PAGE`, ПОСЛЕ блока heatmap (`<div id="heatmap" ...></div>`) и ПЕРЕД `<noscript>`, вставить:
```python
<h2>Explorer</h2>
<div style="margin:8px 0">
  <button id="dl-csv">Скачать CSV</button>
  <button id="dl-json">Скачать JSON</button>
</div>
<div id="explorer-chart" class="card" style="height:420px"></div>
<div id="explorer-table" class="card" style="overflow-x:auto"></div>
```

- [ ] **Step 2: renderExplorer + export в app.js**

Добавить в IIFE:

```javascript
  function renderExplorer(cells) {
    // scatter
    var ec = echarts.init(document.getElementById("explorer-chart"));
    var maxN = Math.max.apply(null, cells.map(function (c) { return c.n || 1; }).concat([1]));
    ec.setOption({
      grid: { left: 56, right: 24, top: 24, bottom: 48 },
      xAxis: { type: "log", name: "cost per task ($)", nameLocation: "middle", nameGap: 30 },
      yAxis: { type: "value", name: "accuracy", min: 0, max: 1,
               axisLabel: { formatter: function (v) { return Math.round(v * 100) + "%"; } } },
      tooltip: {
        formatter: function (p) {
          var c = p.data.cell;
          return c.recipe + " / " + c.type + "<br>acc " + Math.round(c.accuracy * 100) +
                 "% · $" + c.cost_usd.toFixed(4) + " · worth " +
                 (c.worthiness_vs_best > 0 ? "+" : "") + Math.round(c.worthiness_vs_best * 100) + "%";
        }
      },
      series: [{
        type: "scatter",
        data: cells.filter(function (c) { return c.cost_usd > 0; }).map(function (c) {
          return { value: [c.cost_usd, c.accuracy], cell: c,
                   symbolSize: 8 + 18 * (c.n || 1) / maxN,
                   itemStyle: { color: ARM_COLOR[c.arm] || "#6b7280" } };
        })
      }]
    });

    // table (createElement / textContent — no innerHTML)
    var cols = ["type", "recipe", "arm", "accuracy", "cost_usd", "worthiness_vs_best", "complementarity", "n"];
    var host = document.getElementById("explorer-table");
    host.textContent = "";
    var tbl = document.createElement("table");
    var thead = document.createElement("thead");
    var htr = document.createElement("tr");
    cols.forEach(function (k) {
      var th = document.createElement("th"); th.textContent = k;
      th.style.cursor = "pointer";
      th.onclick = function () {
        var map = { accuracy: "accuracy", cost_usd: "cost", worthiness_vs_best: "worthiness", recipe: "recipe" };
        if (map[k]) { state.filters.sort = map[k]; buildControls(); update(); writeHash(); }
      };
      htr.appendChild(th);
    });
    thead.appendChild(htr); tbl.appendChild(thead);
    var tb = document.createElement("tbody");
    cells.forEach(function (c) {
      var tr = document.createElement("tr");
      if (c.recommended) tr.className = "rec";
      cols.forEach(function (k) {
        var td = document.createElement("td");
        var v = c[k];
        if (k === "accuracy") td.textContent = Math.round(v * 100) + "%";
        else if (k === "cost_usd") td.textContent = "$" + v.toFixed(4);
        else if (k === "worthiness_vs_best") td.textContent = (v > 0 ? "+" : "") + Math.round(v * 100) + "%";
        else if (k === "complementarity") td.textContent = v == null ? "—" : v.toFixed(2);
        else td.textContent = v;
        if (k === "accuracy" || k === "cost_usd" || k === "worthiness_vs_best" || k === "n") td.className = "num";
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    tbl.appendChild(tb); host.appendChild(tbl);
    return ec;
  }

  function downloadBlob(text, filename, mime) {
    var blob = new Blob([text], { type: mime });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = filename; document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  }

  function wireExport() {
    var csvBtn = document.getElementById("dl-csv");
    var jsonBtn = document.getElementById("dl-json");
    if (csvBtn) csvBtn.onclick = function () {
      downloadBlob(toCSV(applyFilters(ALL, state.filters)), "fusionbench-cells.csv", "text/csv");
    };
    if (jsonBtn) jsonBtn.onclick = function () {
      downloadBlob(JSON.stringify(applyFilters(ALL, state.filters), null, 2), "fusionbench-cells.json", "application/json");
    };
  }
```

Подключить explorer в `update()` и вызвать `wireExport()` один раз при загрузке. `update()` становится:
```javascript
  function update() {
    var cells = applyFilters(ALL, state.filters);
    if (!cells.length) { fail("Нет данных под текущий фильтр. Сбросьте фильтры."); charts = []; return; }
    var pts = aggregateRecipePoints(cells);
    var pareto = paretoFrontierJS(pts);
    charts = [renderHero(pts, pareto), renderHeatmap(cells), renderExplorer(cells)];
  }
```
И в загрузочный `.then` после `buildControls();` добавить `wireExport();`.

- [ ] **Step 3: Проверить вручную (explorer + export)**

Сгенерить сайт, `http.server 8770`. Проверить: explorer-scatter рисуется (точки по cells, размер по n); таблица отображается, клик по заголовку accuracy/cost меняет сортировку; кнопки CSV/JSON скачивают файл; при активном фильтре скачивается отфильтрованный набор. `node --check`. Остановить сервер.

- [ ] **Step 4: Тесты**

Run: `node tests/site_logic.test.mjs` (PASS); `.venv/bin/python -m pytest tests/test_build_data.py -q` (7 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/build_catalog.py site/app.js
git commit -m "feat: explorer-вид (scatter + таблица) + экспорт CSV/JSON отфильтрованного набора"
```

---

## Task 5: Темы (авто prefers-color-scheme)

**Files:**
- Modify: `scripts/build_catalog.py` (CSS dark-блок в PAGE)
- Modify: `site/app.js` (THEME: matchMedia → цвета ECharts, ре-рендер на смену)

- [ ] **Step 1: CSS dark-блок в шаблоне PAGE**

В `scripts/build_catalog.py`, в `<style>` шаблона `PAGE`, изменить `:root{{color-scheme:light}}` → `:root{{color-scheme:light dark}}` и ДОБАВИТЬ в конец `<style>` (перед `</style>`) media-блок (двойные фигурные скобки — экранирование для .format):
```python
@media (prefers-color-scheme: dark){{
  body{{background:#0f1419;color:#e5e7eb}}
  .sub,.foot,.bar-label,.bar-val,.legend{{color:#9ca3af}}
  .card,table{{background:#1a1f2e;border-color:#374151}}
  th{{background:#161b26;color:#9ca3af}}
  th,td{{border-color:#374151}}
  .verdict{{background:#0f2a1e;border-color:#14532d;color:#a7f3d0}}
  tr.rec{{background:#0f2a26}}
  #filters select,#filters input,button{{background:#1a1f2e;color:#e5e7eb;border:1px solid #374151}}
}}
```

- [ ] **Step 2: THEME в app.js**

Добавить в IIFE (до первого render):
```javascript
  function isDark() { return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches; }
  function axisColors() {
    return isDark()
      ? { axis: "#9ca3af", text: "#e5e7eb", split: "#374151" }
      : { axis: "#6b7280", text: "#111827", split: "#e5e7eb" };
  }
```
В `renderHero`, `renderHeatmap`, `renderExplorer` применить тему к осям. Конкретно — добавить в каждый `setOption` axis-цвета. Для hero/explorer (value+log оси) в `xAxis` и `yAxis` добавить:
```javascript
        axisLine: { lineStyle: { color: axisColors().axis } },
        axisLabel: { color: axisColors().text },
        splitLine: { lineStyle: { color: axisColors().split } },
        nameTextStyle: { color: axisColors().text },
```
(для yAxis hero/explorer сохранить существующий `axisLabel.formatter`, добавив `color`). Для heatmap category-осей добавить `axisLabel: { color: axisColors().text }` (сохранив rotate для xAxis).

При смене системной темы — ре-рендер: добавить в загрузочный `.then` после `wireExport();`:
```javascript
      if (window.matchMedia) {
        matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () { update(); });
      }
```

- [ ] **Step 3: Проверить вручную (тема)**

Сгенерить сайт, `http.server 8770`. Через Playwright с эмуляцией `prefers-color-scheme: dark` — страница тёмная (фон/текст/карточки), оси графиков читаемы на тёмном; в light — как раньше. `node --check`. Остановить сервер.

- [ ] **Step 4: Тесты**

Run: `node tests/site_logic.test.mjs` (PASS); `.venv/bin/python -m pytest tests/test_build_data.py -q` (7 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/build_catalog.py site/app.js
git commit -m "feat: авто dark/light темы (prefers-color-scheme) для страницы и графиков"
```

---

## Task 6: Регенерация сайта + полная проверка

**Files:**
- Modify (generated): `site/index.html`, `site/data.json`

- [ ] **Step 1: Сгенерировать финальный сайт**

Run: `.venv/bin/python scripts/build_catalog.py --runs "runs/*.jsonl" --out site/index.html`
Expected: `wrote site/index.html and site/data.json ...`. Проверить, что index.html содержит `id="filters"`, `id="explorer-chart"`, `id="explorer-table"`, `dl-csv`, `@media (prefers-color-scheme: dark)`:
`grep -cE 'id="filters"|id="explorer-chart"|id="explorer-table"|dl-csv|prefers-color-scheme' site/index.html`.

- [ ] **Step 2: Полный ручной Playwright-прогон**

Поднять `.venv/bin/python -m http.server 8770 --directory site` (фон). Через Playwright проверить целостный сценарий:
- загрузка: 3 ECharts-инстанса (hero, heatmap, explorer) → ≥3 canvas; нет console-ошибок;
- фильтр type=math → все 3 вида перестроились;
- слайдер minacc → URL-hash обновился (`#minacc=...`);
- открытие `http://localhost:8770/#type=math&minacc=0.5` → фильтры восстановлены;
- клик «Скачать CSV» → файл скачался (проверить download event);
- dark-эмуляция → тёмная страница, графики читаемы.
Сделать скриншот (light и dark). Остановить сервер.

- [ ] **Step 3: Все тесты**

Run: `node tests/site_logic.test.mjs` (PASS) и `.venv/bin/python -m pytest -q` (всё зелёное: прежние + test_build_data; норма 1 skipped + 1 xfailed).
Run: `ruff check scripts/build_catalog.py` (только pre-existing E702 ~83/85).

- [ ] **Step 4: Commit регенерированного сайта**

```bash
git add site/index.html site/data.json
git commit -m "chore: регенерировать site/ — explorer + фильтры + темы"
```

---

## Verification (перед «готово»)

- [ ] `node tests/site_logic.test.mjs` — все assertions passed.
- [ ] `.venv/bin/python -m pytest -q` — всё зелёное (контракт data.json цел).
- [ ] `node --check site/app.js` — синтаксис ок; нет `innerHTML` (grep пусто).
- [ ] Playwright: 3 графика; фильтры перестраивают все виды; hash read/write; CSV/JSON качаются; dark работает.
- [ ] `index.html` содержит фильтр-панель, explorer-контейнеры, dark CSS.
- [ ] Спека перечитана построчно: explorer, глобальные фильтры, deep-links, темы, download — реализованы; complementarity-вид/ручной тоггл — вне объёма (не делались).

## Примечания

- `app.js` не использует `innerHTML` нигде (только `textContent`/`createElement`) — проектный хук блокирует innerHTML.
- node — dev-зависимость для `site_logic.test.mjs`; в CI отдельный шаг не добавляем в этом этапе (вне объёма).
- Перед push/деплоем: Pages включить ([[pages-enable-before-push]]); сетевые git/gh в retry ([[happ-flaky-github-tls]]).
