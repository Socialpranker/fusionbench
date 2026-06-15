# Фаза 2 — целостность (integrity): design

**Дата:** 2026-06-14
**Статус:** одобрен, готов к плану реализации
**Зависит от:** [Фаза 1 — грейдинг-ядро и реестр типов задач](2026-06-14-phase1-grading-core-design.md)

## Цель

Дать возможность **пересчитать заявленные метрики сабмишна** из сохранённых сырых
выводов против приватного эталона (gold), чтобы подложный `outputs.jsonl` с
завышенной accuracy **падал в CI**, а корректный — проходил. Плаузибилити-проверка
ловит нереальную (заниженную) стоимость.

Это закрывает дыру доверия v0: без ре-грейда заявленные числа в каталоге ничем не
подкреплены — сабмиттер может написать любую accuracy.

## Ключевой инвариант целостности

Ре-грейд берёт `prediction` **из сабмишна**, но `reference` — **исключительно из
приватного gold**. Сабмиттер не контролирует эталон, поэтому не может подделать
вердикт: он лишь записывает `prediction`, который пересчитывается честно тем же
грейдером, что и при прогоне. Скоринг совпадает бит-в-бит, потому что ре-грейд
вызывает `REGISTRY[suite].grader.score(...)` — ту же реализацию.

**Где ловится подлог:** завысил `claimed.accuracy` в манифесте → пересчёт из gold
даёт реальное число → `assert` падает → CI красный.

## Поток данных

```
submissions/<user>/<run_id>/
   ├── manifest.json   ← заявлено: {suite, claimed.accuracy, claimed.cost_usd, n, ...}
   └── outputs.jsonl   ← сырьё: строка на (task × recipe), с gold_id, prediction, токенами
                                │
   gold/<suite>.jsonl.enc ──decrypt_gold.py(GOLD_DECRYPT_KEY)──▶ gold/<suite>.jsonl
                                │                                      │
                                ▼                                      ▼
                          validate_manifest.py            regrade.py:
                          (схема + плаузибилити            gold[id] → REGISTRY[suite].grader
                           токенов/цены → soft warn)        .score(prediction, reference, meta)
                                                            пересчитать acc, cost
                                                                │
                                                  if |acc − claimed.accuracy| > 0.01 → exit 1  (HARD)
                                                  cost расхождение/нереальность → WARN
```

**Связка gold_id ↔ gold:** в Фазе 1 `output_record` уже пишет `gold_id = example.id`,
а gold-файл ключуется по тому же `id`. Доп. правок Фазы 1 для линковки не требуется.

## Решения (зафиксированы при брейнсторме)

| Развилка | Решение | Обоснование |
|---|---|---|
| Хранение gold | Зашифрованный файл в репо (`gold/<suite>.jsonl.enc` + `GOLD_DECRYPT_KEY`) | Один секрет, без второго репозитория; локально мейнтейнер шифрует сам |
| Шифрование | Fernet из `cryptography` | Аутентифицированное (AES-128-CBC + HMAC), чистый Python, кросс-платформенно |
| Проверка accuracy | HARD fail при расхождении >1% | Ядро целостности |
| Проверка cost | Мягкий флаг (WARN, exit 0) | Цены моделей дрейфуют; жёсткий фейл даст ложные срабатывания на честных сабмишнах |
| Форма gold | Дамп загрузчика: `{id, reference, metadata, type}` | Ре-грейд вызывает тот же `grader.score` бит-в-бит |
| ifbench-констрейнты | Реестр предикатов `{kind, params}` + фабрики | `Constraint.predicate` — лямбда, в JSON не сериализуется; восстанавливается через фабрику |
| Данные приёмки | Фикстура из mock-прогона | Детерминированно, без сети/секретов |
| Объём фазы | Ядро + CI; `fusionbench submit` CLI — следующим шагом | submit-CLI не блокирует acceptance-критерии |

## Форматы файлов

### `submissions/<github_user>/<run_id>/manifest.json`

```json
{
  "schema_version": 1,
  "run_id": "ruler-20260614-abc123",
  "submitted_by": "socialpranker",
  "suite": "ruler",
  "grader": "Synthetic@1",
  "client_commit": "a1b2c3d",
  "claimed": {
    "recipe": "fusion-strong",
    "accuracy": 0.71,
    "cost_usd": 0.0044,
    "n": 150
  }
}
```

