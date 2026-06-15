# FusionBench — Фаза 1: грейдинг-ядро + реестр типов задач

*14 июня 2026 · design-док под реализацию. Родительская спека: [PROPOSAL-community-v2.md](../../PROPOSAL-community-v2.md) §1, §5.*

## Цель и критерии приёмки (из §5)

Заложить «стержень» v2: **тип задачи = `(Loader, Grader)`**, версионируемый грейдинг и сохранение сырых выводов.

Приёмка Фазы 1:
- `python scripts/run_v0.py --suite ruler --mock` — зелёный, пишет `outputs.jsonl`
- `python scripts/run_v0.py --suite ifbench --mock` — зелёный, пишет `outputs.jsonl`
- Юнит-тесты на каждый грейдер проходят
- Появились пакеты `grading/` (base + ExactMatch, Numeric, Synthetic, Constraint) и `tasks/registry.py`

**Граница Фазы 1 (решено с Иваном):** только `--mock`. Лоадеры реализуют интерфейс и отдают синтетику/фикстуры; реальная загрузка через HuggingFace `datasets` — отдельная фаза, зависимость `datasets` сейчас НЕ добавляем.

## Что уже есть (переиспользуем, не дублируем)

| Существующее | Файл | Роль в Фазе 1 |
|---|---|---|
| `is_correct(answer, gold, aliases)` | `scoring.py` | ядро `ExactMatchGrader` (обёртка 1:1) |
| `ArmResult` (`panel_answers`, `judge`, `correct`, `usage`, `cost_usd`) | `config.py` | источник сырья для `outputs.jsonl` |
| `CatalogRow` + `write_rows` (append-JSONL) | `catalog.py` | образец для писателя `outputs.jsonl` |
| `load_tasks(suite, limit, mock)` + `LOADERS` | `tasks/loaders.py` | точка интеграции реестра |
| Задача-dict `{id, type, question, gold, aliases?}` | везде | адаптируется в `Example` |

## Архитектура Фазы 1

### 1. `grading/` — версионируемый грейдинг

Новый пакет `src/fusionbench/grading/`.

**`base.py`** — контракт:
```python
@dataclass(frozen=True)
class Verdict:
    passed: bool
    score: float          # 0..1
    detail: str = ""

class Grader(Protocol):
    name: str             # версия: "ExactMatch@1", "Numeric@1", ...
    def score(self, prediction: str, reference: Any, metadata: dict) -> Verdict: ...
```

Четыре грейдера (каждый — свой файл, одна ответственность):
- **`exact.py` · `ExactMatchGrader`** (`name="ExactMatch@1"`) — обёртка над `scoring.is_correct`. `reference` = gold-строка; `metadata["aliases"]` → aliases. `score = 1.0/0.0`.
- **`numeric.py` · `NumericGrader`** (`name="Numeric@1"`) — извлекает «boxed»/последнее число из prediction, сравнивает с `reference`. SymPy-эквивалентность если SymPy доступен (мягкий импорт), иначе численный fallback с tolerance. SymPy в зависимости НЕ тащим — `try/except ImportError`, без него работает численный путь.
- **`synthetic.py` · `SyntheticGrader`** (`name="Synthetic@1"`) — для RULER: `reference` = точная строка-эталон (needle), строгий нормализованный матч (синтетика → детерминирована).
- **`constraint.py` · `ConstraintGrader`** (`name="Constraint@1"`) — для IFBench. **Отличается от прочих:** не сравнивает с эталонным ответом, а проверяет prediction списком ограничений. `reference` = `list[Constraint]`, где `Constraint` — вызываемое `(str) -> bool` (или dataclass с `.check(prediction)`). `score` = доля выполненных, `passed` = все выполнены.

### 2. `tasks/` — Loader Protocol + реестр

**`tasks/base.py`** — контракт:
```python
@dataclass
class Example:
    id: str
    prompt: str
    reference: Any              # форма зависит от грейдера (str | list[Constraint])
    type: str
    metadata: dict = field(default_factory=dict)   # aliases и т.п.

class Loader(Protocol):
    def load(self, limit: int, split: str = "test") -> list[Example]: ...
```

**`tasks/registry.py`**:
```python
@dataclass(frozen=True)
class TaskSpec:
    type: str
    loader: Loader
    grader: Grader
    license: str
    contamination_policy: str   # "synthetic" | "time-windowed" | "static-risk"

REGISTRY: dict[str, TaskSpec] = {
    "multihop_qa":  TaskSpec("multihop_qa", FramesLoader(), ExactMatchGrader(), "Apache-2.0", "static-risk"),
    "long_context": TaskSpec("long_context", RulerLoader(),  SyntheticGrader(),  "Apache-2.0", "synthetic"),
    "instruction":  TaskSpec("instruction",  IFBenchLoader(), ConstraintGrader(), "Apache-2.0", "static-risk"),
}
```
Ключ реестра = имя suite на CLI? **Нет** — суиты `ruler`/`ifbench` маппятся на типы `long_context`/`instruction`. Реестр индексируется по **имени suite** (`"ruler"`, `"ifbench"`, `"frames"`), а `type` хранится внутри `TaskSpec` (он нужен в `outputs.jsonl` и группировке каталога). Это убирает двусмысленность «suite vs type».

