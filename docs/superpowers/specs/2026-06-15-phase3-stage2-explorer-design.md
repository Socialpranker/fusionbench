# Фаза 3, этап 2 — explorer + deep-links + темы + download: design

**Дата:** 2026-06-15
**Статус:** одобрен (брейнсторм)
**Источник требований:** `docs/PROPOSAL-community-v2.md` §2.4 (deep-links, премиум-штрихи); раздел «Вне объёма» спеки ядра `2026-06-15-phase3-visual-v2-design.md`.
**База:** ядро Фазы 3 (hero-Pareto + heatmap) уже в ветке `phase3-visual` (PR #2).

## Цель

Достроить визуал v2 до полного UX из спеки: интерактивный explorer-вид, глобальные
фильтры с deep-links (URL-hash), авто dark/light-темы, экспорт CSV/JSON. Всё —
**чисто фронтовое**: `data.json` и `build_data` НЕ меняются (контракт уже полон).

## Что НЕ меняется

- `build_data` / контракт `site/data.json` — без изменений. `cells[]` уже содержит всё
  для пересчёта (type, recipe, arm, accuracy, cost_usd, latency_s,
  worthiness_vs_best/_vs_self_moa, complementarity, recommended, n).
- Единственная правка `scripts/build_catalog.py` в этом этапе — CSS-блок в шаблоне
  `PAGE` (dark-режим, см. «Темизация»). Логика генерации данных не трогается.
- `<noscript>`-SVG-фолбэк — без изменений (работает без JS).
- Существующие `tests/test_build_data.py` остаются зелёными (smoke подтверждает контракт).

## Архитектура и поток данных

Один `app.js` (вариант A — без сборки, секции-замыкания). Единый цикл обновления:
любое изменение (фильтр / hash / загрузка) → `update()` → `applyFilters(allCells)` →
пересчёт derived → ре-рендер 3 видов + запись hash (debounced) + обновление
download-данных. Один источник истины — `state`.

```
data.json ──fetch──> allCells
                        │
   state.filters ──> applyFilters(allCells) ──> derived.cells
                        │                            │
        aggregateRecipePoints(derived.cells) ──> recipe_points'
                        │                            │
                 paretoFrontier(recipe_points') ──> pareto'
                        │
        ┌───────────────┼───────────────┬───────────────┐
   renderHero      renderHeatmap   renderExplorer    export(CSV/JSON)
```

**Ключевой сдвиг vs ядро:** фильтры ГЛОБАЛЬНЫ → `app.js` сам выводит
`recipe_points`/`pareto` из ОТФИЛЬТРОВАННЫХ `cells` (в ядре брал готовыми из
`data.json`). `aggregateRecipePoints` и `paretoFrontier` — JS-дубль Python-логики
`build_data`/`pareto_frontier`. Это осознанно: интерактивный пересчёт обязан быть на
клиенте (статика, серверного round-trip нет). Готовые `recipe_points`/`pareto` из
`data.json` — начальное состояние (пустой фильтр → совпадают).

### Секции одного `app.js`

| Секция | Ответственность | Тестируемо |
|---|---|---|
| `STATE` | `state = {filters, ...}`, дефолты | — |
| `DERIVE` | `applyFilters`, `aggregateRecipePoints`, `paretoFrontier`, `toCSV` — чистые | ✅ node |
| `VIEWS` | `renderHero/Heatmap/Explorer` (учитывают тему) | — |
| `CONTROLS` | фильтр-UI, `parseHash`/`writeHash`, debounce | — |
| `THEME` | `matchMedia`→палитра, ре-рендер на смену | — |
| boot | `fetch data.json` → `parseHash` → `update` | — |

Чистые `DERIVE`-функции экспортируются UMD-стилем для node-тестов:
`if (typeof module !== "undefined") module.exports = {...}` в конце файла (браузер
игнорирует, node импортирует). Браузерная часть — IIFE поверх них.

## Фильтры и deep-links

`state.filters`:

| Поле | URL-hash | Тип | Дефолт |
|---|---|---|---|
| type | `type=math` | enum (code/deep_research/multihop_qa/math/factual) или пусто | все |
| maxcost | `maxcost=0.005` | число, верхняя граница `cost_usd` | ∞ |
| minacc | `minacc=0.7` | число 0..1, нижняя граница `accuracy` | 0 |
| sort | `sort=worthiness` | enum: worthiness\|accuracy\|cost\|recipe | worthiness |

`applyFilters(cells)` =
`cells.filter(c => (!type || c.type===type) && c.cost_usd<=maxcost && c.accuracy>=minacc)`
затем сортировка по `sort` (worthiness/accuracy/cost desc; recipe — лексикографически).
Чистая функция.

**Deep-links** (формат спеки `#type=math&maxcost=0.005&minacc=0.7&sort=worthiness`):
- Чтение: при загрузке и `hashchange` → `parseHash()` → `state.filters`. Невалидные
  значения (неизвестный type, нечисловой maxcost) игнорируются → дефолт, без падения.
- Запись: при изменении фильтра → `writeHash()` через `history.replaceState` (не плодим
  историю); только НЕдефолтные ключи (чистый URL).
- Петля: флаг `applyingHash` — пока применяем hash→UI, не пишем обратно.
- Слайдеры: графики обновляются на `input` (живо), запись hash — debounce ~200мс.

**Фильтр-UI** (панель над hero): `<select>` type, `<input type=range>` maxcost и minacc
(с числовыми подписями; min/max берутся из реальных данных через `Math.min/max` по
cells), `<select>` sort, кнопка «Reset» (сброс к дефолтам + очистка hash).

## Explorer-вид

Фильтруемый scatter + синхронная таблица под общим фильтром (оба из `derived.cells`).

- **Scatter** (`#explorer-chart`, ECharts): точка на каждую отфильтрованную cell,
  `value:[cost_usd, accuracy]`, цвет `ARM_COLOR[arm]`, размер по `n` (нормированный
  symbolSize), tooltip `recipe / type · acc% · $cost · worth±%`. Лог-ось cost с guard
  `cost_usd>0` (как в ядре).
- **Таблица** (`#explorer-table`, HTML через `createElement`/`textContent` — НЕ
  innerHTML): колонки type, recipe, arm, accuracy, cost, worthiness, compl., n; та же
  отфильтрованная+сортированная выборка; клик по заголовку = смена `sort` (синхрон с
  hash). Строки `recommended` — класс `.rec` (CSS уже есть).

## Темизация (авто prefers-color-scheme)

- **CSS** (в генеримом `index.html`, шаблон `PAGE` в `build_catalog.py`): добавить
  `@media (prefers-color-scheme: dark)` с инверсией токенов (bg `#f8fafc`→тёмный, text
  `#111827`→светлый, card/border/verdict/foot). `:root{color-scheme:light}` →
  `color-scheme: light dark`. Это ЕДИНСТВЕННАЯ правка `build_catalog.py` в этапе 2
  (только CSS-блок, не логика).
- **ECharts** (`app.js`): `var dark = matchMedia('(prefers-color-scheme: dark)').matches`.
  От него — цвет осей/текста/сетки/фон tooltip. `ARM_COLOR` и heatmap-градиент
  (red→neutral→green) семантические — НЕ инвертируются. На `matchMedia` change —
  ре-рендер графиков (ECharts не перечитывает цвета сам). Контейнеры прозрачны.

## Download (CSV/JSON)

Две кнопки у explorer. Выгружается ОТФИЛЬТРОВАННЫЙ набор (что на экране).
- `toCSV(cells)` — фиксированный список колонок, экранирование значений с запятыми/
  кавычками (`"..."`). Чистая функция (тестируется).
- JSON — `JSON.stringify(derived.cells, null, 2)`.
- Скачивание: `Blob` + `URL.createObjectURL` + временная `<a download>`; имена
  `fusionbench-cells.csv` / `.json`. `URL.revokeObjectURL` после.

## Обработка ошибок

- Нет ECharts / `data.json` → `fail()` в контейнеры (как ядро).
- Пустой результат фильтра → виды показывают «нет данных под текущий фильтр» (не пустой
  холст), кнопка Reset видна.
- Невалидный hash → дефолты, не падаем.

## Тестирование

- **node-юниты** `tests/site_logic.test.mjs`: импорт 4 чистых функций (`applyFilters`,
  `aggregateRecipePoints`, `paretoFrontier`, `toCSV`) из `site/app.js` через
  `module.exports`; проверки: фильтр по type/maxcost/minacc, сортировка, агрегация
  совпадает с Python-`build_data` на тех же входах, pareto-фронт отбрасывает
  доминируемые, CSV экранирует запятые/кавычки. Запуск `node tests/site_logic.test.mjs`.
- **Python smoke** (существующий `test_build_data.py`): контракт `data.json` цел.
- **Ручной Playwright** (перед «готово»): фильтр меняет все 3 вида; hash
  пишется/читается (открыть ссылку с `#type=math` → фильтр восстановлен); dark-режим
  (эмуляция `prefers-color-scheme: dark` → графики/страница тёмные); CSV/JSON
  скачиваются с отфильтрованным набором.

## Деплой

`build_catalog.py` по-прежнему пишет `site/index.html` + `data.json`; `app.js` —
трекаемый исходник (`.gitignore`: `site/*` + `!site/app.js`). `pages.yml` не меняется.
node для тестов — dev-зависимость окружения (в CI добавить шаг, если потребуется;
вне объёма этого этапа).

## Вне объёма

complementarity-вид (попарная error-декорреляция требует смены data-модели —
`CatalogRow` хранит скаляр, не попарно); ручной тоггл темы (берём только авто);
методология-ссылки у графиков (отдельная доковая правка).