- `suite` — ключ в `REGISTRY` (`frames`/`ruler`/`ifbench`), **не** `suite_type` (такого поля нет).
- `grader` дублирует `REGISTRY[suite].grader.name` для явной сверки версии грейдера.
- Поля `models`/`seeds`/`prompt_template_hash`/`token_totals` из черновика **убраны** (YAGNI):
  для ре-грейда не нужны, воспроизводимость в Фазе 2 не проверяется.

### `gold/<suite>.jsonl` (расшифрованный) — строка на пример

```jsonc
// frames / ruler (строковый reference):
{"id": "ruler-0001", "type": "long_context", "reference": "NEEDLE-AAA", "metadata": {}}

// ifbench (реестр предикатов вместо list[Constraint]):
{"id": "ifbench-0001", "type": "instruction", "metadata": {},
 "reference": [{"kind": "exactly_words", "params": {"n": 3}},
               {"kind": "contains", "params": {"word": "moon"}},
               {"kind": "all_caps", "params": {}}]}
```

### Контракт сериализации reference

| suite | reference в gold | как восстанавливается |
|---|---|---|
| frames | `str` | как есть |
| ruler | `str` | как есть |
| ifbench | `list[{kind, params}]` | `CONSTRAINT_FACTORIES[kind](**params)` → `Constraint` |

`metadata` (включая `aliases` для frames) — обычный JSON, уже dict-сериализуем.

### `gold/<suite>.jsonl.enc`

Fernet-токен от UTF-8 байт расшифрованного `.jsonl`. Один файл = один зашифрованный
blob (не построчно). `schema_version` живёт только в манифесте; gold привязан к версии
грейдера через `grader.name`.

## Компоненты и границы модулей

### Изменения в Фазе-1 (для сериализуемости ifbench)

1. **`src/fusionbench/grading/constraint.py`** — реестр фабрик
   `CONSTRAINT_FACTORIES: dict[str, Callable]` + `constraint_to_dict(c) → {kind, params}`
   / `constraint_from_dict(d) → Constraint`. Единственное место, знающее, как
   (де)сериализовать констрейнт.
2. **`src/fusionbench/tasks/ifbench.py`** — констрейнты строятся через
   зарегистрированные фабрики, параметры выносятся в явный `params`-словарь
   (`_contains("moon")` → `kind=contains, params={word: "moon"}`), чтобы round-trip
   был тождественным.

### Новый модуль сериализации gold (сердце Фазы 2)

3. **`src/fusionbench/gold.py`** — `example_to_gold(ex) → dict` и
   `gold_to_reference(suite, row) → (reference, metadata)`. Единственный модуль,
   переводящий между `Example`/`Constraint` и JSON-строкой gold. `regrade.py` зависит
   от него, но не знает внутренностей.

### Утилита крипто

4. **`src/fusionbench/crypto.py`** — тонкая обёртка Fernet: `encrypt_bytes` /
   `decrypt_bytes`. Чтобы скрипты шифрования не дублировали логику и тестировались
   изолированно.

### Скрипты (тонкие: парсинг аргументов + оркестрация)

5. **`scripts/encrypt_gold.py`** — локальный инструмент мейнтейнера:
   `gold/<suite>.jsonl` → `.enc`. Не в CI, запускается руками при обновлении эталона.
6. **`scripts/decrypt_gold.py`** — CI: `.enc` + `GOLD_DECRYPT_KEY` (env) → `.jsonl`.
   Падает явной ошибкой, если ключа нет.
7. **`scripts/validate_manifest.py`** — схема манифеста + плаузибилити (cost/токены).
   exit 0 даже при cost-аномалии (WARN); ненулевой код только при структурной
   невалидности.
8. **`scripts/regrade.py`** — ядро: манифест + outputs + gold, пересчёт через
   `REGISTRY[suite].grader`, явный `sys.exit(1)` по accuracy (HARD), WARN по cost.
   **Не `assert`** — `assert` отключается при `python -O`, а проверку целостности
   нельзя дать выключить флагом.

### CI

9. **`.github/workflows/submit.yml`** — отдельный workflow, триггер
   `pull_request: paths: ["submissions/**"]`. Шаги: install → decrypt → validate →
   regrade. Required check. Не конфликтует с `ci.yml` (тот гоняет тест-матрицу на
   любом push/PR). `GOLD_DECRYPT_KEY` доступен только в этом workflow.

### Тесты и фикстуры