**Новые лоадеры (mock-режим Фазы 1):**
- `tasks/ruler.py · RulerLoader` — генерирует синтетические needle-in-haystack примеры (RULER синтетичен по природе; mock = просто меньше/детерминированно). `reference` = needle-строка.
- `tasks/ifbench.py · IFBenchLoader` — фикстура из нескольких инструкций с проверяемыми ограничениями (например «ответь ровно 3 предложениями», «включи слово X»). `reference` = `list[Constraint]`.
- `FramesLoader` — адаптер над существующим `load_frames` (live тянет HF; под `--mock` отдаёт синтетику, не импортируя `datasets`).

### 3. `outputs.jsonl` — сохранение сырья

**Решение по `RunRecord`:** не вводим тяжёлый новый dataclass. Пишем `outputs.jsonl` из уже существующего `ArmResult` + контекста задачи. Новый файл `src/fusionbench/runs.py`:
```python
def output_record(run_id, example: Example, recipe: str, res: ArmResult, verdict: Verdict, grader_name: str) -> dict
def write_outputs(path, records: list[dict]) -> None   # append-JSONL, как write_rows
```
Поля записи (по §1.1): `run_id, task_id, type, recipe, prediction, panel, judge, claimed_correct, prompt_tokens, completion_tokens, cost_usd, grader, gold_id`.
- `prediction` ← `res.answer`; `panel` ← `res.panel_answers`; `claimed_correct` ← `verdict.passed`; `grader` ← `grader_name` (версия); `gold_id` ← `example.id`.

### 4. Интеграция в `run_v0.py`

Точечно, минимально:
- Резолв suite → `TaskSpec` из `REGISTRY` (с fallback на старый путь `load_tasks` для произвольных `data/<name>.jsonl`, чтобы не сломать существующие суиты).
- Скоринг идёт через `task_spec.grader.score(...)` вместо прямого `is_correct` (для `frames`/`multihop_qa` поведение идентично — это та же логика под обёрткой).
- После прогона по задаче — собрать `output_record` и в конце `write_outputs(run_id outputs.jsonl)`.
- `catalog.jsonl` продолжает писаться как раньше (агрегаты) — не трогаем формат.

## Изоляция и тестируемость

Каждый грейдер — отдельный файл, одна ответственность, тестируется без сети/LLM (чистые функции на строках). Лоадеры под `--mock` детерминированы. `outputs.jsonl`-писатель тестируется на фикстурном `ArmResult`.

## TDD-план (red→green по юнитам)

1. `tests/test_grading.py`: для каждого грейдера — passed/failed/partial кейсы (ExactMatch: alias/substring/numeric; Numeric: SymPy-экв и fallback; Synthetic: строгий матч; Constraint: доля ограничений).
2. `tests/test_registry.py`: `REGISTRY` резолвится, у каждого `TaskSpec` валидные loader/grader, `name` грейдера версионирован.
3. `tests/test_outputs.py`: `output_record` даёт все поля §1.1; `write_outputs` пишет валидный JSONL (append).
4. Интеграционно: `run_v0.py --suite ruler --mock` и `--suite ifbench --mock` отрабатывают и создают `outputs.jsonl` (smoke-проверка в тесте или вручную в верификации).

## Явные отступления от родительской спеки (и почему)

| Спека | Решение Фазы 1 | Причина |
|---|---|---|
| `RunRecord` dataclass | переиспользуем `ArmResult` + `output_record()` | сырьё уже в `ArmResult`; меньше дублирования |
| Реестр по `type` | реестр по **имени suite**, `type` внутри `TaskSpec` | CLI оперирует suite (`ruler`/`ifbench`), убирает двусмысленность |
| StateGrader, UnitTestGrader | вне Фазы 1 | §5 требует 4 грейдера; τ²/LiveCodeBench — позже |
| Live-загрузка датасетов | только mock | решение с Иваном; нет зависимости `datasets`/сети |
| held-out gold, regrade.py | вне Фазы 1 | это Фаза 2 (целостность загрузок) |

## Вне scope Фазы 1

Визуал/ECharts (§2), краудсорс-загрузки и ре-грейд (§3), геймификация (§4), реальная HF-загрузка, SymPy/datasets как hard-зависимости.
