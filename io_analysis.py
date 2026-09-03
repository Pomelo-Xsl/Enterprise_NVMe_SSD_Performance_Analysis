"""Compute the IO breakdown used on analysis and report pages.

Inputs may be :class:`models.IOSample` instances or normalized dictionaries
from the FIO adapter. Results include tail-latency percentiles, read/write mix,
block-size distribution and time-bucketed bandwidth rather than a single
average that could hide short stalls.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Iterable

from analysis import describe, percentile
from models import IOSample


def _value(sample: IOSample | dict, name: str, default=0):
    if isinstance(sample, IOSample):
        return getattr(sample, name, default)
    return sample.get(name, default)


def _operation(sample: IOSample | dict) -> str:
    operation = str(_value(sample, "operation", "read")).lower()
    return "read" if operation.startswith("r") else "write"


def _latency(sample: IOSample | dict) -> float:
    return float(
        _value(
            sample,
            "latency_us",
            _value(sample, "latency", 0),
        )
    )


def latency_distribution(samples: Iterable[IOSample | dict]) -> dict:
    values = [_latency(sample) for sample in samples]
    stats = describe(values)
    return {
        "count": stats.count,
        "minimum_us": stats.minimum,
        "maximum_us": stats.maximum,
        "average_us": stats.average,
        "stddev_us": stats.stddev,
        "p50_us": percentile(values, 50),
        "p95_us": percentile(values, 95),
        "p99_us": percentile(values, 99),
        "p999_us": percentile(values, 99.9),
        "p9999_us": percentile(values, 99.99),
    }


def direction_breakdown(samples: Iterable[IOSample | dict]) -> dict:
    groups: dict[str, list[IOSample | dict]] = defaultdict(list)
    materialized = list(samples)
    for sample in materialized:
        groups[_operation(sample)].append(sample)

    total = len(materialized)
    result = {}
    for operation in ("read", "write"):
        operation_samples = groups.get(operation, [])
        latencies = [_latency(sample) for sample in operation_samples]
        byte_count = sum(
            int(_value(sample, "size_bytes", 0)) for sample in operation_samples
        )
        result[operation] = {
            "operation": operation,
            "operations": len(operation_samples),
            "bytes": byte_count,
            "ratio": len(operation_samples) / total if total else 0.0,
            "average_latency_us": mean(latencies) if latencies else 0.0,
            "p50_latency_us": percentile(latencies, 50),
            "p95_latency_us": percentile(latencies, 95),
            "p99_latency_us": percentile(latencies, 99),
            "p999_latency_us": percentile(latencies, 99.9),
        }
    return result


def block_size_breakdown(samples: Iterable[IOSample | dict]) -> dict:
    groups: dict[int, list[IOSample | dict]] = defaultdict(list)
    for sample in samples:
        groups[int(_value(sample, "size_bytes", 0))].append(sample)

    result = {}
    for block_size, block_samples in sorted(groups.items()):
        latencies = [_latency(sample) for sample in block_samples]
        operations = len(block_samples)
        result[str(block_size)] = {
            "block_size_bytes": block_size,
            "operations": operations,
            "bytes": block_size * operations,
            "read_operations": sum(
                _operation(sample) == "read" for sample in block_samples
            ),
            "write_operations": sum(
                _operation(sample) == "write" for sample in block_samples
            ),
            "average_latency_us": mean(latencies) if latencies else 0.0,
            "p99_latency_us": percentile(latencies, 99),
        }
    return result


def time_windows(
    samples: Iterable[IOSample | dict],
    window_ms: int = 1000,
) -> list[dict]:
    if window_ms <= 0:
        raise ValueError("window_ms must be positive")

    groups: dict[int, list[IOSample | dict]] = defaultdict(list)
    for sample in samples:
        timestamp = int(_value(sample, "timestamp_ms", 0))
        groups[timestamp // window_ms].append(sample)

    windows = []
    for bucket, bucket_samples in sorted(groups.items()):
        byte_count = sum(
            int(_value(sample, "size_bytes", 0)) for sample in bucket_samples
        )
        duration_seconds = window_ms / 1000
        latencies = [_latency(sample) for sample in bucket_samples]
        windows.append(
            {
                "start_ms": bucket * window_ms,
                "end_ms": (bucket + 1) * window_ms,
                "operations": len(bucket_samples),
                "iops": len(bucket_samples) / duration_seconds,
                "bytes": byte_count,
                "bandwidth_bytes_per_second": byte_count / duration_seconds,
                "average_latency_us": mean(latencies) if latencies else 0.0,
                "p99_latency_us": percentile(latencies, 99),
                "reads": sum(_operation(sample) == "read" for sample in bucket_samples),
                "writes": sum(
                    _operation(sample) == "write" for sample in bucket_samples
                ),
            }
        )
    return windows


def queue_depth_distribution(samples: Iterable[IOSample | dict]) -> dict:
    depths = Counter(int(_value(sample, "queue_depth", 1)) for sample in samples)
    total = sum(depths.values())
    return {
        str(depth): {
            "operations": count,
            "ratio": count / total if total else 0.0,
        }
        for depth, count in sorted(depths.items())
    }


def analyze_io(
    samples: Iterable[IOSample | dict],
    window_ms: int = 1000,
) -> dict:
    materialized = list(samples)
    total_bytes = sum(int(_value(sample, "size_bytes", 0)) for sample in materialized)
    unique_lbas = len({_value(sample, "lba", None) for sample in materialized})
    return {
        "sample_count": len(materialized),
        "total_bytes": total_bytes,
        "unique_lbas": unique_lbas,
        "latency": latency_distribution(materialized),
        "directions": direction_breakdown(materialized),
        "block_sizes": block_size_breakdown(materialized),
        "queue_depths": queue_depth_distribution(materialized),
        "time_windows": time_windows(materialized, window_ms),
    }