10. **`tests/test_gold.py`** — round-trip: `Example → gold dict → reference`
    тождественен для всех трёх suite. Для ifbench — восстановленный предикат даёт
    **тот же вердикт** на тестовом prediction, что и оригинал (доказывает, что реестр
    не теряет логику).
11. **`tests/test_regrade.py`** — приёмка (см. ниже).
12. **`tests/test_crypto.py`** — encrypt → decrypt round-trip.
13. **`tests/fixtures/regrade/`** — gold + honest/tampered outputs из mock-прогона.

**Принцип границ:** скрипты тонкие, вся логика — в тестируемых модулях
`gold.py`/`crypto.py`/`grading`. CI вызывает скрипты, скрипты зовут модули.

## Обработка ошибок

| Ситуация | Поведение | Почему |
|---|---|---|
| accuracy расходится >1% | **HARD fail** | ядро целостности — подлог |
| `gold_id` из outputs нет в gold | **HARD fail** | ссылка на несуществующий пример |
| манифест не по схеме / нет обязательного поля | **HARD fail** | структурно невалиден |
| `grader` в манифесте ≠ `REGISTRY[suite].grader.name` | **HARD fail** | пересчёт несравним |
| `GOLD_DECRYPT_KEY` отсутствует/неверный | **HARD fail** с явным сообщением | без gold ре-грейд невозможен |
| `n` в манифесте ≠ числу уникальных задач | **HARD fail** | заявленная выборка не сходится с сырьём |
| outputs содержит несколько recipe | фильтр по `claimed.recipe` | сравниваем заявленный рецепт, не смесь |
| cost расходится / нереальная цена | **WARN** (exit 0) | цены дрейфуют, жёсткий фейл — ложные срабатывания |

**Не глотать ошибку:** при любом HARD-условии печатается *какой именно* пример/поле
не сошлось и реальное vs заявленное число — не просто «mismatch». Делает красный CI
диагностируемым.

**Допуски — явные константы в начале `regrade.py`:**
`ACCURACY_TOL = 0.01`, `COST_WARN_TOL = 0.15` (15% на cost-плаузибилити).

## Тестирование и приёмка

**Стратегия:** TDD — юнит-тест до реализации каждого модуля.

**Фикстуры** (`tests/fixtures/regrade/`) генерируются из
`run_v0.py --mock --suite ruler` (детерминированно), фиксируются в репо как статичные
файлы:
- `gold_ruler.jsonl` + `outputs_honest.jsonl` — accuracy совпадает → проходит
- `outputs_tampered.jsonl` / манифест с завышенной `claimed.accuracy` → падает

**Приёмочные утверждения (= критерии Фазы 2):**
1. подложный outputs с завышенной accuracy → `regrade.py` exit ≠ 0
2. корректный outputs → exit 0
3. заниженная/нереальная цена → WARN в выводе (exit 0)

**Round-trip ifbench** (`tests/test_gold.py`): `Example(ifbench) → gold dict →
from_dict → Constraint`, восстановленный предикат даёт тот же вердикт на тестовом
prediction.

**Команда верификации перед «готово»:** `pytest` (все зелёные) + локальный прогон
`scripts/regrade.py` на honest/tampered-фикстурах с проверкой кодов выхода +
`ruff check`.

## Справочные факты из кода (верифицированы)

- `output_record` (`src/fusionbench/runs.py:39`) пишет `gold_id = example.id`.
- `cost_usd` (`src/fusionbench/budget.py:17`):
  `prompt_tokens/1e6 * price_in + completion_tokens/1e6 * price_out`.
  Цены — `MODELS` в `src/fusionbench/presets.py` (per 1M токенов).
- Грейдеры: `ExactMatch@1` (reference `str` + `metadata.aliases`), `Synthetic@1`
  (reference `str`), `Constraint@1` (reference `list[Constraint]`).
- `Constraint` (`src/fusionbench/grading/constraint.py`): `dataclass(frozen=True)` с
  `describe_text: str` и `predicate: Callable[[str], bool]` — **лямбда, не
  JSON-сериализуема** (причина реестра предикатов).
- `cryptography` в зависимостях **нет** — добавляется в Фазе 2.

## Вне объёма Фазы 2 (следующие шаги)

- `fusionbench submit` CLI (локальная валидация + автогенерация PR через `gh`).
- Реальные (не mock) gold-эталоны для frames/ifbench из held-out источников.
- Проверка воспроизводимости (seeds, prompt_template_hash) — отдельная фаза.
