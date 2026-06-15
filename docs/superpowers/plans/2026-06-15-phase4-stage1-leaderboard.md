# Фаза 4 этап 1 — движок очков + доска лидеров: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Начислять очки контрибьюторам за верифицированные cell-вклады и показывать относительную доску лидеров на сайте, аддитивно к работающему submit/regrade-флоу.

**Architecture:** Подход A (зеркалит Фазу 3): чистое ядро `score_contributions(submissions)→dict` (юнит-тесты) + I/O-обёртка (читает `submissions/*/manifest.json`, пишет `site/leaderboard.json` + `site/leaderboard.html`) + рукописный `site/leaderboard.js` (фетчит json, рисует относительную таблицу). Verify-before-score = «manifest лежит в submissions/ на main = прошёл regrade».

**Tech Stack:** Python 3 (интерпретатор `.venv/bin/python` — НЕТ `python` на PATH), pytest. Ванильный JS (без сборки), node для опц. JS-юнитов. ECharts не нужен (доска — HTML-таблица). Сайт деплоится через `.github/workflows/pages.yml`.

**Источники:** спека `docs/superpowers/specs/2026-06-15-phase4-stage1-leaderboard-design.md`; proposal §4.

---

## Контекст: ключевые факты (verify перед утверждением)

- **Манифест сабмишна** `submissions/<user>/<run_id>/manifest.json`: топ-поля `schema_version`, `run_id`, `submitted_by`, `suite`, `claimed`; в `claimed` — `recipe` (str), `accuracy` (float), `cost_usd` (float), `n` (int). Опц.: `grader`, `client_commit`.
- **Cell-ключ** = `(suite, claimed.recipe)`, строкой `"<suite>×<recipe>"`.
- **Verify-before-score**: `regrade.py` пишет вердикт только в stdout/exit-code, `submit.yml` НЕ коммитит маркер обратно → факт «manifest в `submissions/` на main» = прошёл required-check regrade. Скрипт regrade НЕ перезапускает.
- **Интерпретатор**: `.venv/bin/python` (bare `python` отсутствует). pytest: `.venv/bin/python -m pytest`.
- **innerHTML запрещён** проектным PreToolUse-хуком — только `textContent`/`createElement` в JS.
- **gitignore site/**: `site/*` + `!site/app.js`. Чтобы трекать `leaderboard.js` — добавить `!site/leaderboard.js`. `leaderboard.html`/`leaderboard.json` — build output, НЕ коммитятся.
- **Герметичность тестов** (память): тесты НЕ читают реальный `submissions/`, генерят manifest в `tmp_path`.

---

## File Structure

- **Create** `scripts/score_contributions.py` — чистое ядро `score_contributions()` + I/O `main()` (читает submissions, пишет json+html).
- **Create** `tests/test_score_contributions.py` — pytest-юниты на чистое ядро.
- **Create** `site/leaderboard.js` — рукописный, трекается (`!site/leaderboard.js`).
- **Create** seed-фикстуры: `submissions/<user>/<run_id>/manifest.json` (mock, для демо доски).
- **Modify** `scripts/build_catalog.py` — ссылка на доску в шапке шаблона `PAGE`.
- **Modify** `.github/workflows/pages.yml` — шаг генерации доски.
- **Modify** `.gitignore` — `!site/leaderboard.js`.
- `site/leaderboard.html`, `site/leaderboard.json` — генерятся (не правятся руками, не коммитятся).

---

## Task 1: Чистое ядро очков `score_contributions()` (TDD)

**Files:**
- Create: `scripts/score_contributions.py` (только чистая функция + хелперы; I/O в Task 2)
- Create: `tests/test_score_contributions.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_score_contributions.py`:

```python
# tests/test_score_contributions.py
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import score_contributions as sc  # noqa: E402


def _man(user, suite, recipe, run_id, accuracy=0.7, cost_usd=0.004, n=100):
    # shape of submissions/<user>/<run_id>/manifest.json (claimed nested as in real manifests)
    return {"schema_version": 1, "run_id": run_id, "submitted_by": user, "suite": suite,
            "claimed": {"recipe": recipe, "accuracy": accuracy, "cost_usd": cost_usd, "n": n}}


def test_single_cell_single_user():
    subs = [_man("alice", "frames", "fusion-strong", "r1")]
    lb = sc.score_contributions(subs, now="2026-06-15")
    assert lb["updated"] == "2026-06-15"
    assert lb["contributors"] == [
        {"user": "alice", "points": 20.0, "verified": 1, "cells": ["frames×fusion-strong"]}
    ]


def test_decay_across_users():
    # same cell submitted by 3 users, ordered by run_id → 20 / 10 / 5
    subs = [_man("a", "frames", "fusion", "r3"),
            _man("b", "frames", "fusion", "r1"),
            _man("c", "frames", "fusion", "r2")]
    lb = sc.score_contributions(subs, now="2026-06-15")
    pts = {c["user"]: c["points"] for c in lb["contributors"]}
    assert pts == {"b": 20.0, "c": 10.0, "a": 5.0}   # r1=20, r2=10, r3=5


def test_decay_same_user_accumulates():
    # one user, same cell ×3 → 20+10+5 = 35 (prior counted per cell globally)
    subs = [_man("alice", "frames", "fusion", "r1"),
            _man("alice", "frames", "fusion", "r2"),
            _man("alice", "frames", "fusion", "r3")]
    lb = sc.score_contributions(subs, now="2026-06-15")
    assert lb["contributors"][0] == {
        "user": "alice", "points": 35.0, "verified": 3, "cells": ["frames×fusion"]
    }


def test_sort_points_desc_then_user_asc():
    subs = [_man("zoe", "frames", "a", "r1"),         # zoe 20
            _man("amy", "ruler", "b", "r2"),          # amy 20
            _man("amy", "code", "c", "r3")]           # amy +20 = 40
    lb = sc.score_contributions(subs, now="2026-06-15")
    assert [c["user"] for c in lb["contributors"]] == ["amy", "zoe"]   # 40 > 20
    assert lb["contributors"][0]["points"] == 40.0


def test_empty_input():
    lb = sc.score_contributions([], now="2026-06-15")
    assert lb == {"updated": "2026-06-15", "contributors": []}


def test_malformed_manifest_skipped():
    subs = [_man("alice", "frames", "fusion", "r1"),
            {"submitted_by": "bob"},                  # no suite/claimed → skipped
            {"suite": "frames", "claimed": {"recipe": "x"}}]  # no submitted_by → skipped
    lb = sc.score_contributions(subs, now="2026-06-15")
    assert [c["user"] for c in lb["contributors"]] == ["alice"]
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_score_contributions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'score_contributions'` (или `AttributeError`).

- [ ] **Step 3: Реализовать чистое ядро в `scripts/score_contributions.py`**

Создать `scripts/score_contributions.py`:

```python
#!/usr/bin/env python3
"""Score crowdsourced contributions into a relative leaderboard.

Pure core: score_contributions(submissions, now) -> leaderboard dict.
I/O wrapper (read submissions/*/manifest.json, write site/leaderboard.json + .html)
is added in a later task. Verify-before-score: a manifest present under submissions/
on main has already passed regrade (submit.yml required check) — we do NOT re-grade.
"""
import sys

WEIGHT_CELL = 20  # proposal §4.1 — points for a new verified (recipe × suite) cell


def _valid(man):
    if not isinstance(man, dict):
        return False
    if not man.get("submitted_by") or not man.get("suite"):
        return False
    claimed = man.get("claimed")
    return isinstance(claimed, dict) and bool(claimed.get("recipe"))


def _cell_key(man):
    return man["suite"] + "×" + man["claimed"]["recipe"]


def score_contributions(submissions, now):
    """submissions: iterable of manifest dicts. now: ISO date string (caller-supplied,
    not generated here — keeps output deterministic for tests). Returns leaderboard dict."""
    valid = [m for m in submissions if _valid(m)]
    # deterministic order: by run_id (lexicographic), fallback "" so decay is stable
    valid.sort(key=lambda m: str(m.get("run_id", "")))

    seen_cell = {}                       # cell_key -> how many prior submissions of that cell
    by_user = {}                         # user -> {"points": float, "verified": int, "cells": set}
    for m in valid:
        cell = _cell_key(m)
        prior = seen_cell.get(cell, 0)
        pts = WEIGHT_CELL * (0.5 ** prior)
        seen_cell[cell] = prior + 1
        u = by_user.setdefault(m["submitted_by"],
                               {"points": 0.0, "verified": 0, "cells": set()})
        u["points"] += pts
        u["verified"] += 1
        u["cells"].add(cell)

    contributors = [
        {"user": user, "points": round(d["points"], 2),
         "verified": d["verified"], "cells": sorted(d["cells"])}
        for user, d in by_user.items()
    ]
    # sort: points desc, then user asc (deterministic tie-break)
    contributors.sort(key=lambda c: (-c["points"], c["user"]))
    return {"updated": now, "contributors": contributors}
```

- [ ] **Step 4: Прогнать тест — PASS**

Run: `.venv/bin/python -m pytest tests/test_score_contributions.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/score_contributions.py tests/test_score_contributions.py
git commit -m "feat: score_contributions — чистое ядро очков (cell + лог-затухание) + тесты"
```

---

## Task 2: I/O-обёртка — чтение submissions + запись leaderboard.json

**Files:**
- Modify: `scripts/score_contributions.py` (добавить `load_submissions`, `main`, CLI)
- Modify: `tests/test_score_contributions.py` (тест на load_submissions из tmp_path — герметично)

- [ ] **Step 1: Написать падающий тест на load_submissions**

Добавить в `tests/test_score_contributions.py`:

```python
import json


def test_load_submissions_reads_manifests(tmp_path):
    # build a fake submissions tree in tmp_path (hermetic — no real submissions/)
    d = tmp_path / "submissions" / "alice" / "r1"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps(_man("alice", "frames", "fusion", "r1")))
    bad = tmp_path / "submissions" / "bob" / "r2"
    bad.mkdir(parents=True)
    (bad / "manifest.json").write_text("{ not json")        # malformed → skipped, no crash
    subs = sc.load_submissions(tmp_path / "submissions")
    users = sorted(m["submitted_by"] for m in subs)
    assert users == ["alice"]                                # bob's broken json dropped


def test_load_submissions_missing_dir(tmp_path):
    subs = sc.load_submissions(tmp_path / "nope")            # absent dir → empty, no crash
    assert subs == []
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_score_contributions.py -k load_submissions -q`
Expected: FAIL — `AttributeError: module 'score_contributions' has no attribute 'load_submissions'`.

- [ ] **Step 3: Добавить load_submissions + main + CLI**

В `scripts/score_contributions.py` добавить (после `score_contributions`, плюс импорты `json`, `argparse`, `pathlib` вверху):

```python
import json
import argparse
from pathlib import Path


def load_submissions(submissions_dir):
    """Read every submissions/<user>/<run_id>/manifest.json. Malformed/unreadable
    manifests are skipped with a warning (not fatal). Absent dir -> []."""
    root = Path(submissions_dir)
    out = []
    if not root.is_dir():
        return out
    for mf in sorted(root.glob("*/*/manifest.json")):
        try:
            out.append(json.loads(mf.read_text()))
        except (OSError, json.JSONDecodeError) as e:
            print(f"WARN: skipping {mf}: {e}", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--submissions", default="submissions", help="submissions root dir")
    ap.add_argument("--out-json", default="site/leaderboard.json")
    ap.add_argument("--out-html", default="site/leaderboard.html")
    ap.add_argument("--now", required=True, help="ISO date for 'updated' field (e.g. CI date)")
    args = ap.parse_args()

    subs = load_submissions(args.submissions)
    lb = score_contributions(subs, now=args.now)

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(lb, ensure_ascii=False, indent=2) + "\n")

    Path(args.out_html).write_text(render_leaderboard_html())   # template added in Task 4
    print(f"wrote {args.out_json} ({len(lb['contributors'])} contributors) and {args.out_html}")


if __name__ == "__main__":
    main()
```

NOTE: `render_leaderboard_html()` определяется в Task 4. До Task 4 `main()` не вызывается тестами (тесты Task 2 зовут только `load_submissions`/`score_contributions`), поэтому отсутствие функции не ломает юниты. Если хочется зелёный `--check` импорта сейчас — временно `def render_leaderboard_html(): return ""` и заменить в Task 4. (Реализатор: добавь временную заглушку в этом шаге, Task 4 её заменит.)

Добавить временную заглушку в конец файла (заменится в Task 4):
```python
def render_leaderboard_html():
    return ""   # replaced in Task 4 with the real template
```

- [ ] **Step 4: Прогнать тесты — PASS**

Run: `.venv/bin/python -m pytest tests/test_score_contributions.py -q`
Expected: `8 passed`. Также `.venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); import score_contributions"` → без ошибок.

- [ ] **Step 5: Commit**

```bash
git add scripts/score_contributions.py tests/test_score_contributions.py
git commit -m "feat: score_contributions — чтение submissions + запись leaderboard.json (CLI)"
```

---

## Task 3: Seed-фикстуры submissions (демо-данные для доски)

**Files:**
- Create: `submissions/mira_k/frames_demo_1/manifest.json`
- Create: `submissions/mira_k/ruler_demo_1/manifest.json`
- Create: `submissions/alex_p/frames_demo_2/manifest.json`

- [ ] **Step 1: Проверить, что submissions/ трекается (не в gitignore целиком)**

Run: `git check-ignore submissions/ ; echo "exit $?"`
Expected: exit 1 (НЕ игнорируется — submissions/ это контент репо, не build output). Если игнорируется — СТОП, сообщи (это противоречит Фазе 2, где submissions/ — каталог вкладов).

- [ ] **Step 2: Создать 3 seed-манифеста**

Эти манифесты — иллюстративные демо-вклады (как mock-каталог в Фазе 3). Две cell от mira_k + одна общая cell `frames×fusion-strong` от alex_p (демонстрирует затухание: mira_k первая по этой cell, alex_p вторая).

`submissions/mira_k/frames_demo_1/manifest.json`:
```json
{
  "schema_version": 1,
  "run_id": "frames_demo_1",
  "submitted_by": "mira_k",
  "suite": "frames",
  "claimed": {"recipe": "fusion-strong", "accuracy": 0.71, "cost_usd": 0.0044, "n": 150},
  "notes": "illustrative seed contribution (mock)"
}
```

`submissions/mira_k/ruler_demo_1/manifest.json`:
```json
{
  "schema_version": 1,
  "run_id": "ruler_demo_1",
  "submitted_by": "mira_k",
  "suite": "ruler",
  "claimed": {"recipe": "best-single", "accuracy": 0.62, "cost_usd": 0.0009, "n": 120},
  "notes": "illustrative seed contribution (mock)"
}
```

`submissions/alex_p/frames_demo_2/manifest.json`:
```json
{
  "schema_version": 1,
  "run_id": "frames_demo_2",
  "submitted_by": "alex_p",
  "suite": "frames",
  "claimed": {"recipe": "fusion-strong", "accuracy": 0.70, "cost_usd": 0.0041, "n": 150},
  "notes": "illustrative seed contribution (mock)"
}
```

- [ ] **Step 3: Проверить расчёт очков на seed**

Run: `.venv/bin/python scripts/score_contributions.py --submissions submissions --out-json /tmp/lb.json --out-html /tmp/lb.html --now 2026-06-15 && cat /tmp/lb.json`
Expected: mira_k = 20 (frames×fusion-strong, prior 0) + 20 (ruler×best-single, prior 0) = 40, verified 2;
alex_p = 10 (frames×fusion-strong, prior 1 — после mira_k по run_id frames_demo_1 < frames_demo_2) = 10, verified 1.
Порядок: mira_k (40), alex_p (10).

- [ ] **Step 4: Commit**

```bash
git add submissions/mira_k submissions/alex_p
git commit -m "test: seed-фикстуры submissions для демо доски лидеров"
```

---

## Task 4: Доска — render_leaderboard_html + leaderboard.js + gitignore

**Files:**
- Modify: `scripts/score_contributions.py` (заменить заглушку `render_leaderboard_html` реальным шаблоном)
- Create: `site/leaderboard.js` (рукописный)
- Modify: `.gitignore` (`!site/leaderboard.js`)

- [ ] **Step 1: gitignore — трекать leaderboard.js**

В `.gitignore`, рядом со строкой `!site/app.js`, добавить:
```
!site/leaderboard.js
```

- [ ] **Step 2: Заменить заглушку render_leaderboard_html реальным шаблоном**

В `scripts/score_contributions.py` заменить `def render_leaderboard_html(): return ""` на полноценный HTML-шаблон. Стили — клон light/dark из каталога (общая палитра Фазы 3). Страница пустая до JS; `leaderboard.js` наполняет `#board` из `leaderboard.json`.

```python
LEADERBOARD_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FusionBench — leaderboard</title>
<style>
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#111827;background:#f8fafc;margin:0;line-height:1.55}
.wrap{max-width:880px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:26px;font-weight:600;margin:0 0 4px}
.sub{color:#6b7280;margin:0 0 24px}
.nav{margin:0 0 20px;font-size:14px}
.nav a{color:#0d9488;text-decoration:none}
table{width:100%;border-collapse:collapse;font-size:14px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #f1f5f9}
th{background:#f8fafc;color:#6b7280;font-weight:600;font-size:12.5px;text-transform:uppercase;letter-spacing:.03em}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.bar-wrap{background:#f1f5f9;border-radius:999px;height:8px;overflow:hidden;min-width:80px}
.bar-fill{display:block;height:100%;background:#0d9488}
.foot{color:#9ca3af;font-size:12.5px;margin-top:40px;border-top:1px solid #e5e7eb;padding-top:14px}
@media (prefers-color-scheme: dark){
  body{background:#0f1419;color:#e5e7eb}
  .sub,.foot{color:#9ca3af}
  table{background:#1a1f2e;border-color:#374151}
  th{background:#161b26;color:#9ca3af}
  th,td{border-color:#374151}
  .bar-wrap{background:#374151}
}
</style></head><body><div class="wrap">
<div class="nav"><a href="index.html">← Catalog</a></div>
<h1>Contributor leaderboard</h1>
<p class="sub">Points for verified contributions. Repeat cells decay (log). Relative ranking.</p>
<div id="board"></div>
<p class="foot" id="foot"></p>
<script src="leaderboard.js"></script>
</div></body></html>
"""


