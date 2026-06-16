import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from webui import export as ex  # noqa: E402


def _rows():
    return [
        {"type": "code", "recipe": "best-single", "accuracy": 0.90, "cost_usd": 0.001},
        {"type": "math", "recipe": "fusion-strong", "accuracy": 0.70, "cost_usd": 0.004},
    ]


def test_csv_has_header_and_rows():
    data = ex.rows_to_csv_bytes(_rows())
    text = data.decode("utf-8")
    reader = list(csv.reader(io.StringIO(text)))
    assert reader[0] == ["type", "recipe", "accuracy", "cost_usd"]
    assert len(reader) == 3  # header + 2 rows


def test_csv_empty_rows_is_empty_string():
    assert ex.rows_to_csv_bytes([]) == b""


def test_json_round_trip():
    data = ex.rows_to_json_bytes(_rows())
    assert json.loads(data.decode("utf-8")) == _rows()
