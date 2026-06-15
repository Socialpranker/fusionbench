# phase3-visual

**Дата:** 2026-06-15 | **Статус:** в работе (ядро готово в PR #2; этап 2 заспланирован, НЕ начат)
**Цель:** Фаза 3 «визуал v2» FusionBench — переписать каталог-сайт на `data.json` + ECharts (Pareto + heatmap), затем достроить explorer/фильтры/темы/download.

## Продолжить работу

**Ближайшая задача: исполнить план этапа 2 через subagent-driven-development.** Контекст прошлой сессии раздулся (>400k) — поэтому handoff + /clear. План полностью самодостаточен.

1. Прочитай план: `docs/superpowers/plans/2026-06-15-phase3-stage2-explorer.md` (6 TDD-задач, весь код в шагах, без плейсхолдеров).
2. Запусти скилл `superpowers:subagent-driven-development`, исполняй задачи 1→6 по одной: на каждую — свежий субагент (implementer, model sonnet) → spec-review (haiku) → code-quality-review (sonnet) → фиксы → следующая. Точно так же собрали ядро Фазы 3 в этой сессии — паттерн рабочий.
3. После всех 6 задач — финальный целостный review всей реализации этапа 2, затем `finishing-a-development-branch`.

**Критично знать:**
- **Интерпретатор Python — `.venv/bin/python`** (НЕ `python`, его нет на PATH). pytest: `.venv/bin/python -m pytest -q`.
- **node** из PATH — для `tests/site_logic.test.mjs` (юниты чистых JS-функций). ECharts грузится с CDN — браузерная проверка нужна с реальной сетью к jsdelivr.
- **innerHTML запрещён** — проектный PreToolUse-хук блокирует его как XSS. В `app.js` только `textContent`/`createElement`. План это учитывает.
- **`site/` — build output в .gitignore** (`site/*` + `!site/app.js`). Трекается ТОЛЬКО `app.js`; `index.html`/`data.json` генерятся `build_catalog.py`, НЕ коммитятся как исходник (Task 6 их коммитит как регенерированный артефакт — это норма проекта). Грабли: нельзя `!site/app.js` при игноре каталога `site/` — нужно `site/*`. См. память [[site-gitignore-build-output]].
- **Ветка:** работаем в `phase3-visual` (этап 2 нарастает на ядро, тот же PR #2 обновится при push). PR #2 база — `phase2-integrity`.
- **Контракт `data.json` НЕ меняется** в этапе 2 (только CSS dark-блок в `build_catalog.py`). `cells[]` уже содержит всё для JS-пересчёта.

**Следующий шаг прямо сейчас:** `/clear` → новый чат → «Прочитай .claude/handoffs/phase3-visual.md и продолжи: исполни план этапа 2 (docs/superpowers/plans/2026-06-15-phase3-stage2-explorer.md) через subagent-driven».

## Сделано (эта сессия)

- **Ядро Фазы 3** (коммиты `ee89953..601965b`): `pareto_frontier` вынесена, `build_data`→`site/data.json`, `render`→`render_fallback` (SVG в `<noscript>`), `site/app.js` (hero-Pareto + heatmap на ECharts 5.5.1). Тесты `tests/test_build_data.py` (7). Рендер подтверждён в браузере. → **PR #2** (`phase3-visual` → `phase2-integrity`), OPEN.
- **Спека + план этапа 2** (`554be74`, `8e77a85`): explorer + deep-links + темы + download.
- (Ранее в сессии) Фаза 2: фикс анти-чита `regrade.py` (coverage+dedup, `cb3ea28`), документирование forged-prediction как known-limitation.

## Осталось

- [ ] **Исполнить план этапа 2** (6 задач) — главное.
- [ ] После этапа 2: финальный review + решение по веткам/мержу.
- [ ] **Перед деплоем сайта:** включить GitHub Pages ([[pages-enable-before-push]]) иначе deploy-job 404.
- [ ] **Фаза 2 (PR #1)** должна влиться в main ПЕРЕД Фазой 3 (Ф3 стоит поверх Ф2). У Фазы 2 были блокеры CI (RCE submit.yml и др.) — судя по заголовку PR #1 «+4 фикса блокеров», закрыты фоновой задачей; проверить статус PR #1 перед мержем.

## Решения

- **Explorer = фильтруемый scatter + синхронная таблица**, фильтры **глобальные** (все 3 вида) → `app.js` пересчитывает recipe_points/pareto из отфильтрованных cells (JS-дубль Python `build_data` — осознанно, статика без серверного round-trip).
- **Один `app.js` без сборки** (вариант A), секции STATE/DERIVE/VIEWS/CONTROLS/THEME; чистые DERIVE-функции с UMD-экспортом (`module.exports`) для node-тестов.
- **Темы — авто prefers-color-scheme** (без кнопки); ARM_COLOR/heatmap-градиент семантические, не инвертируются.
- **Download — отфильтрованные cells** (что на экране) в CSV/JSON через Blob.
- **Слайдеры:** живой `input` для графиков, debounce 200мс для записи URL-hash.
