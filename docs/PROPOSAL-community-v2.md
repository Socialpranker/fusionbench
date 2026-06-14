# FusionBench v2 — спецификация механик сообщества (для Claude Code)

*14 июня 2026 · имплементационная спека. Можно отдавать Claude Code пофазно.*

Это расширение research-предложения: те же 4 механики (типы задач, визуал, краудсорс-загрузки, геймификация), но с конкретными интерфейсами, схемами данных, примерами кода и CI. Рациональ и источники — в конце.

---

## 0. Как пользоваться (для Claude Code)

**Что уже есть в репозитории** (`src/fusionbench/`): `config.py` (dataclasses `ModelSpec/RecipeConfig/Usage/ArmResult`), `presets.py`, `client.py` (OpenRouter + Mock), `budget.py`, `solvers.py` (5 плеч), `judge.py` (bias-контроль), `scoring.py` (`is_correct`), `complementarity.py`, `catalog.py`, `search.py`; `scripts/run_v0.py`, `run_search.py`, `build_catalog.py`, `check_setup.py`; тесты; CI + Pages.

**Принцип:** сначала строим стержень (раздел 1), потом всё навешивается. Стержень = **верифицируемый `Grader` на тип задачи + сохранённые сырые выводы (`outputs.jsonl`) + ре-грейд на CI**.

**Неизменные правила (инварианты проекта):**
- грейдинг детерминированный, без LLM-судьи (это делает ре-грейд дешёвым и результат бесспорным);
- любое сравнение «fusion лучше» — при **равном бюджете токенов**;
- судья никогда не из семьи модели в панели;
- **сохраняем сырые выводы** каждого ран'а — без них нет ни ре-грейда, ни доверия.

---

## 1. Стержень: тип задачи = `(Loader, Grader)`

### 1.1 Расширяем запись результата: сохраняем сырьё

Сейчас раннер пишет только агрегаты (`CatalogRow`). Добавляем **пер-итемные** выводы — новый артефакт `runs/<run_id>/outputs.jsonl`, строка на (задача × рецепт):

```json
{"run_id":"2026-06-14T10-00Z_ab12","task_id":"frames-0007","type":"multihop_qa",
 "recipe":"fusion-strong","prediction":"1969","panel":{"anthropic/claude-fable-5":"1969",
 "openai/gpt-5.5":"1969","google/gemini-3-pro":"1968"},"judge":{"best_answer":"1969"},
 "claimed_correct":true,"prompt_tokens":812,"completion_tokens":143,"cost_usd":0.0041,
 "grader":"NumericGrader@1","gold_id":"frames-0007"}
```

`prediction` — финальный ответ рецепта; `panel` — сырьё панели (для аудита/комплементарности). Эталон (`gold`) сюда **не** пишем (см. 3.2). Добавь `RunRecord` dataclass в `config.py` и писатель `runs.py` (JSONL), по аналогии с `catalog.py`.

### 1.2 Интерфейс `Grader` + примеры (новый `grading/` пакет)

```python
# src/fusionbench/grading/base.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Any

@dataclass
class Verdict:
    passed: bool
    score: float          # 0..1; для бинарных = float(passed)
    detail: str = ""

class Grader(Protocol):
    name: str
    def score(self, prediction: str, reference: Any, metadata: dict) -> Verdict: ...
```

Реестр переиспользуемых грейдеров (каждый — отдельный файл `grading/<name>.py`):

```python
# grading/exact.py — наука (MC), факт. ответ, FRAMES
import re
def _norm(s): return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

class ExactMatchGrader:
    name = "ExactMatch@1"
    def score(self, prediction, reference, metadata):
        a = _norm(prediction)
        golds = [reference, *metadata.get("aliases", [])]
        ok = any(_norm(g) and (_norm(g) == a or _norm(g) in a) for g in golds)
        return Verdict(ok, float(ok))
```

