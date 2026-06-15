# Фаза 3 — Визуал v2 (ядро): design

**Дата:** 2026-06-15
**Статус:** одобрен (брейнсторм)
**Источник требований:** `docs/PROPOSAL-community-v2.md` §2 (строки 185–248)
**Объём:** ядро — `data.json` + hero-Pareto + heatmap. Explorer, deep-links (URL-hash),
dark/light-темы и download — **вне этой итерации** (следующий этап Фазы 3).

## Цель

Переписать публикацию каталога: вместо одного самодостаточного `site/index.html`
с инлайн-SVG — эмитить машинно-читаемый `site/data.json` и рисовать графики на
ECharts из него. Текущий SVG-рендер сохраняется как фолбэк (graceful degradation
без JS / при недоступности CDN).

## Архитектура и поток данных

```
runs/*.jsonl  ──>  build_catalog.py  ──┬──> site/data.json   (генерится: контракт §2.1)
 (CatalogRow)       ├─ load_rows/dedupe │
                    ├─ build_data(rows) ─┘   ← новая чистая функция, эмитит dict
                    └─ render_fallback() ──> site/index.html (каркас + <noscript> SVG+таблицы)

site/app.js  (СТАТИЧНЫЙ, в git) ── fetch('data.json') ──> ECharts: hero-Pareto + heatmap
site/index.html ── <script src=ECharts CDN> + <script src=app.js>
```

Три артефакта в `site/`, с чёткой границей ответственности:
данные (`data.json`, генерится) ⊥ логика рендера (`app.js`, статичный) ⊥
каркас + фолбэк (`index.html`, генерится с актуальным `<noscript>`-SVG).

- **`data.json`** — генерится `build_data(rows)`. Контракт ниже.
- **`index.html`** — генерится `build_catalog`. Каркас: подключает ECharts-CDN и
  `app.js`, контейнеры под 2 графика, заголовок + вердикт. Внутри `<noscript>` —
  текущий статичный SVG-Pareto + таблицы (фолбэк без JS / при CDN-фейле).
- **`app.js`** — статичный рукописный файл (в git, не генерится). `fetch('data.json')`
  → строит hero-Pareto (§2.2) и heatmap (§2.3). Данные-независим → редактируется как
  обычный JS, проверяется глазами + Playwright.

## Контракт `site/data.json`

```json
{
  "generated": "2026-06-15",
  "suites": ["frames", "ruler", "ifbench"],
  "recipes": [
    {"name": "best-single", "arm": "best_single"},
    {"name": "fusion-strong", "arm": "fusion"}
  ],
  "cells": [
    {"type": "multihop_qa", "recipe": "fusion-strong", "arm": "fusion",
     "accuracy": 0.71, "cost_usd": 0.0044, "latency_s": 1.6,
     "worthiness_vs_best": 0.05, "worthiness_vs_self_moa": 0.10,
     "complementarity": 0.79, "recommended": true, "n": 150}
  ],
  "recipe_points": [
    {"recipe": "fusion-strong", "arm": "fusion", "accuracy": 0.68, "cost_usd": 0.0041}
  ],
  "pareto": [
    {"cost_usd": 0.0009, "accuracy": 0.55},
    {"cost_usd": 0.0041, "accuracy": 0.68}
  ],
  "complementarity": [
    {"a": "gemini-3-flash", "b": "kimi-k2.6", "type": "multihop_qa", "value": 0.81}
  ]
}
```

**Маппинг `CatalogRow` → ячейка `cells[]`:** `task_type→type`, `recipe`, `arm`,
`accuracy`, `mean_cost_usd→cost_usd`, `mean_latency_s→latency_s`, `worthiness_vs_best`,
`worthiness_vs_self_moa`, `complementarity` (может быть `null`), `n_tasks→n`.
`recommended` — флаг, выставляется при сборке.

**Срезы (два разных, не дублируются):**
- `recipe_points[]` + `pareto[]` — **средние по рецепту across task_type** (как текущий
  `svg_scatter`, строки 204–213). Это срез для hero-Pareto: одна точка на рецепт.
