# phase4-leaderboard

**Дата:** 2026-06-15 | **Статус:** спека + план готовы, реализация НЕ начата
**Цель:** Фаза 4 этап 1 FusionBench — движок очков за вклады + относительная доска лидеров.

## Продолжить работу

**Ближайшая задача: исполнить план через subagent-driven-development.** Контекст прошлой сессии раздулся (>360k) — поэтому handoff + /clear. Спека и план самодостаточны.

1. Прочитай план: `docs/superpowers/plans/2026-06-15-phase4-stage1-leaderboard.md` (6 TDD-задач, весь код в шагах, без плейсхолдеров). Спека: `docs/superpowers/specs/2026-06-15-phase4-stage1-leaderboard-design.md`.
2. Запусти скилл `superpowers:subagent-driven-development`, исполняй задачи 1→6 по одной: на каждую — свежий субагент (implementer, model sonnet) → spec-review (haiku) → code-quality-review (sonnet) → фиксы → следующая. Точно так же собрали этап 2 Фазы 3 — паттерн рабочий.
3. После всех 6 задач — финальный целостный review всей реализации, затем `finishing-a-development-branch`.

**Критично знать:**
- **Интерпретатор Python — `.venv/bin/python`** (НЕ `python`, его нет на PATH). pytest: `.venv/bin/python -m pytest -q`.
- **innerHTML запрещён** проектным PreToolUse-хуком. В `leaderboard.js` только `textContent`/`createElement`. План это учитывает.
- **gitignore:** трекать `site/leaderboard.js` через `!site/leaderboard.js` (как `!site/app.js`). `leaderboard.html`/`leaderboard.json` — build output, НЕ коммитятся. См. [[site-gitignore-build-output]].
- **verify-before-score** = «manifest в submissions/ на main = прошёл regrade» (regrade required-check блокирует мерж; вердикт нигде не персистится). Скрипт regrade НЕ перезапускает.
- **`--now` всегда снаружи** (CLI/CI `date`), НЕ генерить в Python — детерминизм тестов.
- **glob точечный** `submissions/*/manifest.json`, не широкий — [[run-v0-two-schemas-glob-trap]].
- **Ветка:** работаем в `phase4-leaderboard` (отведена от main, спека+план уже закоммичены: `3a6b254`, `ce16664`). База для PR — main.
- **ruff** не в venv, есть системный (`/Library/Frameworks/.../ruff`). **Playwright dark-эмуляция**: `page.emulateMedia({colorScheme:'dark'})` через `browser_run_code_unsafe` (обычный browser_evaluate тему не сменит) — см. [[phase3-visual-v2-design]].

**Следующий шаг прямо сейчас:** `/clear` → новый чат → «Прочитай .claude/handoffs/phase4-leaderboard.md и продолжи: исполни план Фазы 4 этап 1 через subagent-driven».

## Объём этапа 1 (из спеки)

**В объёме:** `score_contributions.py` (чистое ядро очков cell+лог-затухание `20·0.5^prior` + I/O→`leaderboard.json`) · отдельная страница `leaderboard.html`+`leaderboard.js` (относительная доска, бар к лидеру) · seed-фикстуры submissions · навигация catalog↔leaderboard · интеграция в `pages.yml` · pytest на ядро (затухание/мульти-юзер/пустой/malformed, герметично).

**ВНЕ объёма (следующие этапы):** Issue Form + бот, тиры/бейджи, воспроизведения + repro-fail метрика, веса за сьюты/адаптеры/багфиксы, рейт-лимит, CITATION.cff. (Фаза 5 — HF Space, отдельно.)

## Контекст проекта (на старте сессии)

- **Фазы 1–3 ВЛИТЫ в main** (PR #1/#2/#3 merged). Сайт живой: https://socialpranker.github.io/fusionbench/ (HTTP 200, деплой зелёный).
- Submission-инфра Фазы 2 работает: PR → `submit.yml` → `regrade.py` (required check). `submissions/` сейчас пуст (только структура+README) → поэтому seed-фикстуры для демо доски.
- Манифест: `submitted_by` (контрибьютор), `suite`+`claimed.recipe` (cell-ключ `"suite×recipe"`), `claimed.accuracy/cost_usd/n`, `run_id` (детерминированный порядок для затухания).

## Решения брейнсторма

- Объём = движок очков + доска (не бот-первым). Источник = `submissions/*/manifest.json` + seed.
- Доска = отдельная `leaderboard.html` (не секция index.html) — чистое разделение каталог/люди.
- Сейфгарды этапа 1 = лог-затухание + verify-before-score + относительная доска. repro-fail — позже.
- Архитектура = подход A (чистая функция + отдельный скрипт + статичный json), зеркалит Фазу 3.

## Осталось

- [ ] **Исполнить план** (6 задач) — главное.
- [ ] Финальный review + `finishing-a-development-branch` (PR в main, merge commit — как Фазы 1–3).
- [ ] Деплой проверится автоматически (pages.yml уже работает, новый шаг доски в том же build-job).
