# Фаза 4 этап 1 — движок очков + доска лидеров: Design

**Дата:** 2026-06-15 · **Статус:** одобрен (брейнсторм) · **Ветка-основа:** main (Фазы 1–3 влиты)
**Источник требований:** `docs/PROPOSAL-community-v2.md` §4 (геймификация) + §5 (фазовый план).

## Цель

Первый этап Фазы 4 «краудсорс + доска лидеров»: начислять очки контрибьюторам за
**верифицированные** вклады-ячейки и показывать **относительную** доску лидеров на сайте.
Базируется на уже работающей инфраструктуре приёма сабмишнов (Фаза 2: PR → `submit.yml`
→ `regrade.py`). Чисто аддитивно — существующий submit/regrade-флоу не меняется.

## Объём

**В этапе 1:**
- `scripts/score_contributions.py` — движок очков (чистое ядро + I/O-обёртка) → `site/leaderboard.json`.
- Очки за cell-вклады с логарифмическим затуханием по повторам.
- Verify-before-score (только сабмишны, попавшие в main = прошедшие regrade).
- Отдельная страница `site/leaderboard.html` + `site/leaderboard.js` — относительная доска.
- Seed-фикстуры (mock-сабмишны) для демо доски.
- Интеграция в `pages.yml` (генерация при деплое).
- Юнит-тесты (pytest на чистое ядро; node — если в JS появятся чистые derive-функции).

**ВНЕ объёма этапа 1 (следующие этапы Фазы 4):**
- Issue Form + бот (`.github/ISSUE_TEMPLATE/result.yml` + Action) — альтернативный вход для не-кодеров.
- Тиры (Contributor/Verified/Maintainer/Core) и бейджи.
- Воспроизведения (reproduction-вклады), `repro_fail_rate` shadow-метрика.
- Веса за сьюты/адаптеры/багфиксы (§4.1) — этап 1 считает только cell-вклады.
- Рейт-лимит, бан рецидивистов, авто-`CITATION.cff`.
- (Фаза 5) HF Space-витрина.

## Решения брейнсторма

- **Объём этапа 1** = движок очков + доска (не бот-первым, не всё-сразу). PR+regrade уже работает.
- **Источник вкладов** = `submissions/<user>/<run_id>/manifest.json` (+ seed-фикстуры для демо).
- **Размещение доски** = отдельная страница `leaderboard.html` (не секция в index.html) — чистое
  разделение «каталог рецептов» vs «люди», не раздувает `app.js`.
- **Сейфгарды этапа 1** = лог-затухание + verify-before-score + относительная доска. repro-fail/
  воспроизведения — позже (нет данных).
- **Архитектура** = подход A: чистая функция очков + отдельный скрипт + статичный `leaderboard.json`.
  Зеркалит Фазу 3 (данные/логика/представление), TDD-friendly, изолированно. (Отвергнуто: встраивание
  в `build_catalog.py` — смешивает ответственности; клиентский расчёт — манифесты не публикуются на сайт.)

## Архитектура

Три изолированных юнита (данные / логика / представление):

```
submissions/<user>/<run_id>/manifest.json   (вход: верифицированные вклады)
        │
        ▼
scripts/score_contributions.py
   ├─ score_contributions(submissions) -> leaderboard_dict   ← ЧИСТОЕ ЯДРО (юнит-тесты)
   └─ I/O-обёртка: читает submissions/*/manifest.json, пишет site/leaderboard.json + leaderboard.html
        │
        ▼
site/leaderboard.json   (контракт данных)
        │
        ▼
site/leaderboard.html (генерится) + site/leaderboard.js (рукописный)   ← ПРЕДСТАВЛЕНИЕ
```

## Модель данных и логика очков

**Cell-ключ:** `(suite, recipe)` из `manifest.suite` + `manifest.claimed.recipe`. Строковое
представление для json/UI: `"<suite>×<recipe>"` (например `"frames×fusion-strong"`).

