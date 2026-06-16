"""Serialize the currently-filtered catalog slice to CSV / JSON bytes."""
from __future__ import annotations

import csv
import io
import json


def rows_to_csv_bytes(rows):
    """CSV bytes with header from the first row's keys. Empty input -> b''."""
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def rows_to_json_bytes(rows):
    """Pretty JSON bytes of the row dicts."""
    return (json.dumps(rows, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
