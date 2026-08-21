"""Portable exports for task results; does not expose device-write operations."""
from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Iterable


SAMPLE_COLUMNS = ("minute", "bandwidth", "iops", "latency", "temperature")


def samples_csv(samples: Iterable[dict]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=SAMPLE_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for sample in samples:
        writer.writerow({column: sample.get(column, "") for column in SAMPLE_COLUMNS})
    return output.getvalue()


def task_json(task: dict) -> str:
    """Create stable UTF-8 JSON suitable for a report archive."""
    return json.dumps(task, ensure_ascii=False, indent=2, sort_keys=True, default=str)
