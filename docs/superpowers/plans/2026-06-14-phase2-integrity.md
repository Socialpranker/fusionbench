# Фаза 2 — целостность: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Пересчитать заявленные метрики сабмишна из сохранённого `outputs.jsonl` против зашифрованного приватного gold, чтобы подложная accuracy падала в CI (HARD), а нереальная цена давала мягкий WARN.

**Architecture:** Тонкие CI-скрипты (`decrypt_gold`/`validate_manifest`/`regrade`) поверх тестируемых модулей (`gold.py` — сериализация reference, `crypto.py` — Fernet). ifbench-констрейнты переводятся на реестр предикатов `{kind, params}`, потому что `Constraint.predicate` — лямбда и в JSON не сериализуется. Ре-грейд вызывает тот же `REGISTRY[suite].grader.score`, что и прогон, поэтому скоринг совпадает бит-в-бит.

**Tech Stack:** Python 3.10+, `cryptography` (Fernet, новая зависимость), pytest. CI — GitHub Actions (`submit.yml`, триггер `submissions/**`).

**Спека:** [docs/superpowers/specs/2026-06-14-phase2-integrity-design.md](../specs/2026-06-14-phase2-integrity-design.md)

**Заметка по верификации:** в проекте нет настроенного ruff (`pyproject.toml` dev = только pytest). Верификация каждой задачи = `pytest`. `ruff check src/fusionbench scripts` — только если ruff установлен глобально; не добавляем его в зависимости (YAGNI).

---

## File Structure

| Файл | Действие | Ответственность |
|---|---|---|
| `src/fusionbench/grading/constraint.py` | Modify | + реестр `CONSTRAINT_FACTORIES`, `constraint_to_dict`/`constraint_from_dict` |
| `src/fusionbench/tasks/ifbench.py` | Modify | шаблоны как данные `{kind, params}`, констрейнты через реестр |
| `src/fusionbench/gold.py` | Create | `example_to_gold`, `gold_to_reference` — граница (де)сериализации gold |
| `src/fusionbench/crypto.py` | Create | `encrypt_bytes`/`decrypt_bytes` (Fernet) |
| `scripts/encrypt_gold.py` | Create | мейнтейнер: `gold/<suite>.jsonl` → `.enc` |
| `scripts/decrypt_gold.py` | Create | CI: `.enc` + `GOLD_DECRYPT_KEY` → `.jsonl` |
| `scripts/dump_gold.py` | Create | мейнтейнер: загрузчик suite → `gold/<suite>.jsonl` |
| `scripts/validate_manifest.py` | Create | схема манифеста + плаузибилити cost (WARN) |
| `scripts/regrade.py` | Create | ядро: пересчёт acc (HARD exit), cost (WARN) |
| `.github/workflows/submit.yml` | Create | триггер `submissions/**`: decrypt→validate→regrade |
| `pyproject.toml` | Modify | + `cryptography` в dependencies |
| `tests/test_constraint_serde.py` | Create | round-trip констрейнтов + тождество вердикта |
| `tests/test_gold.py` | Create | round-trip Example→gold→reference для 3 suite |
| `tests/test_crypto.py` | Create | encrypt→decrypt round-trip |
| `tests/test_regrade.py` | Create | приёмка: honest проходит, tampered падает, cost WARN |
| `tests/fixtures/regrade/` | Create | gold + honest/tampered outputs + манифесты |

---

## Task 1: Реестр предикатов в constraint.py

**Files:**
- Modify: `src/fusionbench/grading/constraint.py`
- Test: `tests/test_constraint_serde.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_constraint_serde.py
from fusionbench.grading.constraint import (
    Constraint, constraint_to_dict, constraint_from_dict, make_constraint,
)


def test_make_constraint_exactly_words():
    c = make_constraint("exactly_words", n=3)
    assert c.check("one two three") is True
    assert c.check("one two") is False


def test_roundtrip_exactly_words():
    c = make_constraint("exactly_words", n=3)
    d = constraint_to_dict(c)
    assert d == {"kind": "exactly_words", "params": {"n": 3}}
    c2 = constraint_from_dict(d)
    # restored predicate behaves identically
    for s in ["a b c", "a b", "x y z w"]:
        assert c2.check(s) == c.check(s)


def test_roundtrip_contains():
    c = make_constraint("contains", word="moon")
    d = constraint_to_dict(c)
    assert d == {"kind": "contains", "params": {"word": "moon"}}
    c2 = constraint_from_dict(d)
    for s in ["the MOON is up", "sun only", ""]:
        assert c2.check(s) == c.check(s)


def test_roundtrip_all_caps():
    c = make_constraint("all_caps")
    d = constraint_to_dict(c)
    assert d == {"kind": "all_caps", "params": {}}
    c2 = constraint_from_dict(d)
    for s in ["HELLO", "Hello", "123"]:
        assert c2.check(s) == c.check(s)


def test_unknown_kind_raises():
    import pytest
    with pytest.raises(KeyError):
        make_constraint("no_such_kind")
    with pytest.raises(KeyError):
        constraint_from_dict({"kind": "no_such_kind", "params": {}})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_constraint_serde.py -v`
