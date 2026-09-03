"""Serialize completed analyses into files people can reuse elsewhere.

CSV variants are intentionally flat for spreadsheet and plotting tools, while
the JSON export keeps the nested report structure. Exporting never re-runs a
workload or touches the source device.
"""

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


def _flatten(prefix: str, value, output: dict) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            _flatten(child_prefix, child, output)
    elif isinstance(value, list):
        output[prefix] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        output[prefix] = value


def flatten_mapping(data: dict) -> dict:
    output = {}
    _flatten("", data, output)
    return output


def report_summary_csv(report: dict) -> str:
    """Export nested report metadata as key/value CSV rows."""

    flattened = flatten_mapping(
        {
            key: value
            for key, value in report.items()
            if key not in {"samples", "points"}
        }
    )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(("metric", "value"))
    for key, value in sorted(flattened.items()):
        writer.writerow((key, value))
    return output.getvalue()


def io_samples_csv(samples: Iterable[dict]) -> str:
    """Export normalized IO samples with workload-oriented columns."""

    columns = (
        "timestamp_ms",
        "lba",
        "size_bytes",
        "operation",
        "latency_us",
        "queue_depth",
    )
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for sample in samples:
        writer.writerow({column: sample.get(column, "") for column in columns})
    return output.getvalue()


def cache_comparison_csv(comparison: dict) -> str:
    """Export one row per cache algorithm for spreadsheet comparison."""

    algorithms = comparison.get("algorithms", comparison)
    fields = (
        "algorithm",
        "accesses",
        "hits",
        "misses",
        "hit_ratio",
        "hot_hits",
        "cold_hits",
        "evictions",
        "dirty_evictions",
        "clean_evictions",
        "dirty_eviction_ratio",
        "resident_pages",
        "dirty_pages",
    )
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for name, metrics in sorted(algorithms.items()):
        writer.writerow({"algorithm": name, **metrics})
    return output.getvalue()


def report_json(report: dict) -> str:
    return json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    )