```python
# grading/numeric.py — математика (boxed/числовой, SymPy-эквивалентность)
import re
class NumericGrader:
    name = "Numeric@1"
    def score(self, prediction, reference, metadata):
        try:
            from sympy import simplify, sympify
            pred = self._extract(prediction)
            ok = simplify(sympify(pred) - sympify(str(reference))) == 0
        except Exception:
            ok = self._nums(prediction) & self._nums(str(reference)) != set()
        return Verdict(bool(ok), float(bool(ok)))
    def _extract(self, s):
        m = re.findall(r"-?\d+(?:\.\d+)?", s.replace(",", "")); return m[-1] if m else s
    def _nums(self, s):
        return {round(float(x), 4) for x in re.findall(r"-?\d[\d,]*(?:\.\d+)?", s or "") for x in [x.replace(",", "")]}
```

```python
# grading/unittest_exec.py — код (LiveCodeBench / SWE-bench): запуск тестов в песочнице
import subprocess, tempfile, textwrap, os
class UnitTestGrader:
    name = "UnitTest@1"
    def score(self, prediction, reference, metadata):
        # reference = тесты; prediction = код. Запускаем в изоляции с таймаутом.
        code = _extract_code_block(prediction)
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "sol.py"), "w").write(code)
            open(os.path.join(d, "test.py"), "w").write(reference)
            try:
                r = subprocess.run(["python", "test.py"], cwd=d, capture_output=True,
                                   timeout=metadata.get("timeout", 15))
                ok = r.returncode == 0
            except subprocess.TimeoutExpired:
                ok = False
        return Verdict(ok, float(ok))
        # ВАЖНО: в CI запускать под ограниченным пользователем/контейнером (untrusted code).
```

Эскизы остальных (тот же контракт):
- `grading/constraint.py` — **IFBench/IFEval**: `reference`/`metadata` несёт список python-функций-проверок; `score` = доля выполненных ограничений.
- `grading/state.py` — **τ²-bench**: `reference` = эталонное конечное состояние БД/среды; `metadata["trajectory"]` пере-проигрывается, сравнивается финальное состояние (без LLM).
- `grading/synthetic.py` — **RULER**: ключ ответа задаётся шаблоном генерации (needle/aggregation) → точное совпадение.
- `grading/setmatch.py` — мультиответ: сравнение множеств без учёта порядка.

### 1.3 Интерфейс `Loader` + примеры

```python
# src/fusionbench/tasks/base.py
from dataclasses import dataclass, field
@dataclass
class Example:
    id: str
    prompt: str
    reference: object            # форма зависит от грейдера (строка/тесты/состояние)
    type: str
    metadata: dict = field(default_factory=dict)

class Loader(Protocol):
    def load(self, limit: int, split: str = "test") -> list[Example]: ...
```

```python
# tasks/ruler.py — длинный контекст, синтетика (contamination-proof)
class RulerLoader:
    def __init__(self, subtask="niah_single", ctx_len=16000): ...
    def load(self, limit, split="test"):
        # генерим синтетически: «иголки» в длинном тексте; reference = вставленный факт
        return [Example(id=f"ruler-{i}", prompt=text, reference=needle,
                        type="long_context", metadata={"ctx_len": self.ctx_len})
                for i, (text, needle) in enumerate(self._gen(limit))]
```

FRAMES-лоадер уже есть (`tasks/loaders.py`). Аналогично добавить `ifbench.py`, `tau2.py`, `livecodebench.py` (для последнего — `cutoff_date` фильтр против утечки).

### 1.4 Манифест регистрации (`tasks/registry.py`)

```python
from dataclasses import dataclass
@dataclass(frozen=True)
class TaskSpec:
    type: str
    loader: object
    grader: object
    license: str
    contamination_policy: str    # "synthetic" | "time-windowed" | "static-risk"

from .ruler import RulerLoader
from .ifbench import IFBenchLoader
from ..grading.synthetic import SyntheticGrader
from ..grading.constraint import ConstraintGrader
# ...
REGISTRY = {
  "multihop_qa":  TaskSpec("multihop_qa", FramesLoader(), ExactMatchGrader(), "Apache-2.0", "static-risk"),
  "long_context": TaskSpec("long_context", RulerLoader(), SyntheticGrader(), "Apache-2.0", "synthetic"),
  "instruction":  TaskSpec("instruction", IFBenchLoader(), ConstraintGrader(), "Apache-2.0", "static-risk"),
  "agentic":      TaskSpec("agentic", Tau2Loader(), StateGrader(), "MIT", "static-risk"),
  # code / math / science / factual ...
}
```

