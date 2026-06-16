# Фаза 5 — HF Space-витрина (read-only Gradio-доска + HF Datasets)

**Дата:** 2026-06-16
**Статус:** дизайн одобрен, переход к плану реализации
**Источник:** `docs/PROPOSAL-community-v2.md` §5; handoff `.claude/handoffs/phase5-hf-space.md`

## Цель

Построить витрину поверх артефактов Фаз 3–4 (`site/leaderboard.json`, `site/data.json`):
доска лидеров + табличный каталог рецептов с фильтрами, запускаемые одним `app.py`
и локально (`python app.py`), и на Hugging Face Space без переписывания. Плюс отдельный
CLI для выгрузки результатов как HF Dataset.

## Решения брейнсторма (2026-06-16)

| Развилка | Решение |
|---|---|
| Объём MVP | Read-only Gradio-доска **+ HF Datasets**-выгрузка (2 этапа) |
| HF-токен | Пользователь даст по ходу → datasets проверяем end-to-end; секрет **только через ENV**, не коммитить |
| Источник данных | Читать **готовые** `leaderboard.json` + `data.json` (единый source of truth с сайтом) |
| Размещение JSON | Локальный файл → URL-fallback (Pages); путь/URL через ENV; сеть в retry (HAPP рвёт TLS) |
| Объём UX | Доска лидеров + табличный каталог с фильтрами (type/maxcost/minacc/sort) + экспорт. **Без графиков** (Pareto/heatmap остаются на сайте) |
| Демо-данные | Отдельные фикстуры в `examples/` **вне** `submissions/` (seed в submissions/ ломает regrade-чек Фазы 2) |
| Структура кода | Монолитный `app.py` + пакет `webui/` + отдельный CLI `scripts/publish_datasets.py` (вариант A) |
| Выгрузка datasets | results dataset = `leaderboard.json` + `data.json`; манифесты `submissions/` — позже, когда появятся реальные сабмишны |

## Архитектура

Два независимых артефакта, оба следуют проектному паттерну «чистое ядро + I/O + CLI».

### 1. Витрина — `app.py` (корень репо) + пакет `webui/`

```
app.py                  # тонкий вход: сборка Gradio Blocks, проводка событий, demo.launch()
                        #              HF Space берёт его из корня (нативно)
webui/
  __init__.py
  data_loader.py        # load_leaderboard(), load_catalog() — локальный файл → URL-fallback (retry), чистые
  transform.py          # filter_catalog(rows, type, maxcost, minacc, sort), to_leaderboard_df(), to_catalog_df()
  export.py             # rows_to_csv_bytes(), rows_to_json_bytes() — для DownloadButton
```

- `app.py` — **только** сборка UI и проводка. Никакой бизнес-логики: вычисления в `webui/`,
  тестируются без поднятия Gradio.
- `data_loader.py` решает грабли «локально vs HF»: путь/URL из ENV
  (`FUSIONBENCH_DATA_DIR`, `FUSIONBENCH_DATA_URL`). Сначала локальный файл; при отсутствии —
  fetch с Pages-URL (через `httpx`, retry с бэкоффом); если ничего — пустая структура → empty-state.

### 2. Выгрузка — `scripts/publish_datasets.py` (CLI)

```
scripts/publish_datasets.py
  collect_dataset_files(...)              # чистое: какие файлы / в какой layout публикуем
  publish(api, repo_id, files, dry_run)   # I/O: create_repo(exist_ok=True) + upload_folder
  main()                                  # argparse: --repo, --source, --dry-run; токен из HF_TOKEN ENV
```

- Токен — только из ENV (`HF_TOKEN`), никогда не аргумент и не коммит.
- `--dry-run` печатает план без сети — тестируется без токена; реальный push — когда есть токен.

## Поток данных

### Витрина (runtime)

```
demo.launch() → on load:
  load_leaderboard():
    1. ENV FUSIONBENCH_DATA_DIR/leaderboard.json (локальный файл)
    2. fallback: FUSIONBENCH_DATA_URL + /leaderboard.json (fetch + retry)
    3. ничего → {"contributors": []} → empty-state
  load_catalog(): тот же каскад → {"cells": []} при отсутствии

  Доска: to_leaderboard_df() → Dataframe (#, user, points, verified, cells), грузится один раз
  Каталог: сырые cells → gr.State (один раз);
           любой фильтр (type dropdown / maxcost,minacc слайдеры / sort dropdown)
           → filter_catalog(state, ...) → to_catalog_df() → Dataframe
           слайдеры min/max берутся из данных при загрузке
  Экспорт: DownloadButton(csv) / DownloadButton(json) отдают ТЕКУЩИЙ отфильтрованный срез
```

Колонки доски — как на сайте: `#`, `user`, `points`, `verified`, `cells`.
Относительную «полоску» сайта в табличном MVP не воспроизводим (это JS-рендер); points — числом.

### Выгрузка (offline CLI, не в runtime витрины)

```
publish_datasets.py --repo <user>/fusionbench-results --dry-run
  collect_dataset_files() → [(local_path, path_in_repo), ...]   # leaderboard.json, data.json
  publish(dry_run=True)   → печатает план, сеть не трогает
  publish(dry_run=False)  → create_repo(exist_ok=True) + upload_folder   # нужен HF_TOKEN
```

results dataset = `leaderboard.json` + `data.json`. Манифесты `submissions/*/*/manifest.json` —
заложить layout, но публиковать позже (сейчас submissions/ пуст).

## Обработка ошибок

**Витрина деградирует мягко, CLI-выгрузка падает громко** — разные контракты под разные потоки.