**Очки за сабмишн (этап 1 — только cell-вклады):**
```
WEIGHT_CELL = 20                       # proposal §4.1
points_for_submission = WEIGHT_CELL * (0.5 ** prior)
```
где `prior` = число сабмишнов ТОЙ ЖЕ cell, упорядоченных РАНЬШЕ текущего. Порядок —
детерминированный: сабмишны сортируются по `run_id` лексикографически (стабильно, не зависит
от файловой системы / git-времени). Первый сабмиттер cell получает 20, второй 10, третий 5, …
(лог-затухание → ~0). Один контрибьютор, повторно сабмитящий ту же cell, тоже попадает под затухание
(prior считается по cell глобально, не per-user).

**Verify-before-score:** учитываются ТОЛЬКО манифесты, физически лежащие в `submissions/` на main.
Это и есть верификация: попасть в main можно лишь через PR с зелёным `submit.yml` (regrade — required
check, блокирующий мерж). `score_contributions.py` **НЕ перезапускает** regrade и не читает gold.
(Источник истины «merged = passed» подтверждён: regrade.py пишет вердикт только в stdout/exit-code,
submit.yml не коммитит маркер обратно — гейт обеспечивается branch protection.)

**Скор контрибьютора:** `sum(points_for_submission)` по всем его сабмишнам.

**Контракт `leaderboard.json`** (поля заложены под будущие этапы, этап 1 заполняет только реальные):
```json
{
  "updated": "2026-06-15",
  "contributors": [
    {"user": "mira_k", "points": 35.0, "verified": 3,
     "cells": ["frames×fusion-strong", "ruler×best-single"]}
  ]
}
```
- `points` — округление до разумной точности (например 2 знака).
- `verified` — число засчитанных сабмишнов контрибьютора.
- `cells` — отсортированный уникальный список cell-ключей контрибьютора.
- Массив `contributors` отсортирован по `points` desc, тай-брейк по `user` asc (детерминизм).
- Поля `tier/badges/reproductions/repro_fail_rate` — НЕ в этапе 1.
- `updated` — дата генерации; передаётся в скрипт аргументом/`--now` (не `Date.now()` внутри, чтобы
  тесты были детерминированы), либо из окружения CI.

## Страница доски

`site/leaderboard.html` (генерится из шаблона в `score_contributions.py`) + `site/leaderboard.js`
(рукописный, трекается через gitignore-исключение, как `site/app.js`).

- **Таблица** контрибьюторов: колонки `rank`, `user`, `points`, `verified`, `cells`. Построение
  через `createElement`/`textContent` — **innerHTML запрещён** проектным PreToolUse-хуком (как в
  explorer Фазы 3).
- **Относительность** (анти-Goodhart §4.4 «ранги рядом, не глобальный абсолют»): у каждой строки —
  бар, нормированный к лидеру (`points / max_points`), чтобы не культивировать абсолютное число;
  опционально подсветка «соседей по рангу». Без гигантского абсолютного отрыва как главного сигнала.
- **Навигация**: шапка со ссылкой `← Catalog` (на `index.html`); обратная ссылка с каталога
  (`index.html` шапка) → `leaderboard.html`. Реализуется добавлением ссылки в шаблон `PAGE`
  каталога (`build_catalog.py`) и в шаблон доски.
- **Темы**: переиспользовать dark/light CSS (`prefers-color-scheme`) из Фазы 3 — общий блок стилей.
- **Пустое состояние**: `leaderboard.json` с пустым `contributors` → страница показывает
  «Пока нет верифицированных вкладов», не пустой/битый макет.
- **Загрузка данных**: `leaderboard.js` фетчит `leaderboard.json` (относительный путь, как
  `app.js` фетчит `data.json` — безопасно под Pages-subpath). Фолбэк при ошибке fetch/пустом json.

## Интеграция в CI / pipeline

- **`pages.yml`**: добавить шаг `python scripts/score_contributions.py` (после «Ensure catalog data»,
  рядом с `build_catalog.py`) → пишет `site/leaderboard.json` + `site/leaderboard.html`.
- Артефакт Pages уже грузит весь `site/` → доска деплоится автоматически.
- **Источник сабмишнов в CI**: реальные `submissions/` (сейчас пусто) + seed-фикстуры в репо.
  Пустой `submissions/` → валидный пустой `leaderboard.json`, скрипт НЕ падает.