def render_leaderboard_html():
    return LEADERBOARD_PAGE
```

NOTE: шаблон — обычная строка (НЕ `.format`), поэтому фигурные скобки CSS НЕ экранируются (в отличие от `build_catalog.py`, где `.format`). Никаких `{}`-плейсхолдеров здесь нет — данные грузит JS из json.

- [ ] **Step 3: Создать `site/leaderboard.js` (относительная доска, без innerHTML)**

Создать `site/leaderboard.js`:

```javascript
// site/leaderboard.js — renders the relative contributor leaderboard from leaderboard.json.
// No innerHTML (project hook blocks it) — only textContent / createElement.
(function () {
  if (typeof document === "undefined") return;  // not a browser (node UMD load)

  var board = document.getElementById("board");
  var foot = document.getElementById("foot");

  fetch("leaderboard.json")
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) {
      var rows = (data && data.contributors) || [];
      if (foot) foot.textContent = "Updated " + ((data && data.updated) || "");
      if (!rows.length) {
        board.textContent = "Пока нет верифицированных вкладов.";
        board.style.color = "#6b7280"; board.style.padding = "16px";
        return;
      }
      board.appendChild(buildTable(rows));
    })
    .catch(function (e) {
      board.textContent = "Could not load leaderboard.json: " + e.message;
      board.style.color = "#6b7280"; board.style.padding = "16px";
    });

  function buildTable(rows) {
    var max = maxPoints(rows);
    var cols = ["#", "user", "points", "verified", "cells"];
    var tbl = document.createElement("table");
    var thead = document.createElement("thead");
    var htr = document.createElement("tr");
    cols.forEach(function (k) {
      var th = document.createElement("th"); th.textContent = k; htr.appendChild(th);
    });
    thead.appendChild(htr); tbl.appendChild(thead);
    var tb = document.createElement("tbody");
    rows.forEach(function (c, i) {
      var tr = document.createElement("tr");
      tr.appendChild(td(String(i + 1), "num"));
      tr.appendChild(td(c.user));
      tr.appendChild(pointsCell(c.points, max));
      tr.appendChild(td(String(c.verified), "num"));
      tr.appendChild(td((c.cells || []).join(", ")));
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    return tbl;
  }

  function pointsCell(points, max) {
    // relative bar (points / leader) + the number — avoids absolute-number culting
    var cell = document.createElement("td");
    var n = document.createElement("span");
    n.textContent = points;
    n.style.marginRight = "8px"; n.style.fontVariantNumeric = "tabular-nums";
    var wrap = document.createElement("span");
    wrap.className = "bar-wrap";
    wrap.style.display = "inline-block"; wrap.style.verticalAlign = "middle";
    wrap.style.width = "100px";
    var fill = document.createElement("span");
    fill.className = "bar-fill";
    fill.style.width = (max > 0 ? Math.round(100 * points / max) : 0) + "%";
    wrap.appendChild(fill);
    cell.appendChild(n); cell.appendChild(wrap);
    return cell;
  }

  function maxPoints(rows) {
    return rows.reduce(function (m, c) { return c.points > m ? c.points : m; }, 0);
  }

  function td(text, cls) {
    var el = document.createElement("td");
    el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
})();
```

NOTE: `leaderboard.js` — простая browser-only вьюшка; чистых derive-функций, требующих node-юнитов, тут нет (нормировка тривиальна). Опц. node-тест НЕ делаем в этом этапе (вне объёма, как node-CI в Фазе 3).

- [ ] **Step 4: Проверить генерацию + grep innerHTML**

Run: `.venv/bin/python scripts/score_contributions.py --submissions submissions --out-json site/leaderboard.json --out-html site/leaderboard.html --now 2026-06-15`
Expected: `wrote site/leaderboard.json (2 contributors) and site/leaderboard.html`.
Run: `node --check site/leaderboard.js` → ок.
Run: `grep -n 'innerHTML' site/leaderboard.js` → пусто (exit 1).
Run: `grep -cE 'id="board"|leaderboard\.js|prefers-color-scheme' site/leaderboard.html` → ≥3 (все три маркера присутствуют; точное число строк не важно).

- [ ] **Step 5: Прогнать pytest (не сломано)**

Run: `.venv/bin/python -m pytest tests/test_score_contributions.py -q`
Expected: `8 passed`.

- [ ] **Step 6: Commit**

```bash
git add scripts/score_contributions.py site/leaderboard.js .gitignore
git commit -m "feat: страница доски лидеров — render_leaderboard_html + leaderboard.js (относительная, без innerHTML)"
```

---

## Task 5: Навигация catalog → leaderboard в шаблоне PAGE

**Files:**
- Modify: `scripts/build_catalog.py` (ссылка на доску в шапке `PAGE`)

- [ ] **Step 1: Найти точку вставки в шаблоне PAGE**

Прочитать `scripts/build_catalog.py`, найти в шаблоне `PAGE` строку `<h1>{title}</h1>` (шапка). Вставить НАД `<h1>` навигацию (та же стилистика, что `.nav` на доске).

- [ ] **Step 2: Добавить ссылку на доску**

В `scripts/build_catalog.py`, в шаблоне `PAGE`, НЕПОСРЕДСТВЕННО перед строкой `<h1>{title}</h1>` вставить:
```python
<div class="nav" style="margin:0 0 16px;font-size:14px"><a href="leaderboard.html" style="color:#0d9488;text-decoration:none">Contributor leaderboard →</a></div>
```
ВНИМАНИЕ: `build_catalog.py` рендерит `PAGE` через `.format(...)` — в этой строке НЕТ фигурных скобок, поэтому экранирование не нужно. Если добавляешь inline-CSS с `{}` — НЕ делай (используй атрибут style без фигурных скобок CSS-блоков). Проверь, что `.format()` не сломался (Task 6 Step 1).

- [ ] **Step 3: Проверить, что каталог всё ещё генерится**

Run: `.venv/bin/python scripts/build_catalog.py --runs "runs/catalog*.jsonl" --out site/index.html`
Expected: `wrote site/index.html and site/data.json ...` (без ошибки `.format`).
Run: `grep -c 'leaderboard.html' site/index.html` → 1.

- [ ] **Step 4: pytest не сломан**

Run: `.venv/bin/python -m pytest tests/test_build_data.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_catalog.py
git commit -m "feat: ссылка на доску лидеров в шапке каталога"
```

---

## Task 6: Интеграция в pages.yml + полная проверка

**Files:**
- Modify: `.github/workflows/pages.yml` (шаг генерации доски)

- [ ] **Step 1: Добавить шаг генерации доски в pages.yml**

В `.github/workflows/pages.yml`, в job `build`, ПОСЛЕ шага `- run: python scripts/build_catalog.py --runs "runs/catalog*.jsonl" --out site/index.html` и ПЕРЕД `- run: touch site/.nojekyll`, вставить:
```yaml
      - name: Build contributor leaderboard
        run: python scripts/score_contributions.py --submissions submissions --out-json site/leaderboard.json --out-html site/leaderboard.html --now "$(date -u +%Y-%m-%d)"
```
NOTE: `--now` берётся из `date` в CI (не из Python — детерминизм ядра сохранён, дата приходит снаружи). Это статичная команда без untrusted-input (нет `${{ github.event.* }}`) — security-хук может предупредить, но инъекции нет.

- [ ] **Step 2: Локальная симуляция CI — пустой submissions (не падать)**

Симулировать отсутствие реальных вкладов (только seed останутся, но проверим и пустой случай):
```bash
.venv/bin/python scripts/score_contributions.py --submissions /tmp/empty_subs --out-json /tmp/empty_lb.json --out-html /tmp/empty_lb.html --now 2026-06-15 && cat /tmp/empty_lb.json
```
Expected: `wrote ... (0 contributors) ...`, json = `{"updated":"2026-06-15","contributors":[]}`. Скрипт НЕ падает на отсутствующей директории.

- [ ] **Step 3: Полная регенерация сайта (каталог + доска)**

```bash
.venv/bin/python scripts/build_catalog.py --runs "runs/catalog*.jsonl" --out site/index.html
.venv/bin/python scripts/score_contributions.py --submissions submissions --out-json site/leaderboard.json --out-html site/leaderboard.html --now 2026-06-15
```
Expected: оба пишут файлы; `site/leaderboard.json` = 2 contributors (mira_k 40, alex_p 10).

- [ ] **Step 4: Playwright — проверить доску в браузере**

Поднять `.venv/bin/python -m http.server 8770 --directory site` (фон). Через Playwright (`browser_navigate` + `browser_evaluate`, dark-эмуляция через `browser_run_code_unsafe` + `page.emulateMedia`):
- `http://localhost:8770/leaderboard.html` → таблица с 2 строками (mira_k, alex_p), points-бары, нет console-ошибок (favicon 404 игнор);
- порядок: mira_k (40) сверху, alex_p (10) — бар alex_p = 25% от лидера;
- навигация: `← Catalog` ведёт на index.html; на index.html ссылка `Contributor leaderboard →` ведёт назад;
- dark-эмуляция: страница тёмная, таблица читаема;
- пустое состояние: временно подменить fetch на пустой — или проверить логику отдельно (опц.).
Остановить сервер. Скриншот light+dark.

- [ ] **Step 5: Все тесты + линт**

Run: `.venv/bin/python -m pytest -q` → всё зелёное (новые test_score_contributions + прежние; норма прошлых 1 skipped + 1 xfailed).
Run: `node --check site/leaderboard.js` → ок; `grep -n innerHTML site/leaderboard.js` → пусто.
Run: `ruff check scripts/score_contributions.py` (системный ruff; ожидаем чисто или только осознанные).

- [ ] **Step 6: Commit pages.yml**

```bash
git add .github/workflows/pages.yml
git commit -m "ci: pages — генерировать доску лидеров (score_contributions) при деплое"
```

---

## Verification (перед «готово»)

- [ ] `.venv/bin/python -m pytest -q` — всё зелёное (ядро очков + прежние; норма 1 skipped + 1 xfailed).
- [ ] `score_contributions.py` на seed → leaderboard.json: mira_k 40 / alex_p 10 (затухание frames×fusion-strong: 20→10).
- [ ] Пустой `submissions/` → валидный пустой leaderboard.json, без падения.
- [ ] `node --check site/leaderboard.js` ок; нет `innerHTML` (grep пусто).
- [ ] `leaderboard.html` содержит `id="board"`, `leaderboard.js`, dark CSS.
- [ ] `index.html` содержит ссылку `leaderboard.html` (навигация).
- [ ] Playwright: доска рендерит таблицу из json; относительные бары; навигация catalog↔leaderboard; dark; пустое состояние.
- [ ] `build_catalog.py` `.format()` не сломан (каталог генерится).
- [ ] Спека перечитана построчно: движок очков, лог-затухание, verify-before-score, относительная доска, seed, интеграция CI — реализованы; бот/тиры/бейджи/воспроизведения — вне объёма (не делались).

## Примечания

- Чисто аддитивно: submit/regrade Фазы 2 и каталог Фазы 3 не тронуты (кроме навигационной ссылки).
- `leaderboard.html`/`leaderboard.json` — build output (НЕ коммитятся); трекается только `leaderboard.js` (через `!site/leaderboard.js`). Память [[site-gitignore-build-output]].
- `--now` всегда приходит снаружи (CLI/CI), НЕ генерится в Python — детерминизм тестов.
- Скрипт читает `submissions/*/manifest.json` точечным glob, не широким `runs/*.jsonl` — память [[run-v0-two-schemas-glob-trap]] (не наступать на разносхемные файлы).
- Деплой Pages уже работает (PR #3 починил glob); новый шаг доски добавляется в тот же build-job.