Раннер берёт грейдер из `REGISTRY[example.type].grader` вместо хардкода `is_correct`. `scoring.is_correct` остаётся как реализация внутри `ExactMatchGrader`.

### 1.5 Чек-лист «добавить тип задачи»
1. `tasks/<name>.py` — `Loader`.  2. грейдер из `grading/` (или новый).  3. строка в `REGISTRY`.  4. приватный held-out split (3.2).  5. `python scripts/run_v0.py --suite <name> --mock` зелёный.

Рекомендованные первые добавления (бесспорный грейдинг, без утечки): **RULER, IFBench, τ²-bench-Verified**. Избегать: HumanEval, GSM8K, HotpotQA, MMLU, base SWE-bench.

---

## 2. Визуал v2 — ECharts из `data.json`

### 2.1 Контракт данных `site/data.json` (эмитит `build_catalog.py`)

```json
{
  "generated": "2026-06-14",
  "suites": ["frames","ruler","ifbench"],
  "recipes": [
    {"name":"best-single","arm":"best_single"},
    {"name":"fusion-strong","arm":"fusion","panel":["...","..."],"judge":"..."}
  ],
  "cells": [
    {"type":"multihop_qa","recipe":"fusion-strong","accuracy":0.71,"cost_usd":0.0044,
     "latency_s":1.6,"worthiness_vs_self_moa":0.10,"complementarity":0.79,"recommended":true,"n":150}
  ],
  "complementarity": [{"a":"gemini-3-flash","b":"kimi-k2.6","type":"multihop_qa","value":0.81}]
}
```

### 2.2 Герой-Pareto (ECharts `option`, шаблон)

```js
const worthCost = 2.0, worthAcc = 0.72;     // порог «выгодной зоны»
option = {
  grid:{left:48,right:24,top:24,bottom:44},
  xAxis:{type:'log', name:'стоимость, × одиночной'},
  yAxis:{type:'value', name:'точность', axisLabel:{formatter:v=>Math.round(v*100)+'%'}},
  series:[
    { type:'scatter', symbolSize:16, data: cells.map(c=>({value:[c.cost_usd, c.accuracy], name:c.recipe})),
      markArea:{ itemStyle:{color:'rgba(21,128,61,0.08)'},
        data:[[{xAxis:0, yAxis:worthAcc},{xAxis:worthCost, yAxis:1}]] },     // worth-it квадрант
      label:{show:true, formatter:p=>p.name, position:'top'} },
    { type:'line', data: paretoFrontier(cells), lineStyle:{type:'dashed'}, symbol:'none' } // фронтир
  ],
  tooltip:{ formatter:p=>`${p.name}: ${p.value[0].toFixed(4)}$ · ${Math.round(p.value[1]*100)}%` }
};
```

### 2.3 Heatmap «тип × рецепт» (ECharts)

```js
option = {
  tooltip:{position:'top'},
  xAxis:{type:'category', data:recipes}, yAxis:{type:'category', data:taskTypes},
  visualMap:{min:-0.1, max:0.1, calculable:true,
             inRange:{color:['#b91c1c','#f1f5f9','#15803d']}},   // red→neutral→green
  series:[{ type:'heatmap',
    data: matrix.map(m=>[m.recipeIdx, m.typeIdx, m.worthiness_vs_best]),
    label:{show:true, formatter:p=>(p.value[2]>0?'+':'')+Math.round(p.value[2]*100)} }]
};
```

### 2.4 Файлы сайта + deep-links

```
site/index.html      — каркас + загрузка echarts (CDN) + fetch('data.json')
site/app.js          — строит 4 вида из data.json (hero, heatmap, complementarity, explorer)
site/data.json       — генерится build_catalog.py при каждом merge
```