- **gitignore**: `site/leaderboard.js` трекать через исключение (как `!site/app.js`);
  `leaderboard.html`/`leaderboard.json` — build output (не коммитятся), генерятся в CI.
  ВНИМАНИЕ на glob-ловушку [[run-v0-two-schemas-glob-trap]]: скрипт читает `submissions/**/manifest.json`,
  не широкий glob по разнросхемным файлам.

## Тесты и обработка ошибок

- **Юниты `tests/test_score_contributions.py`** (pytest) на чистое `score_contributions(submissions)`:
  - лог-затухание (разные юзеры): одна cell, 3 сабмишна от 3 юзеров (по run_id) → 20 / 10 / 5 разным людям;
  - лог-затухание (один юзер): одна cell ×3 от одного юзера → у него 20+10+5 = 35 (prior по cell глобально);
  - мульти-контрибьютор: корректная агрегация и сортировка (points desc, user asc);
  - детерминизм: тот же вход → тот же выход (сортировки стабильны);
  - пустой вход → `{"contributors": []}` (+ `updated`);
  - malformed-манифест (нет `submitted_by`/`suite`/`claimed.recipe`) → пропуск с warn, не падение.
- **Герметичность** [[test-build-data-hermetic-runs]]: тесты генерят временные `manifest.json` в
  `tmp_path`, НЕ зависят от реального `submissions/` (иначе CI/локаль разойдутся).
- **JS-юниты `tests/leaderboard_logic.test.mjs`** (node, опц.): если в `leaderboard.js` появятся
  чистые derive-функции (нормировка бара, вычисление рангов) — UMD-экспорт (`module.exports`) +
  node-тест, как Фаза 3 (`site_logic.test.mjs`).
- **Error handling**:
  - манифест без обязательных полей → пропустить, предупредить (stderr), продолжить;
  - пустой `submissions/` → валидный пустой `leaderboard.json`;
  - битый JSON в манифесте → пропустить с warn, не падать на всём прогоне.

## File Structure

- **Create** `scripts/score_contributions.py` — движок очков + генерация json/html.
- **Create** `site/leaderboard.js` — рукописный, трекается (gitignore-исключение).
- **Create** `tests/test_score_contributions.py` — pytest-юниты на чистое ядро.
- **Create** seed-фикстуры: несколько `submissions/<user>/<run_id>/manifest.json` (mock) для демо.
- **Modify** `scripts/build_catalog.py` — добавить ссылку на доску в шапку `PAGE` (навигация).
- **Modify** `.github/workflows/pages.yml` — шаг генерации доски.
- **Modify** `.gitignore` — исключение для `site/leaderboard.js`.
- **(опц.) Create** `tests/leaderboard_logic.test.mjs` — node-юниты, если будут чистые JS-функции.

## Verification (перед «готово»)

- `pytest -q` — все зелёные (новые тесты score_contributions + прежние; норма прошлых skip/xfail).
- (опц.) `node tests/leaderboard_logic.test.mjs` — passed.
- `score_contributions.py` на seed-фикстурах → валидный `leaderboard.json` с ожидаемыми очками (затухание).
- Локальная симуляция CI: пустой `submissions/` → пустой валидный `leaderboard.json`, без падения.
- Нет `innerHTML` в `leaderboard.js` (только `textContent`/`createElement`).
- Playwright: `leaderboard.html` рендерит таблицу из json; навигация catalog ↔ leaderboard; dark-тема;
  пустое состояние показывает сообщение.
- `pages.yml` локально-симулирован: генерит `leaderboard.json` + `leaderboard.html` рядом с `index.html`.

## Примечания

- Чисто аддитивно: submit/regrade-флоу Фазы 2 и каталог Фазы 3 не ломаются.
- Перед деплоем сайта Pages уже включён ([[pages-enable-before-push]]); деплой грузит весь `site/`.
- `updated`-дату передавать аргументом/из CI, НЕ генерить внутри (детерминизм тестов).
