# Промпт для Claude Code — выложить FusionBench на GitHub + Pages

Скопируй всё ниже и вставь в Claude Code (он работает на твоей машине с твоим git/gh и ключом).

---

Контекст: проект FusionBench в `~/Downloads/CODING_PROJECTS/FusionBench` — Python-харнесс,
который меряет, когда multi-model fusion окупается, + генератор публичного каталога. Он уже
собран, но `.git` повреждён (создан в песочнице, залипшие `.lock`). Доведи до чистого
публичного репозитория с CI и GitHub Pages, прогони тесты, при наличии ключа сделай первый
реальный прогон. Делай по шагам, останавливайся и показывай мне вывод, если что-то падает.

1. `cd ~/Downloads/CODING_PROJECTS/FusionBench`

2. Тесты должны пройти:
   `pip install -e ".[dev]" && pytest -q`

3. Пересоздай git начисто (текущий .git битый):
   `rm -rf .git && git init -b main && git add -A && git commit -m "FusionBench v0: harness, recipe search, catalog site, CI/Pages"`

4. Создай удалённый репозиторий и запушь. Если есть gh CLI:
   `gh repo create fusionbench --public --source=. --remote=origin --push`
   Иначе создай пустой репо на github.com и:
   `git remote add origin git@github.com:<МОЙ_ЛОГИН>/fusionbench.git && git push -u origin main`

5. Включи Pages через Actions:
   `gh api -X POST repos/<МОЙ_ЛОГИН>/fusionbench/pages -f build_type=workflow`
   (или вручную: Settings → Pages → Source = GitHub Actions). Дождись workflow
   «Build & deploy catalog» и проверь, что сайт задеплоился.

6. Замени плейсхолдеры `yourname` на мой логин в `README.md` (бейджи) и `CITATION.cff` (url),
   закоммить и запушь.

7. (Опционально, нужен платный ключ) первый реальный прогон:
   - `cp .env.example .env` и впиши `OPENROUTER_API_KEY`.
   - Сверь слаги/цены моделей в `src/fusionbench/presets.py` (помечены PLACEHOLDER) с реальными
     на openrouter.ai — без этого live-прогон упадёт или посчитает неверную стоимость.
   - `pip install datasets`
   - `python scripts/check_setup.py --live`  (проверка ключа одним дешёвым вызовом)
   - `python scripts/run_v0.py --suite frames --budget 6000 --limit 150`  (первая настоящая цифра)
   - `python scripts/build_catalog.py --runs "runs/*.jsonl" --out site/index.html`
   - закоммить реальные результаты: `git add -f runs/*.jsonl && git commit -m "first live run" && git push`
     (runs/ в .gitignore, поэтому `-f`). Pages обновится реальными данными.

В конце дай мне ссылку на репозиторий и на опубликованный сайт.