Состояние вида — в URL-hash: `#type=multihop_qa&maxcost=0.005&minacc=0.7&sort=worthiness`. При загрузке парсим hash → фильтруем; при изменении фильтров — пишем hash (любой вид шарится копированием ссылки). Премиум-штрихи: dark/light с едиными цвето-токенами по `arm`; «скачать CSV/JSON» и ссылка на методологию у каждого графика; анимация ≤200мс.

Переписать `build_catalog.py`: вместо инлайна HTML — эмитить `data.json` + статический `index.html`/`app.js` на ECharts. Текущая SVG-версия остаётся фолбэком.

---

## 3. Краудсорс-загрузки + целостность

### 3.1 Артефакт сабмишена

PR/форма добавляет каталог `submissions/<github_user>/<run_id>/`:

```
manifest.json     # воспроизводимость + заявленные агрегаты
outputs.jsonl     # сырые выводы по каждой задаче (формат из 1.1, без gold)
```

```json
// manifest.json
{"run_id":"...","submitted_by":"socialpranker","suite":"frames","client_commit":"a1b2c3",
 "models":{"anthropic/claude-fable-5":"2026-06-10"},"seeds":{"panel":0,"synth":0},
 "prompt_template_hash":"sha256:...","grader":"ExactMatch@1",
 "claimed":{"recipe":"fusion-strong","accuracy":0.71,"cost_usd":0.0044,"n":150},
 "token_totals":{"prompt":121800,"completion":21450}}
```

### 3.2 Held-out gold (приватно — иначе всё рушится)

- Публичные клиенты получают **задачи без эталонов**.
- Эталоны (`gold/<suite>.jsonl`) лежат **только** в CI: приватный репозиторий-сабмодуль или зашифрованный GitHub Secret/Actions environment.
- Периодическая **ротация** held-out слайса → заученные/подогнанные рецепты деградируют.

### 3.3 Ре-грейд на CI (ключевой механизм)

```python
# scripts/regrade.py — запускается в CI, НИКОГДА не вызывает LLM
import json, sys
from fusionbench.tasks.registry import REGISTRY
from fusionbench.budget import cost_usd; from fusionbench.presets import MODELS

def regrade(sub_dir, gold_path):
    gold = {g["id"]: g for g in map(json.loads, open(gold_path))}
    man = json.load(open(f"{sub_dir}/manifest.json"))
    grader = REGISTRY[man["suite_type"]].grader
    n = ok = recomputed_cost = 0
    for line in open(f"{sub_dir}/outputs.jsonl"):
        r = json.loads(line); g = gold[r["gold_id"]]
        v = grader.score(r["prediction"], g["reference"], g.get("metadata", {}))
        ok += v.passed; n += 1
        recomputed_cost += _cost_from_tokens(r)        # tokens × прайс из MODELS
    acc = ok / n
    claimed = man["claimed"]
    # вердикт: совпало ли пересчитанное с заявленным
    assert abs(acc - claimed["accuracy"]) <= 0.01, f"accuracy mismatch {acc} vs {claimed['accuracy']}"
    assert abs(recomputed_cost - claimed["cost_usd"]*claimed["n"]) / (claimed['cost_usd']*claimed['n']) <= 0.15
    print(f"OK re-graded acc={acc:.3f} cost=${recomputed_cost:.2f}")
```

```yaml
# .github/workflows/submit.yml
name: Validate submission
on: { pull_request: { paths: ["submissions/**"] } }
jobs:
  regrade:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e .
      - name: Re-grade saved outputs against held-out gold
        env: { GOLD_KEY: ${{ secrets.GOLD_DECRYPT_KEY }} }
        run: |
          python scripts/decrypt_gold.py        # расшифровать приватный эталон
          python scripts/validate_manifest.py submissions/**   # схема + плаузибилити
          python scripts/regrade.py submissions/**             # ре-грейд = required check
```

Что ловит: фейковые/завышенные числа (ре-грейд), неверный грейдер (канонический в CI), нереальную цену/латентность (плаузибилити), невоспроизводимость (манифест). **Никогда не принимаем самозаявленное число, не пересчитав из артефактов.**