Expected: FAIL — `ImportError: cannot import name 'constraint_to_dict'`

- [ ] **Step 3: Write minimal implementation**

Replace the top of `src/fusionbench/grading/constraint.py` (keep `ConstraintGrader` unchanged below). The `Constraint` dataclass gains a `kind` and `params` so it can describe itself for serialization:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .base import Verdict


@dataclass(frozen=True)
class Constraint:
    """One checkable instruction-following rule. `describe_text` surfaces in the verdict
    so a failed submission shows *which* rule broke. `kind`/`params` let the constraint
    serialize to gold and rebuild its predicate via CONSTRAINT_FACTORIES — the predicate
    itself is a lambda and cannot be stored as JSON."""

    describe_text: str
    predicate: Callable[[str], bool]
    kind: str = ""
    params: dict = field(default_factory=dict)

    def check(self, prediction: str) -> bool:
        return self.predicate(prediction)

    def describe(self) -> str:
        return self.describe_text


def _exactly_words(n: int) -> Constraint:
    return Constraint(f"exactly {n} words", lambda p, n=n: len(p.split()) == n,
                      kind="exactly_words", params={"n": n})


def _contains(word: str) -> Constraint:
    return Constraint(f"contains '{word}'", lambda p, w=word: w.lower() in p.lower(),
                      kind="contains", params={"word": word})


def _all_caps() -> Constraint:
    return Constraint("all uppercase",
                      lambda p: p.strip() == p.strip().upper() and any(c.isalpha() for c in p),
                      kind="all_caps", params={})


# kind -> factory. Single source of truth for building and rebuilding constraints.
CONSTRAINT_FACTORIES: dict[str, Callable[..., Constraint]] = {
    "exactly_words": _exactly_words,
    "contains": _contains,
    "all_caps": _all_caps,
}


def make_constraint(kind: str, **params: Any) -> Constraint:
    """Build a constraint by registered kind. Raises KeyError on unknown kind."""
    return CONSTRAINT_FACTORIES[kind](**params)


def constraint_to_dict(c: Constraint) -> dict:
    """Serialize to gold form. Requires the constraint to carry a registered `kind`."""
    if not c.kind:
        raise ValueError(f"constraint {c.describe_text!r} has no kind; cannot serialize")
    return {"kind": c.kind, "params": dict(c.params)}