### Загрузка данных (`data_loader.py`)
- Локального файла нет → URL-fallback. URL недоступен/таймаут → пустая структура → честный
  empty-state («Пока нет верифицированных вкладов» / «Каталог пуст»), не трейсбек.
- Сетевой fetch обёрнут в retry (HAPP рвёт TLS): N попыток с бэкоффом, затем empty-state.
  `curl`/`sleep` не используем — только Python-клиент (`httpx`).
- Битый/неполный JSON (нет ключа) → ловим, лог в stderr, трактуем как пустой, UI не роняем
  (как генераторы Фаз 3–4: malformed → skip, не assert).
- Пустой каталог → слайдеры получают безопасные дефолты (maxcost=1, minacc=0), таблица пустая.

### Фильтрация (`transform.py`)
- `complementarity = null` допустим в data.json → сортировка кладёт null в конец детерминированно.
- Невалидные значения слайдеров клампятся в диапазон.

### Выгрузка (`publish_datasets.py`)
- `HF_TOKEN` не задан и не `--dry-run` → понятная ошибка + ненулевой exit (`exit`, **не** `assert`:
  assert снимается `python -O`, как в regrade-правиле проекта), сеть не трогаем.
- Файл-источник отсутствует → понятная ошибка «сначала сгенерируйте артефакты», ненулевой exit.
- Сетевой сбой при push → retry вокруг `upload_folder`; при исчерпании — ненулевой exit с диагностикой.

## Тестирование

Паттерн проекта (`test_score_contributions.py`, `test_build_data.py`): юнит на чистые функции
+ герметичный E2E, всё в `tmp_path`/синтетике. Интерпретатор: `.venv/bin/python -m pytest -q`.
Baseline: **91 passed, 1 skipped, 1 xfailed** — новые тесты добавляются, старые остаются зелёными.

- **`tests/test_webui_data_loader.py`** (без Gradio): чтение локального файла из tmp;
  URL-fallback при отсутствии файла (URL замокан, не реальная сеть); оба источника недоступны
  → пустая структура без исключения; битый JSON → пустая структура + stderr; retry считает попытки (мок).
- **`tests/test_webui_transform.py`** (чистые функции): `filter_catalog` по каждому фильтру и
  комбинации; все 4 режима sort + детерминизм + null-complementarity в конце; `to_*_df` колонки/порядок;
  пустой вход → пустой DataFrame + дефолты слайдеров.
- **`tests/test_webui_export.py`**: csv/json на отфильтрованном срезе — корректный заголовок CSV,
  валидный JSON, round-trip.
- **`tests/test_publish_datasets.py`**: `collect_dataset_files` layout на синтетике в tmp; `--dry-run`
  не трогает сеть/HfApi (мок, ассерт что upload не звался); нет HF_TOKEN и не dry-run → ненулевой exit;
  источник отсутствует → ненулевой exit; E2E `main()` с monkeypatch argv.

**Демо-фикстуры:** папка `examples/` (вне `submissions/`) — мини `leaderboard.json` + `data.json`
с парой строк. Для локального запуска `app.py` (скриншоты/ручная проверка) и как источник в тестах.
Реальную сеть в тестах не дёргаем (URL всегда мок).

**Ручная верификация витрины:** Playwright MCP (не curl — недоступен в sandbox-bash): поднять
`app.py` локально, проверить рендер доски и каталога, работу фильтров, скачивание экспорта.

## Деплой и зависимости

- **`pyproject.toml`:** новая опц-группа `space` (`gradio`, `huggingface_hub`; `httpx` уже есть —
  переиспользуем). Установка `pip install -e ".[space]"`. Версии с осознанной нижней границей.
- **HF Space** (готовим, не деплоим): ждёт `app.py` + `requirements.txt` в корне Space.
  `app.py` уже в корне. `requirements.txt` — отдельный артефакт (Space не читает опц-группы pyproject),
  те же пины, что в группе `space`. `README.md` Space с YAML-хедером (`sdk: gradio`, `app_file: app.py`) —
  заготовка в репо. Реальный `push_to_hub` / деплой — **только по запросу и с токеном** (outward-facing).

## Этапность реализации

1. **Этап 1 — read-only витрина:** `app.py` + `webui/` + тесты + `examples/`-фикстуры + ручная
   верификация Playwright. Самодостаточно, локально-запускаемо, верифицируемо без токена.
2. **Этап 2 — выгрузка datasets:** `scripts/publish_datasets.py` + тесты (dry-run). Реальный push
   end-to-end — когда пользователь даст токен.

## Границы фазы (что НЕ делаем)

- Не деплоим на HF без запроса; не пушим / не открываем PR без запроса.
- Не воспроизводим графики (Pareto/heatmap), deep-links, относительную полоску — остаются на сайте.
- Не трогаем хвост Фазы 4 (Issue-форма/бот, тиры, бейджи, веса) — отдельный трек.
- Приватный evaluator-Space (уровень 3 proposal) — вне фазы.

## Грабли проекта (учтены в дизайне)

- Интерпретатор — `.venv/bin/python` (НЕ `python`).
- НЕ класть seed в `submissions/` — ломает regrade-чек Фазы 2 (демо в `examples/`).
- gitignore `site/`: `site/*` + `!site/app.js` + `!site/leaderboard.js`; `*.json`/`*.html` — build output.
- `--now`/даты — снаружи (детерминизм). К Gradio применяется так же: `now`/время не генерим внутри.
- Сеть (gh/git/fetch) — в retry (HAPP рвёт TLS). curl/sleep могут быть недоступны в sandbox-bash.
- Проверка целостности — через `exit`, не `assert` (снимается `python -O`).
- Ветка `phase5-hf-space` от main. Коммиты на русском, conventional, `git add` по файлам.
  Co-Authored-By: `Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