### 3.4 CLI `fusionbench submit`

```
$ fusionbench run --suite frames --recipe fusion-strong --limit 150   # пишет runs/<id>/
$ fusionbench submit runs/<id>                                         # валидирует локально,
   # → создаёт submissions/<user>/<id>/, открывает PR (gh) или печатает инструкцию
```

Снижает трение PR-флоу; локальная валидация ловит ошибки до CI.

### 3.5 Поток для не-кодеров (Issue Form)

```yaml
# .github/ISSUE_TEMPLATE/result.yml
name: Submit a run
body:
  - type: input
    id: run_url
    attributes: { label: "URL артефакта (release asset / gist с outputs.jsonl + manifest.json)" }
    validations: { required: true }
  - type: dropdown
    id: suite
    attributes: { label: Suite, options: [frames, ruler, ifbench, agentic] }
```

Бот (`github-issue-parser` + Action) скачивает артефакт, прогоняет `regrade.py`, при успехе коммитит в `submissions/` и закрывает issue, проставляя `submitted_by` из автора issue.

---

## 4. Геймификация (очки только за верифицированное)

### 4.1 Вклад и веса

| Вклад | Базовый вес | Условие начисления |
|---|---|---|
| Новый верифицированный сьют задач | 100 | принят в `REGISTRY`, CI зелёный |
| Новый адаптер модели / метод fusion | 60 | мерджнут, есть тест |
| Новая ячейка (модель × задача) | 20 | ре-грейд совпал |
| **Независимое воспроизведение** чужой ячейки | 25 | совпало с оригиналом ±1% *(платим больше, чем за rerun)* |
| Багфикс / улучшение харнесса | 15 | мерджнут |
| N-й повтор существующей ячейки | 20·0.5^(N-1) | лог-затухание → ~0 |

### 4.2 `scripts/score_contributions.py` (логика)

```python
# читает merged submissions + git-историю -> site/leaderboard.json
def points_for(contrib, history):
    base = WEIGHTS[contrib.kind]
    if contrib.kind == "cell":
        prior = history.count_cells(contrib.cell_key)      # сколько раз ячейку уже делали
        base *= 0.5 ** prior                               # diminishing returns
    if contrib.kind == "reproduction" and contrib.confirms_existing:
        base = WEIGHTS["reproduction"]
    return base

def contributor_score(user, history):
    raw = sum(points_for(c, history) for c in history.verified_of(user))
    fail = history.reproduction_failure_rate(user)
    return 0 if fail > 0.5 else raw                        # shadow-метрика: высокий провал → стоп
```

### 4.3 Тиры и бейджи

| Тир | Порог (по составу, не сумме) |
|---|---|
| Contributor | ≥1 верифицированный вклад |
| Verified | ≥5 ячеек ИЛИ ≥1 воспроизведение |
| Maintainer | ≥1 сьют/адаптер + ≥10 воспроизведений |
| Core | ≥3 сьюта/адаптера + устойчивый трек воспроизведений |

Бейджи: `First Reproducer`, `Suite Author`, `Bug Hunter`, `Domain Expert: <тип>`. Признание: авто-`CITATION.cff` (раздел contributors) + соавторство в релизах/препринте для Core.

### 4.4 `leaderboard.json` + анти-Goodhart

```json
{"updated":"2026-06-14","contributors":[
  {"user":"mira_k","points":870,"tier":"Maintainer","badges":["Suite Author","First Reproducer"],
   "verified":42,"reproductions":11,"repro_fail_rate":0.04}]}
```