def constraint_from_dict(d: dict) -> Constraint:
    """Rebuild from gold form via the factory registry."""
    return make_constraint(d["kind"], **d.get("params", {}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_constraint_serde.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Verify existing grading tests still pass**

Run: `pytest tests/test_grading.py -v`
Expected: PASS (Constraint gained optional fields; `ConstraintGrader` unchanged)

- [ ] **Step 6: Commit**

```bash
git add src/fusionbench/grading/constraint.py tests/test_constraint_serde.py
git commit -m "feat: реестр предикатов для сериализации ifbench-констрейнтов"
```

---

## Task 2: Перевести ifbench.py на реестр

**Files:**
- Modify: `src/fusionbench/tasks/ifbench.py`
- Test: `tests/test_constraint_serde.py` (добавить проверку загрузчика)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_constraint_serde.py`:

```python
def test_ifbench_loader_constraints_serializable():
    from fusionbench.tasks.ifbench import IFBenchLoader
    from fusionbench.grading.constraint import constraint_to_dict, constraint_from_dict
    examples = IFBenchLoader().load(limit=3)
    assert len(examples) == 3
    for ex in examples:
        for c in ex.reference:
            d = constraint_to_dict(c)             # must not raise (kind present)
            c2 = constraint_from_dict(d)
            assert c2.check("HELLO WORLD") == c.check("HELLO WORLD")
            assert c2.check("one two three") == c.check("one two three")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_constraint_serde.py::test_ifbench_loader_constraints_serializable -v`
Expected: FAIL — current `_TEMPLATES` build constraints whose `kind` is "" (raises ValueError in `constraint_to_dict`).

Actually it would fail because `ifbench.py` defines its OWN `_exactly_words` etc. without `kind`. We replace them with the registry.

- [ ] **Step 3: Write minimal implementation**

Replace `src/fusionbench/tasks/ifbench.py` entirely:

```python
from __future__ import annotations

from ..grading.constraint import make_constraint
from .base import Example

# Templates described as DATA so each constraint serializes to gold and round-trips.
# Each entry: (prompt, [(kind, params), ...]).
_TEMPLATES = [
    ("Reply with exactly three words mentioning a cat.",
     [("exactly_words", {"n": 3}), ("contains", {"word": "cat"})]),
    ("Answer in all capital letters.",
     [("all_caps", {})]),
    ("Write exactly five words and include the word ocean.",
     [("exactly_words", {"n": 5}), ("contains", {"word": "ocean"})]),
]


class IFBenchLoader:
    """Instruction-following fixture: each example carries verifiable Constraints as its
    reference (not a gold string), graded by ConstraintGrader. Constraints are built from
    registered kinds so they serialize to gold for CI re-grade."""

    type = "instruction"

    def load(self, limit: int, split: str = "test") -> list[Example]:
        out = []
        for i in range(limit):
            prompt, specs = _TEMPLATES[i % len(_TEMPLATES)]
            constraints = [make_constraint(kind, **params) for kind, params in specs]
            out.append(Example(id=f"ifbench-{i:04d}", prompt=prompt, reference=constraints, type=self.type))
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_constraint_serde.py -v`
Expected: PASS (all tests including loader)

- [ ] **Step 5: Verify registry + outputs tests still pass**

Run: `pytest tests/test_registry.py tests/test_grading.py tests/test_outputs.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/fusionbench/tasks/ifbench.py tests/test_constraint_serde.py
git commit -m "refactor: ifbench-шаблоны как данные через реестр предикатов"
```

---

## Task 3: Модуль gold.py — сериализация reference

**Files:**
- Create: `src/fusionbench/gold.py`
- Test: `tests/test_gold.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gold.py
import json

from fusionbench.gold import example_to_gold, gold_to_reference
from fusionbench.tasks.registry import REGISTRY


def _roundtrip_suite(suite):
    spec = REGISTRY[suite]
    examples = spec.loader.load(limit=3)
    for ex in examples:
        row = example_to_gold(ex)
        # row must be JSON-serializable
        json.dumps(row)
        assert row["id"] == ex.id
        assert row["type"] == ex.type
        reference, metadata = gold_to_reference(suite, row)
        # grading with the restored reference matches grading with the original
        for pred in ["NEEDLE-AAA", "HELLO WORLD", "one two three", "anything else"]:
            v1 = spec.grader.score(pred, ex.reference, ex.metadata)
            v2 = spec.grader.score(pred, reference, metadata)
            assert v1.passed == v2.passed, (suite, ex.id, pred)


def test_gold_roundtrip_ruler():
    _roundtrip_suite("ruler")


def test_gold_roundtrip_ifbench():
    _roundtrip_suite("ifbench")


def test_gold_roundtrip_frames_string_reference():
    # frames loader hits the network; build a synthetic string-reference Example instead.
    from fusionbench.tasks.base import Example
    from fusionbench.gold import example_to_gold, gold_to_reference
    ex = Example(id="frames-0001", prompt="q", reference="Paris",
                 type="multihop_qa", metadata={"aliases": ["paris, france"]})
    row = example_to_gold(ex)
    assert row["reference"] == "Paris"
    assert row["metadata"] == {"aliases": ["paris, france"]}
    reference, metadata = gold_to_reference("frames", row)
    assert reference == "Paris"
    assert metadata == {"aliases": ["paris, france"]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gold.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusionbench.gold'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fusionbench/gold.py
"""Serialize a loader's Example into the gold-file row CI re-grades against, and back.

This is the single boundary between Example/Constraint objects and the JSON gold file.
String-reference suites (frames, ruler) pass through; the instruction suite (ifbench)
carries a list of constraints whose predicates are lambdas — those round-trip through
the constraint registry, not raw JSON.
"""
from __future__ import annotations

from typing import Any

from .grading.constraint import Constraint, constraint_from_dict, constraint_to_dict
from .tasks.base import Example

# Suites whose grader reference is a list[Constraint] rather than a plain string.
_CONSTRAINT_SUITES = {"ifbench"}


def example_to_gold(ex: Example) -> dict[str, Any]:
    """Dump an Example to a JSON-serializable gold row: {id, type, reference, metadata}."""
    ref = ex.reference
    if isinstance(ref, list) and all(isinstance(c, Constraint) for c in ref):
        reference: Any = [constraint_to_dict(c) for c in ref]
    else:
        reference = ref
    return {
        "id": ex.id,
        "type": ex.type,
        "reference": reference,
        "metadata": dict(ex.metadata),
    }


def gold_to_reference(suite: str, row: dict) -> tuple[Any, dict]:
    """Rebuild (reference, metadata) for grader.score() from a gold row."""
    metadata = dict(row.get("metadata", {}))
    if suite in _CONSTRAINT_SUITES:
        reference: Any = [constraint_from_dict(d) for d in row["reference"]]
    else:
        reference = row["reference"]
    return reference, metadata
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gold.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/fusionbench/gold.py tests/test_gold.py
git commit -m "feat: gold.py — сериализация reference загрузчика в gold-файл и обратно"
```

---

## Task 4: Модуль crypto.py — Fernet-обёртка

**Files:**
- Modify: `pyproject.toml` (+ `cryptography`)
- Create: `src/fusionbench/crypto.py`
- Test: `tests/test_crypto.py`

- [ ] **Step 1: Add dependency**

Edit `pyproject.toml` dependencies list:

```toml
dependencies = [
    "httpx>=0.27",        # only used by the real OpenRouter client; mock mode needs nothing
    "python-dotenv>=1.0",
    "cryptography>=42.0", # Fernet encryption for the held-out gold file (Phase 2)
]
```

Then install:

Run: `pip install -e ".[dev]"`
Expected: installs `cryptography`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_crypto.py
import pytest

from fusionbench.crypto import encrypt_bytes, decrypt_bytes, generate_key


def test_roundtrip():
    key = generate_key()
    data = b'{"id": "ruler-0001", "reference": "NEEDLE-AAA"}\n'
    token = encrypt_bytes(data, key)
    assert token != data
    assert decrypt_bytes(token, key) == data


def test_wrong_key_fails():
    k1, k2 = generate_key(), generate_key()
    token = encrypt_bytes(b"secret", k1)
    with pytest.raises(Exception):
        decrypt_bytes(token, k2)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_crypto.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusionbench.crypto'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/fusionbench/crypto.py
"""Thin Fernet wrapper for the held-out gold file. Fernet = AES-128-CBC + HMAC, so a
tampered ciphertext fails to decrypt rather than silently returning garbage. The key
lives in the GOLD_DECRYPT_KEY GitHub secret; never commit it."""
from __future__ import annotations

from cryptography.fernet import Fernet


def generate_key() -> bytes:
    """Generate a new base64 Fernet key. Run once; store as GOLD_DECRYPT_KEY secret."""
    return Fernet.generate_key()


def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    return Fernet(key).encrypt(data)


def decrypt_bytes(token: bytes, key: bytes) -> bytes:
    """Raises cryptography.fernet.InvalidToken on wrong key or tampered ciphertext."""
    return Fernet(key).decrypt(token)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_crypto.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/fusionbench/crypto.py tests/test_crypto.py
git commit -m "feat: crypto.py — Fernet-обёртка для шифрования gold-файла"
```

---

## Task 5: scripts/dump_gold.py — построить gold из загрузчика

**Files:**
- Create: `scripts/dump_gold.py`

Мейнтейнерский инструмент (не CI): прогоняет загрузчик suite и пишет `gold/<suite>.jsonl` через `example_to_gold`. Тестируется через прогон, не юнит-тест (тонкая обёртка над уже покрытыми модулями).

- [ ] **Step 1: Write implementation**

```python
#!/usr/bin/env python3
"""Maintainer tool: dump a suite's gold references to gold/<suite>.jsonl.

    python scripts/dump_gold.py --suite ruler --limit 150

The output is the held-out answer key. Encrypt it with encrypt_gold.py before committing;
never commit the plaintext gold/<suite>.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fusionbench.gold import example_to_gold
from fusionbench.tasks.registry import REGISTRY


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True, choices=sorted(REGISTRY))
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--out", default=None, help="default: gold/<suite>.jsonl")
    args = ap.parse_args()

    spec = REGISTRY[args.suite]
    examples = spec.loader.load(args.limit)
    out = Path(args.out or f"gold/{args.suite}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(example_to_gold(ex), ensure_ascii=False) + "\n")
    print(f"wrote {len(examples)} gold rows -> {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test it**

Run: `python scripts/dump_gold.py --suite ruler --limit 5 --out /tmp/gold_ruler_smoke.jsonl`
Expected: `wrote 5 gold rows -> /tmp/gold_ruler_smoke.jsonl`

Run: `python -c "import json; [json.loads(l) for l in open('/tmp/gold_ruler_smoke.jsonl')]; print('valid jsonl')"`
Expected: `valid jsonl`

- [ ] **Step 3: Commit**

```bash
git add scripts/dump_gold.py
git commit -m "feat: dump_gold.py — построить gold-файл из загрузчика suite"
```

---

## Task 6: scripts/encrypt_gold.py + decrypt_gold.py

**Files:**
- Create: `scripts/encrypt_gold.py`
- Create: `scripts/decrypt_gold.py`

- [ ] **Step 1: Write encrypt_gold.py**

```python
#!/usr/bin/env python3
"""Maintainer tool: encrypt gold/<suite>.jsonl -> gold/<suite>.jsonl.enc with Fernet.

    GOLD_DECRYPT_KEY=<base64-key> python scripts/encrypt_gold.py --suite ruler

Run after dump_gold.py. Commit ONLY the .enc file. Generate a key once with:
    python -c "from fusionbench.crypto import generate_key; print(generate_key().decode())"
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fusionbench.crypto import encrypt_bytes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True)
    args = ap.parse_args()

    key = os.environ.get("GOLD_DECRYPT_KEY")
    if not key:
        sys.exit("GOLD_DECRYPT_KEY not set")

    src = Path(f"gold/{args.suite}.jsonl")
    if not src.exists():
        sys.exit(f"{src} not found (run dump_gold.py first)")
    dst = src.with_suffix(".jsonl.enc")
    dst.write_bytes(encrypt_bytes(src.read_bytes(), key.encode()))
    print(f"encrypted {src} -> {dst}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write decrypt_gold.py**

```python
#!/usr/bin/env python3
"""CI tool: decrypt gold/<suite>.jsonl.enc -> gold/<suite>.jsonl using GOLD_DECRYPT_KEY.

    GOLD_DECRYPT_KEY=<key> python scripts/decrypt_gold.py --suite ruler

Exits non-zero (loudly) if the key is missing or wrong — never proceeds without gold.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fusionbench.crypto import decrypt_bytes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True)
    args = ap.parse_args()

    key = os.environ.get("GOLD_DECRYPT_KEY")
    if not key:
        sys.exit("GOLD_DECRYPT_KEY not set — cannot decrypt gold")

    enc = Path(f"gold/{args.suite}.jsonl.enc")
    if not enc.exists():
        sys.exit(f"{enc} not found")
    out = enc.with_suffix("")  # drops .enc -> gold/<suite>.jsonl
    try:
        out.write_bytes(decrypt_bytes(enc.read_bytes(), key.encode()))
    except Exception as e:
        sys.exit(f"decrypt failed (wrong key or tampered file): {e}")
    print(f"decrypted {enc} -> {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Round-trip smoke test**

```bash
KEY=$(python -c "from fusionbench.crypto import generate_key; print(generate_key().decode())")
python scripts/dump_gold.py --suite ruler --limit 5
GOLD_DECRYPT_KEY=$KEY python scripts/encrypt_gold.py --suite ruler
rm gold/ruler.jsonl
GOLD_DECRYPT_KEY=$KEY python scripts/decrypt_gold.py --suite ruler
python -c "import json; rows=[json.loads(l) for l in open('gold/ruler.jsonl')]; assert len(rows)==5; print('roundtrip ok', len(rows))"
```
Expected: ends with `roundtrip ok 5`

Then clean up the plaintext/enc smoke artifacts (real gold is committed separately):
```bash
rm -f gold/ruler.jsonl gold/ruler.jsonl.enc
```

- [ ] **Step 4: Commit**

```bash
git add scripts/encrypt_gold.py scripts/decrypt_gold.py
git commit -m "feat: encrypt_gold/decrypt_gold — Fernet шифрование gold для CI"
```

---

## Task 7: Фикстуры приёмки из mock-прогона

**Files:**
- Create: `tests/fixtures/regrade/gold_ruler.jsonl`
- Create: `tests/fixtures/regrade/outputs_honest.jsonl`
- Create: `tests/fixtures/regrade/outputs_tampered.jsonl` (= honest, манифест врёт)
- Create: `tests/fixtures/regrade/manifest_honest.json`
- Create: `tests/fixtures/regrade/manifest_tampered.json`

Фикстуры — статичные файлы в репо. Генерируем из детерминированного mock-прогона, затем редактируем манифесты под сценарии.

- [ ] **Step 1: Generate raw outputs + gold from mock run**

```bash
mkdir -p tests/fixtures/regrade
python scripts/run_v0.py --mock --suite ruler --limit 12 \
    --out /tmp/cat_fix.jsonl --outputs /tmp/outputs_fix.jsonl
python scripts/dump_gold.py --suite ruler --limit 12 --out tests/fixtures/regrade/gold_ruler.jsonl
```

- [ ] **Step 2: Keep only one recipe's outputs as the honest submission**

The runner writes every recipe. A submission claims ONE recipe. Filter to `fusion-strong`:

```bash
python -c "
import json
rows = [json.loads(l) for l in open('/tmp/outputs_fix.jsonl')]
keep = [r for r in rows if r['recipe'] == 'fusion-strong']
with open('tests/fixtures/regrade/outputs_honest.jsonl','w') as f:
    for r in keep: f.write(json.dumps(r, ensure_ascii=False)+'\n')
# tampered submission ships the SAME outputs (cannot fake the graded reference)
with open('tests/fixtures/regrade/outputs_tampered.jsonl','w') as f:
    for r in keep: f.write(json.dumps(r, ensure_ascii=False)+'\n')
acc = sum(r['claimed_correct'] for r in keep)/len(keep)
cost = sum(r['cost_usd'] for r in keep)
print('n', len(keep), 'real_acc', round(acc,4), 'total_cost', round(cost,6))
"
```
Note the printed `n`, `real_acc`, `total_cost` — they fill the manifests below.

- [ ] **Step 3: Write manifest_honest.json**

Use the real values from Step 2. Example (substitute actual numbers):

```json
{
  "schema_version": 1,
  "run_id": "ruler_mock_12",
  "submitted_by": "fixture",
  "suite": "ruler",
  "grader": "Synthetic@1",
  "client_commit": "fixture",
  "claimed": {
    "recipe": "fusion-strong",
    "accuracy": <real_acc from step 2>,
    "cost_usd": <total_cost / n from step 2>,
    "n": <n from step 2>
  }
}
```

- [ ] **Step 4: Write manifest_tampered.json**

Identical, but `accuracy` inflated well beyond tolerance (e.g. real 0.58 → claim 0.95):

```json
{
  "schema_version": 1,
  "run_id": "ruler_mock_12",
  "submitted_by": "fixture",
  "suite": "ruler",
  "grader": "Synthetic@1",
  "client_commit": "fixture",
  "claimed": {
    "recipe": "fusion-strong",
    "accuracy": 0.95,
    "cost_usd": <same cost_usd as honest>,
    "n": <same n>
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/regrade/
git commit -m "test: фикстуры приёмки ре-грейда (honest/tampered из mock-прогона)"
```

---

## Task 8: scripts/regrade.py — ядро целостности

**Files:**
- Create: `scripts/regrade.py`
- Test: `tests/test_regrade.py`

Ре-грейд читает манифест + outputs + gold, пересчитывает accuracy через `REGISTRY[suite].grader`, сравнивает с заявленной. accuracy расходится → `sys.exit(1)` (НЕ assert). cost — суммирует сохранённый `cost_usd` из outputs (прайс-лист мог дрейфовать), сверяет с заявленным и проверяет плаузибилити → только WARN.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_regrade.py
import subprocess
import sys
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "regrade"
SCRIPT = Path(__file__).parent.parent / "scripts" / "regrade.py"


def _run(manifest, outputs):
    return subprocess.run(
        [sys.executable, str(SCRIPT),
         "--manifest", str(FIX / manifest),
         "--outputs", str(FIX / outputs),
         "--gold", str(FIX / "gold_ruler.jsonl")],
        capture_output=True, text=True,
    )


def test_honest_submission_passes():
    r = _run("manifest_honest.json", "outputs_honest.jsonl")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_tampered_accuracy_fails():
    r = _run("manifest_tampered.json", "outputs_tampered.jsonl")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "accuracy" in (r.stdout + r.stderr).lower()


def test_cost_anomaly_is_warning_not_failure(tmp_path):
    # honest outputs, but manifest claims an absurdly low cost -> WARN, still exit 0
    import json
    man = json.loads((FIX / "manifest_honest.json").read_text())
    man["claimed"]["cost_usd"] = man["claimed"]["cost_usd"] / 100.0
    p = tmp_path / "manifest_low_cost.json"
    p.write_text(json.dumps(man))
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--manifest", str(p),
         "--outputs", str(FIX / "outputs_honest.jsonl"),
         "--gold", str(FIX / "gold_ruler.jsonl")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "WARN" in (r.stdout + r.stderr)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_regrade.py -v`
Expected: FAIL — `scripts/regrade.py` does not exist (FileNotFoundError / non-zero).

- [ ] **Step 3: Write implementation**

```python
#!/usr/bin/env python3
"""Re-grade a submission: recompute accuracy from saved outputs against held-out gold.

    python scripts/regrade.py --manifest <m.json> --outputs <o.jsonl> --gold <g.jsonl>

Accuracy mismatch is a HARD failure (exit 1) — this is the anti-cheat core. Cost is a
soft plausibility check (WARN, exit 0): model prices drift, so a hard cost gate would
red-flag honest submissions. Uses sys.exit, never assert (assert is stripped by python -O).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fusionbench.gold import gold_to_reference
from fusionbench.tasks.registry import REGISTRY

ACCURACY_TOL = 0.01
COST_WARN_TOL = 0.15


def _load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--outputs", required=True)
    ap.add_argument("--gold", required=True)
    args = ap.parse_args()

    man = json.loads(Path(args.manifest).read_text())
    claimed = man["claimed"]
    suite = man["suite"]

    spec = REGISTRY.get(suite)
    if spec is None:
        sys.exit(f"unknown suite {suite!r} (not in REGISTRY)")
    if man.get("grader") and man["grader"] != spec.grader.name:
        sys.exit(f"grader mismatch: manifest {man['grader']!r} vs registry {spec.grader.name!r}")

    gold = {row["id"]: row for row in _load_jsonl(args.gold)}
    outputs = [r for r in _load_jsonl(args.outputs) if r.get("recipe") == claimed["recipe"]]
    if not outputs:
        sys.exit(f"no outputs for claimed recipe {claimed['recipe']!r}")

    n = ok = 0
    recomputed_cost = 0.0
    for r in outputs:
        gid = r["gold_id"]
        if gid not in gold:
            sys.exit(f"gold_id {gid!r} from outputs not found in gold file")
        reference, metadata = gold_to_reference(suite, gold[gid])
        v = spec.grader.score(r["prediction"], reference, metadata)
        ok += int(v.passed)
        n += 1
        recomputed_cost += float(r.get("cost_usd", 0.0))

    if n != claimed["n"]:
        sys.exit(f"n mismatch: manifest says {claimed['n']}, found {n} outputs")

    acc = ok / n
    # HARD: accuracy must match within tolerance
    if abs(acc - claimed["accuracy"]) > ACCURACY_TOL:
        sys.exit(f"FAIL accuracy mismatch: re-graded {acc:.4f} vs claimed "
                 f"{claimed['accuracy']:.4f} (tol {ACCURACY_TOL})")

    # SOFT: cost plausibility (WARN only)
    claimed_total = claimed["cost_usd"] * n
    if claimed_total <= 0 and recomputed_cost > 0:
        print(f"WARN cost: claimed total ${claimed_total:.4f} but outputs sum to "
              f"${recomputed_cost:.4f} (implausibly low)")
    elif recomputed_cost > 0:
        rel = abs(recomputed_cost - claimed_total) / recomputed_cost
        if rel > COST_WARN_TOL:
            print(f"WARN cost: re-summed ${recomputed_cost:.4f} vs claimed "
                  f"${claimed_total:.4f} (off by {rel*100:.0f}%)")

    print(f"OK re-graded acc={acc:.4f} (claimed {claimed['accuracy']:.4f}), "
          f"cost=${recomputed_cost:.4f}, n={n}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_regrade.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Manual acceptance check (the Phase-2 criteria)**

```bash
python scripts/regrade.py --manifest tests/fixtures/regrade/manifest_honest.json \
    --outputs tests/fixtures/regrade/outputs_honest.jsonl --gold tests/fixtures/regrade/gold_ruler.jsonl; echo "exit=$?"
python scripts/regrade.py --manifest tests/fixtures/regrade/manifest_tampered.json \
    --outputs tests/fixtures/regrade/outputs_tampered.jsonl --gold tests/fixtures/regrade/gold_ruler.jsonl; echo "exit=$?"
```
Expected: first prints `OK ...` / `exit=0`; second prints `FAIL accuracy mismatch ...` / `exit=1`.

- [ ] **Step 6: Commit**

```bash
git add scripts/regrade.py tests/test_regrade.py
git commit -m "feat: regrade.py — пересчёт accuracy против gold, подлог падает (HARD)"
```

---

## Task 9: scripts/validate_manifest.py

**Files:**
- Create: `scripts/validate_manifest.py`
- Test: `tests/test_regrade.py` (добавить)

Проверяет структуру манифеста (обязательные поля, типы). Плаузибилити cost — WARN. Структурная невалидность — exit 1.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_regrade.py`:

```python
def test_validate_manifest_accepts_honest():
    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "scripts" / "validate_manifest.py"),
         str(FIX / "manifest_honest.json")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_validate_manifest_rejects_missing_field(tmp_path):
    import json
    bad = {"schema_version": 1, "suite": "ruler"}  # no "claimed"
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "scripts" / "validate_manifest.py"), str(p)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_regrade.py::test_validate_manifest_accepts_honest -v`
Expected: FAIL — script missing.

- [ ] **Step 3: Write implementation**

```python
#!/usr/bin/env python3
"""Validate a submission manifest: required fields, types, and cost plausibility (WARN).

    python scripts/validate_manifest.py submissions/<user>/<run_id>/manifest.json

Structural problems (missing/wrong-typed fields, unknown suite) -> exit 1.
Cost implausibility -> WARN, exit 0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fusionbench.tasks.registry import REGISTRY

_REQUIRED = ["schema_version", "run_id", "submitted_by", "suite", "claimed"]
_CLAIMED_REQUIRED = {"recipe": str, "accuracy": (int, float), "cost_usd": (int, float), "n": int}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    args = ap.parse_args()

    try:
        man = json.loads(Path(args.manifest).read_text())
    except Exception as e:
        sys.exit(f"cannot parse manifest: {e}")

    for key in _REQUIRED:
        if key not in man:
            sys.exit(f"manifest missing required field {key!r}")

    if man["suite"] not in REGISTRY:
        sys.exit(f"unknown suite {man['suite']!r} (not in REGISTRY)")

    claimed = man["claimed"]
    for key, typ in _CLAIMED_REQUIRED.items():
        if key not in claimed:
            sys.exit(f"manifest.claimed missing {key!r}")
        if not isinstance(claimed[key], typ):
            sys.exit(f"manifest.claimed.{key} must be {typ}, got {type(claimed[key]).__name__}")

    if not (0.0 <= claimed["accuracy"] <= 1.0):
        sys.exit(f"accuracy out of range: {claimed['accuracy']}")
    if claimed["n"] <= 0:
        sys.exit(f"n must be positive: {claimed['n']}")

    # cost plausibility — WARN only
    if claimed["cost_usd"] < 0:
        print(f"WARN cost: negative cost_usd {claimed['cost_usd']}")
    elif claimed["cost_usd"] == 0:
        print("WARN cost: claimed cost_usd is 0 (implausible for a real run)")

    print(f"OK manifest valid: suite={man['suite']} recipe={claimed['recipe']} n={claimed['n']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_regrade.py -v`
Expected: PASS (all regrade + validate tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_manifest.py tests/test_regrade.py
git commit -m "feat: validate_manifest.py — схема манифеста + cost-плаузибилити (WARN)"
```

---

## Task 10: CI workflow submit.yml

**Files:**
- Create: `.github/workflows/submit.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: Validate submission

on:
  pull_request:
    paths:
      - "submissions/**"

jobs:
  regrade:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - name: Re-grade changed submissions against held-out gold
        env:
          GOLD_DECRYPT_KEY: ${{ secrets.GOLD_DECRYPT_KEY }}
        run: |
          set -euo pipefail
          # Find submission dirs touched by this PR.
          git fetch origin "${{ github.base_ref }}" --depth=1
          changed=$(git diff --name-only "origin/${{ github.base_ref }}"...HEAD -- 'submissions/**' \
            | sed -E 's#(submissions/[^/]+/[^/]+)/.*#\1#' | sort -u)
          if [ -z "$changed" ]; then echo "no submission dirs changed"; exit 0; fi
          for dir in $changed; do
            echo "::group::$dir"
            suite=$(python -c "import json,sys; print(json.load(open('$dir/manifest.json'))['suite'])")
            python scripts/decrypt_gold.py --suite "$suite"
            python scripts/validate_manifest.py "$dir/manifest.json"
            python scripts/regrade.py \
              --manifest "$dir/manifest.json" \
              --outputs "$dir/outputs.jsonl" \
              --gold "gold/$suite.jsonl"
            echo "::endgroup::"
          done
```

- [ ] **Step 2: Lint the YAML locally (if available)**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/submit.yml')); print('yaml ok')"`
Expected: `yaml ok` (if PyYAML present; otherwise skip — GitHub validates on push)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/submit.yml
git commit -m "ci: submit.yml — decrypt→validate→regrade на изменённых сабмишнах"
```

---

## Task 11: README submissions + .gitignore для plaintext gold

**Files:**
- Create: `submissions/README.md`
- Modify: `.gitignore`
- Modify: `README.md` (краткая ссылка на сабмишн-флоу)

- [ ] **Step 1: gitignore plaintext gold (commit only .enc)**

Append to `.gitignore` (create if absent):

```gitignore
# Plaintext gold answer keys — only the .enc form is committed.
gold/*.jsonl
!gold/.gitkeep
```

- [ ] **Step 2: submissions/README.md**

```markdown
# Submissions

Each submission is a directory `submissions/<github_user>/<run_id>/` with:

- `manifest.json` — claimed recipe, accuracy, cost_usd, n, suite, grader.
- `outputs.jsonl` — raw per-(task × recipe) outputs from your run.

On PR, `.github/workflows/submit.yml` re-grades your saved outputs against the
held-out gold answer key and **fails if the claimed accuracy does not match** the
re-graded value (tolerance ±1%). Cost is checked for plausibility (warning only).

Generate outputs with `scripts/run_v0.py` (writes `runs/outputs.jsonl`), then copy the
single recipe you're claiming into your submission directory along with a manifest.
```

- [ ] **Step 3: Add gold/.gitkeep**

```bash
mkdir -p gold && touch gold/.gitkeep
```

- [ ] **Step 4: Link from main README**

Add a short line under the existing content of `README.md` (find the contributions / how-to section):

```markdown
## Submitting a run

See [submissions/README.md](submissions/README.md). CI re-grades your saved
`outputs.jsonl` against a private gold key; an inflated accuracy fails the check.
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore submissions/README.md gold/.gitkeep README.md
git commit -m "docs: сабмишн-флоу + gitignore plaintext gold"
```

---

## Final verification (before declaring Phase 2 done)

- [ ] **Full test suite green**

Run: `pytest -q`
Expected: all tests pass (existing + new: constraint_serde, gold, crypto, regrade).

- [ ] **Acceptance criteria — re-verify the three from the spec**

```bash
# 1. honest passes
python scripts/regrade.py --manifest tests/fixtures/regrade/manifest_honest.json \
  --outputs tests/fixtures/regrade/outputs_honest.jsonl --gold tests/fixtures/regrade/gold_ruler.jsonl; echo "exit=$?"
# 2. tampered (inflated accuracy) fails
python scripts/regrade.py --manifest tests/fixtures/regrade/manifest_tampered.json \
  --outputs tests/fixtures/regrade/outputs_tampered.jsonl --gold tests/fixtures/regrade/gold_ruler.jsonl; echo "exit=$?"
```
Expected: (1) `OK ...` exit=0; (2) `FAIL accuracy mismatch` exit=1.

- [ ] **ruff (only if installed globally)**

Run: `ruff check src/fusionbench scripts 2>/dev/null || echo "ruff not installed — skipped"`

- [ ] **Operational note for the user (NOT a code step)**

Before the CI actually protects submissions, the user must:
1. Generate a key: `python -c "from fusionbench.crypto import generate_key; print(generate_key().decode())"`
2. Add it to GitHub repo secrets as `GOLD_DECRYPT_KEY`.
3. Build + encrypt real gold: `python scripts/dump_gold.py --suite ruler` → `GOLD_DECRYPT_KEY=<key> python scripts/encrypt_gold.py --suite ruler` → commit `gold/ruler.jsonl.enc`.

All code and the test suite work locally without the secret.

---

