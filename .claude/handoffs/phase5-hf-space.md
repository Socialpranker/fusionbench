# phase5-hf-space

**Дата:** 2026-06-16 | **Статус:** РЕАЛИЗОВАНА (оба этапа) на ветке `phase5-hf-space`, НЕ смержена/не задеплоена
**Цель:** Фаза 5 FusionBench — HF Space-витрина: read-only Gradio-доска + каталог + CLI выгрузки results на HF Datasets.

## Что сделано

Брейнсторм → спек → план → subagent-driven исполнение (13 задач, TDD, два ревью на задачу).

- **Спек:** `docs/superpowers/specs/2026-06-16-phase5-hf-space-design.md`
- **План:** `docs/superpowers/plans/2026-06-16-phase5-hf-space.md`

**Этап 1 — витрина (Task 1-8):**
- `app.py` (корень) — Gradio Blocks, вкладки Leaderboard + Catalog (фильтры type/maxcost/minacc/sort, экспорт CSV/JSON), empty-state. gradio 6 → `gr.Dataframe(type="array")`.
- `webui/` — `data_loader.py` (локальный файл `FUSIONBENCH_DATA_DIR` → URL-fallback `FUSIONBENCH_DATA_URL` с retry), `transform.py` (filter_catalog/to_*_df/slider_bounds/project_catalog_rows), `export.py` (CSV/JSON bytes). Чистые, тестируются без Gradio.
- `examples/leaderboard.json` + `examples/data.json` — демо-фикстуры (вне submissions/).
- Верифицировано вживую через Playwright: доска (2 contributor), фильтр type=code → 2 строки, 0 ошибок консоли.

**Этап 2 — выгрузка (Task 9-12):**
- `scripts/publish_datasets.py` — collect_dataset_files → publish (dry-run / create_repo+upload_file с retry) → main (argparse, токен-гейт HF_TOKEN ENV, raise SystemExit). results dataset = leaderboard.json + data.json.
- `requirements.txt` + `README_HF_SPACE.md` (sdk:gradio, app_file:app.py) — заготовка Space.
- Опц-группа `space` в `pyproject.toml`.

**Тесты:** baseline 91 → **121 passed, 1 skipped, 1 xfailed** (+30). `.venv/bin/python -m pytest -q`.

## Локальный запуск

```bash
pip install -e ".[space]"            # gradio + huggingface_hub
FUSIONBENCH_DATA_DIR=examples .venv/bin/python app.py   # витрина на демо-фикстурах
.venv/bin/python scripts/publish_datasets.py --repo demo/fb-results --source examples --dry-run
```

## Открытые хвосты (по запросу)

- **Финиш ветки:** merge в main / PR — НЕ сделано (по запросу). `superpowers:finishing-a-development-branch`.
- **Реальная HF Datasets-выгрузка** (`publish_datasets.py` без `--dry-run`) — нужен `HF_TOKEN` в ENV + аккаунт. Деплой Space — outward-facing, по запросу. Секрет только через ENV, не коммитить.
- **Манифесты submissions/ в dataset** — отложено (submissions/ сейчас пуст), layout заложен.
- **Хвост Фазы 4** (Issue Form+бот, тиры, бейджи, веса) — отдельный трек, НЕ Фаза 5.

## Что НЕ делать без запроса
- Не пушить / не открывать PR / не мержить.
- Не деплоить на HF, не делать реальный push датасета (нет токена; outward-facing).
