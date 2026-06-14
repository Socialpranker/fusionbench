# FusionBench v2 — механики сообщества (deep-research предложение)

*14 июня 2026*

## Главное: это не 4 фичи, а одна архитектура

Все четыре запроса сходятся в один стержень — **верифицируемый грейдер на каждый тип задачи + сохранённые сырые выводы моделей + ре-грейд на CI**. Из него почти бесплатно вытекает остальное:

- новый тип задач (#1) = пара `(Loader, Grader)`;
- доверие к загрузкам (#3) = CI заново оценивает *сохранённые выводы* по скрытому эталону — без повторных платных вызовов LLM;
- хостинг и лидерборд (#4) = PR + GitHub Actions пересобирают каталог и доску;
- геймификация (#4) = очки только за то, что CI смог воспроизвести.

Поэтому строим сначала стержень, остальное навешивается.

---

## 1. Типы задач — таксономия + только верифицируемые датасеты

Минимальный непересекающийся набор (свод HELM Capabilities / Artificial Analysis v4 / Open LLM v2):

| Тип | Датасет (open, авто-проверяемый) | Грейдинг |
|---|---|---|
| Код | LiveCodeBench (оконный → без утечки) + SWE-bench Verified | прогон unit-тестов |
| Математика | MATH-500 + AIME 2025/26 | numeric / SymPy exact-match |
| Наука | GPQA Diamond | 4-way MC exact-match |
| Multi-hop QA | FRAMES *(уже есть)* | normalized string |
| Агентность / инструменты | τ²-bench-Verified | сравнение конечного состояния среды (без судьи) |
| Длинный контекст | RULER | синтетика → contamination-proof |
| Следование инструкциям | IFBench | питон-верификатор на каждое ограничение |
| Факт. короткий ответ | SimpleQA Verified | string-match с эталоном |
| *(overlay)* Мультиязычность | Global-MMLU / переводные сплиты | как у базового типа |

**Избегать как основные (насыщены/загрязнены):** HumanEval(+), GSM8K, HotpotQA, MMLU, base SWE-bench, MGSM.

**Абстракция:** тип задачи = `(Loader, Grader)`. Библиотека переиспользуемых грейдеров — `ExactMatch`, `Numeric/SymPy`, `UnitTest` (sandbox), `SetMatch`, `Constraint` (питон-чек), `State` (сравнение состояния среды), `Synthetic`. Реестр-манифест `{type, loader, grader, license, contamination_policy}`. Добавить тип = бросить два файла. Всё детерминированно и дёшево — **именно это делает CI-ре-грейд (#3) возможным.**

---

## 2. Визуал — что и на чём

Набор (одна мысль на график):

- **Герой:** cost-quality Pareto-scatter с подписанным квадрантом «worth-it» + линия фронтира, ось цены логарифмическая, цвет по семейству моделей (приём Artificial Analysis — квадрант снимает нужду в подписи).
- **Рабочая лошадь:** heatmap «тип задачи × рецепт» (стоит/не стоит, дивергентная шкала red→green, дельта в ячейке).
- **Поддержка:** heatmap комплементарности «модель × модель».
- **Эксплорер:** тот же scatter + фильтры (тип, потолок цены, мин. качество).
- **Не радар** — превращается в шум за пределами 3–6 осей.

**Библиотека: ECharts** — нативный heatmap, ~100 КБ (tree-shake), спека = JS-объект ≈ JSON → один шаблон графика на все типы из одного `data.json` на GitHub Pages. Альтернатива — Observable Plot (терсее). Не Plotly (~3.6 МБ), не Chart.js (нет нативного heatmap → отсекает (b) и (c)).

**Premium-штрихи:** подписанный квадрант + фронтир; shareable deep-links (состояние вида в URL-hash); сортируемая/фильтруемая таблица с drill-down по строке; dark/light с едиными цвето-токенами; сдержанная анимация (~200 мс); «скачать данные + методология» у каждого графика (сигнал доверия как у Epoch).

---

## 3. Загрузки + целостность (критичный пункт)

Правило №1: **никогда не принимаем самозаявленное число, которое не пересчитали из артефактов** (ловушка Papers-with-Code — там копировали чужие цифры и публиковали заведомо ложные).

Ранжированная механика:

1. **Ре-грейд сохранённых выводов на CI (ключ).** Загрузка обязана включать сырые выводы моделей по каждому пункту. CI заново прогоняет *канонический верифицируемый грейдер* по скрытому эталону — **LLM не вызывается, только пересчёт текста**. ~90% защиты по цене копеек (модель SWE-bench минус дорогая часть). Фейковое число, не совпавшее с ре-грейдом собственных выводов, падает прямо в PR-чеке.
2. **Скрытый эталон не отдаём клиентам** — ключи грейдера живут в CI-секрете/приватном репо, периодическая ротация. Без этого пункт 1 рушится (логика приватного теста Kaggle).
3. **Манифест воспроизводимости:** версии моделей, сиды, промпты/шаблон, токены по пунктам, версия грейдера, commit-хеш. «Невоспроизводимо = невалидно» (MLPerf).
4. **Проверки правдоподобия цены/латентности:** заявленная цена vs `токены × прайс`, флаг при отклонении. Ре-грейд проверяет *качество*, это — *цену*.
5. **Submission через PR; CI — вратарь** (обязательные чеки 1/3/4). Трение — это фича: анонимный спам не доходит до лидерборда. CLI `fusionbench submit` снижает трение.
6. Подписанные ран'ы (опц., позже) и репутационный вес (последним, как defense-in-depth).

---

## 4a. Хостинг + живой лидерборд — поэтапно

- **Сейчас: GitHub-native (git как БД).** PR добавляет JSONL → Actions валидирует, ре-грейдит, пересобирает сайт + лидерборд. **$0, максимум доверия, почти ноль ops.** Для не-кодеров — **Issue Forms** + `github-issue-parser` (бот превращает форму в данные, «codeless contributions»). Лидерборд — пересборка на каждый merge (всегда консистентен с каталогом).
- **Потом: Hugging Face Space + Datasets** как дружелюбная витрина: submissions-dataset + results-dataset + Gradio-лидерборд + приватный evaluator-Space (скрытый тест). Бесплатно, ML-родная аудитория, OAuth-идентичность → настоящий *живой* лидерборд и upload-UI без знания git. Минусы: free Spaces засыпают, жёсткая схема полей, привязка к платформе.
- **Бэкенд** (Cloudflare Workers + D1, ~$0–5/мес) — только если перерастёшь оба.

---

## 4b. Геймификация (качество > объём)

Принцип: **очки только за верифицированный (CI-воспроизведённый) вклад.** Это и убивает накрутку — нельзя нафармить то, что нужно заново исполнить.

| Вклад | Вес |
|---|---|
| Новый верифицированный сьют задач | максимум |
| Новый адаптер модели / метод fusion | высокий |
| Новая ячейка (модель × задача) | средний |
| **Независимое воспроизведение** чужого результата | средне-высокий *(платим щедро — это крауд-аудит)* |
| Багфикс / улучшение харнесса | средний |
| N-й повтор существующей ячейки | лог-затухание → ~0 |

**Тиры** (Kaggle-стиль, по *составу* медалей, не по сумме): Contributor → Verified → Maintainer → Core. **Бейджи:** First Reproducer, Suite Author, Bug Hunter, Domain Expert. **Признание:** авто-`CITATION.cff` + соавторство в релизах/препринте для Core — держит людей сильнее очков.

**Анти-Goodhart:** verify-before-score; валидация мейнтейнером + grace-period; новизна + лог-затухание; платим за воспроизведения; теневая метрика «доля проваленных воспроизведений» (высокая → стоп начисления); **относительный** лидерборд (ранги рядом с тобой, не глобальный абсолют — иначе демотивирует хвост); рейт-лимиты + бан рецидивистов.

**Не делать:** глобальный абсолютный лидерборд; награды, обмениваемые на дефицит (футболка Hacktoberfest → волна спам-PR); один показатель как цель.

---

## Предлагаемый порядок сборки

1. **Стержень:** библиотека грейдеров + `(Loader, Grader)` + 2–3 новых верифицируемых типа (RULER, IFBench, τ²-bench) + сохранение сырых выводов в схему результата.
2. **Целостность:** held-out gold в CI + ре-грейд сохранённых выводов + манифест + плаузибилити → PR-submission.
3. **Визуал v2** на ECharts (герой-Pareto + heatmap) из `data.json`.
4. **Краудсорс:** Issue Forms + бот; лидерборд (verified-only) на пересборке.
5. **(Позже)** витрина на HF Space.

Пункты 1–2 — фундамент под всё; визуал (3) можно делать параллельно.

---

## Источники

**Типы/датасеты:** [AA Intelligence Index v4](https://artificialanalysis.ai/methodology/intelligence-benchmarking) · [HELM Capabilities](https://crfm.stanford.edu/2025/03/20/helm-capabilities.html) · [LiveCodeBench](https://livecodebench.github.io/) · [GPQA Diamond](https://epoch.ai/benchmarks/gpqa-diamond) · [FRAMES](https://huggingface.co/datasets/google/frames-benchmark) · [τ²-bench-Verified](https://github.com/amazon-agi/tau2-bench-verified) · [RULER](https://arxiv.org/abs/2404.06654) · [IFBench](https://github.com/allenai/IFBench) · [SimpleQA Verified](https://arxiv.org/html/2509.07968v1)

**Визуал:** [Artificial Analysis](https://artificialanalysis.ai/) · [Epoch Benchmarks](https://epoch.ai/blog/introducing-benchmarks-dashboard) · [HELM](https://crfm.stanford.edu/helm/) · [ECharts](https://echarts.apache.org/) · [Observable Plot](https://github.com/observablehq/plot)

**Целостность/хостинг:** [HF Open LLM submitting](https://huggingface.co/docs/leaderboards/en/open_llm_leaderboard/submitting) · [SWE-bench sb-cli](https://www.swebench.com/sb-cli/submit-to-leaderboard/) · [MLPerf audit](https://github.com/mlcommons/inference_policies/blob/master/MLPerf_Audit_Guidelines.adoc) · [Blum & Hardt «The Ladder»](https://proceedings.mlr.press/v37/blum15.pdf) · [Git scraping (Willison)](https://simonwillison.net/2020/Oct/9/git-scraping/) · [Codeless contributions (Issue Forms)](https://stefanbuck.com/blog/codeless-contributions-with-github-issue-forms) · [Building a benchmark on HF](https://huggingface.co/blog/hugging-science/building-a-benchmark-or-challenge)

**Геймификация:** [Kaggle Progression](https://www.kaggle.com/progression) · [all-contributors](https://github.com/all-contributors/all-contributors) · [Hacktoberfest spam fix](https://dev.to/devteam/an-update-on-hacktoberfest-37a) · [Reputation gaming in SO](https://arxiv.org/abs/2111.07101) · [Leaderboard effects](https://arxiv.org/pdf/1707.03704)