Сейфгарды (каждый → что блокирует): verify-before-score (фейки) · валидация мейнтейнера + grace-period (мусорные PR) · новизна+лог-затухание (спам-rerun'ы) · оплата воспроизведений (крауд-аудит) · repro-fail shadow-метрика (накрутка качеством) · **относительный** лидерборд, ранги рядом с тобой (демотивация хвоста) · рейт-лимит + бан рецидивистов (voting-ring). **Не делать:** глобальный абсолютный рейтинг; награды, обмениваемые на дефицит; один показатель как цель.

---

## 5. Фазовый план + критерии приёмки

**Фаза 1 — стержень.** `grading/` (base + ExactMatch, Numeric, Synthetic, Constraint), `tasks/base.py`, `tasks/registry.py`, сохранение `runs/<id>/outputs.jsonl`, новые типы RULER + IFBench.
*Приёмка:* `run_v0 --suite ruler --mock` и `--suite ifbench --mock` зелёные; `outputs.jsonl` пишется; юнит-тесты на каждый грейдер.

**Фаза 2 — целостность.** `gold/` приватно + `decrypt_gold.py`, `regrade.py`, `validate_manifest.py`, `submit.yml`, `fusionbench submit`.
*Приёмка:* подложный `outputs.jsonl` с завышенной точностью **падает** в CI; корректный — проходит; плаузибилити ловит заниженную цену.

**Фаза 3 — визуал v2.** `build_catalog.py` → `data.json`; `site/app.js` на ECharts (hero Pareto + heatmap + explorer + deep-links).
*Приёмка:* сайт строится из `data.json`; фильтры пишут URL-hash; тёмная/светлая темы; «скачать данные» работает.

**Фаза 4 — краудсорс + доска.** Issue Form + бот; `score_contributions.py` → `leaderboard.json`; страница доски (относительный ранг).
*Приёмка:* сабмишен через PR и через Issue Form доходит до каталога; очки начисляются только после зелёного ре-грейда; rerun даёт затухающие очки.

**Фаза 5 (позже) — HF Space-витрина.** submissions/results datasets + Gradio-лидерборд + приватный evaluator-Space.

Фазы 1–2 — фундамент; Фазу 3 можно вести параллельно.

---

## Источники

**Типы/датасеты:** [AA Intelligence Index v4](https://artificialanalysis.ai/methodology/intelligence-benchmarking) · [HELM Capabilities](https://crfm.stanford.edu/2025/03/20/helm-capabilities.html) · [LiveCodeBench](https://livecodebench.github.io/) · [GPQA Diamond](https://epoch.ai/benchmarks/gpqa-diamond) · [FRAMES](https://huggingface.co/datasets/google/frames-benchmark) · [τ²-bench-Verified](https://github.com/amazon-agi/tau2-bench-verified) · [RULER](https://arxiv.org/abs/2404.06654) · [IFBench](https://github.com/allenai/IFBench) · [SimpleQA Verified](https://arxiv.org/html/2509.07968v1)

**Визуал:** [Artificial Analysis](https://artificialanalysis.ai/) · [Epoch Benchmarks](https://epoch.ai/blog/introducing-benchmarks-dashboard) · [HELM](https://crfm.stanford.edu/helm/) · [ECharts](https://echarts.apache.org/) · [Observable Plot](https://github.com/observablehq/plot)

**Целостность/хостинг:** [HF Open LLM submitting](https://huggingface.co/docs/leaderboards/en/open_llm_leaderboard/submitting) · [SWE-bench sb-cli](https://www.swebench.com/sb-cli/submit-to-leaderboard/) · [MLPerf audit](https://github.com/mlcommons/inference_policies/blob/master/MLPerf_Audit_Guidelines.adoc) · [Blum & Hardt «The Ladder»](https://proceedings.mlr.press/v37/blum15.pdf) · [Git scraping (Willison)](https://simonwillison.net/2020/Oct/9/git-scraping/) · [Codeless contributions (Issue Forms)](https://stefanbuck.com/blog/codeless-contributions-with-github-issue-forms) · [Building a benchmark on HF](https://huggingface.co/blog/hugging-science/building-a-benchmark-or-challenge)

**Геймификация:** [Kaggle Progression](https://www.kaggle.com/progression) · [all-contributors](https://github.com/all-contributors/all-contributors) · [Hacktoberfest spam fix](https://dev.to/devteam/an-update-on-hacktoberfest-37a) · [Reputation gaming in SO](https://arxiv.org/abs/2111.07101) · [Leaderboard effects](https://arxiv.org/pdf/1707.03704)