- `cells[]` — **детализация recipe × type**. Срез для heatmap (`worthiness_vs_best` по
  сетке) и таблиц-фолбэка.

`complementarity[]` эмитится (данные дёшевы и нужны следующему этапу), но **в ядре не
визуализируется** — hero-Pareto и heatmap его не используют. Это не противоречие: поле
готовится впрок, рисовать его будет explorer вне этой итерации.

## Расчёты (в Python, кладутся готовыми в `data.json`)

JS только рисует — никакой бизнес-логики в `app.js`.

1. **`pareto_frontier(points)`** — выносится в отдельную чистую функцию из текущего
   `svg_scatter` (строки 88–92: сортировка по cost↑, накопление растущей accuracy).
   Вход — `recipe_points`, выход — отсортированный фронт non-dominated точек → `pareto[]`.
2. **`recommended`** per type — переиспользуем существующую `recommended(rows)`
   (`min` по `(-accuracy, cost)`) внутри каждого `type`; победившая ячейка получает
   `recommended: true`.
3. **`worthiness_vs_best`** — уже в `CatalogRow`, прокидывается в `cells[]` для heatmap.

## Компоненты `build_catalog.py` (после рефактора)

| Функция | Роль | Статус |
|---|---|---|
| `load_rows`, `dedupe` | чтение runs/*.jsonl | без изменений |
| `pareto_frontier(points)` | фронт non-dominated | выносится из `svg_scatter` |
| `build_data(rows) -> dict` | эмит контракта `data.json` | новая, чистая, ядро TDD |
| `render_fallback(rows) -> str` | каркас HTML + `<noscript>` SVG+таблицы | переименованный `render` |
| `main` | пишет `data.json` + `index.html` | дополняется вторым выходом |

Существующие `svg_scatter`, `compl_bars`, рендер таблиц — уходят в `<noscript>`-ветку
`render_fallback`. Ничего не выкидываем.

## Обработка ошибок

- `build_catalog` без строк → `SystemExit` (как сейчас).
- `app.js`: `fetch('data.json')` падает → сообщение в контейнере, не белый экран.
- ECharts-CDN недоступен при включённом JS → `app.js` проверяет
  `typeof echarts === 'undefined'` и оставляет видимым фолбэк-блок (`<noscript>` сам
  не сработает, если JS есть, но CDN лёг — поэтому нужна явная проверка).
- `data.json` с пустыми `cells` → graceful «нет данных».

## Тестирование

- **`tests/test_build_data.py`** (новый, TDD):
  - схема `data.json`: ключи `cells/recipes/recipe_points/pareto/complementarity`;
  - `pareto_frontier` на известных точках: фронт корректен, доминируемые отброшены;
  - `recommended`-флаг ровно на лучшей ячейке per type;
  - JSON-сериализуемость: `json.dumps(build_data(rows))` не падает; `null` для
    отсутствующей `complementarity`.
- **smoke:** `build_catalog` на `runs/catalog.jsonl` пишет `data.json` + `index.html`;
  JSON парсится, HTML содержит контейнеры графиков + `<noscript>`-блок.
- **ручная проверка рендера** (перед «готово», не в CI): `python -m http.server` +
  Playwright (webapp-testing) — canvas рисуется, нет console-ошибок.

## Деплой

`.github/workflows/pages.yml` менять не нужно: он зовёт `make site` → `build_catalog`,
который теперь пишет оба файла. `app.js` и `data.json` лежат в `site/`, деплоятся как есть.

## Вне объёма (следующий этап Фазы 3)

Explorer-вид, deep-links (URL-hash `#type=...&maxcost=...`), dark/light-темы с
едиными цвето-токенами по arm, кнопки «скачать CSV/JSON». Контракт `data.json` уже
содержит всё нужное для них (`cells` с полными полями, `complementarity`), так что
следующий этап — чисто фронтовый, без изменения генерации данных.
