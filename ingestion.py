"""Adapters for results produced by SSD Benchmark, PressureTest and FIO."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from alerts import evaluate_result, summary
from analysis import analyse
from anomaly import detect_anomalies
from cache_metrics import compare_results
from cache_simulator import compare_algorithms
from fio_parser import parse_fio_json
from hot_cold import classify_workload
from io_analysis import analyze_io
from models import IOSample
from workloads import to_points


def _configuration(name: str, source: str, sample_count: int) -> dict:
    """Build repository metadata without pretending an imported run was executed here."""
    return {
        "scenario": {
            "name": name,
            "profile": "external-analysis",
            "runtime": 0,
            "cache_pages": 0,
            "safe_simulation": True,
            "tags": ["imported", source],
        },
        "workload": {
            "kind": source,
            "count": sample_count,
            "page_count": 0,
            "read_ratio": 0,
            "block_size": 0,
            "seed": 0,
        },
        "cache": {
            "algorithm": "analysis-only",
            "capacity_pages": 0,
        },
        "alerts": {},
    }


def _base_report(name: str, source: str, sample_count: int) -> dict:
    return {
        "schema_version": "1.0",
        "mode": "imported-analysis",
        "source_format": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": _configuration(name, source, sample_count),
        "sample_count": sample_count,
    }


def _alerts_for(report: dict) -> dict:
    events = evaluate_result(
        {
            "smart": report.get("smart", {}),
            "analysis": report.get("performance", {}),
            "anomalies": report.get("anomalies", []),
        }
    )
    return {
        "summary": summary(events),
        "events": [event.to_dict() for event in events],
    }


def _ingest_samples(payload: dict, name: str, cache_pages: int) -> dict:
    samples = [IOSample.from_dict(item) for item in payload["samples"]]
    if not samples:
        raise ValueError("samples must contain at least one IO record")

    unique_pages = len({sample.lba for sample in samples})
    effective_capacity = min(max(1, cache_pages), max(1, unique_pages))
    cache_results = compare_algorithms(samples, effective_capacity)
    points = to_points(samples)

    report = _base_report(name, "normalized-io", len(samples))
    report.update(
        {
            "samples": [sample.to_dict() for sample in samples],
            "points": points,
            "io_statistics": analyze_io(samples),
            "page_heat": classify_workload(samples),
            "cache_results": cache_results,
            "cache_comparison": compare_results(cache_results),
            "performance": analyse(points),
            "anomalies": detect_anomalies(points),
            "smart": payload.get("smart", {}),
        }
    )
    report["configuration"]["cache"].update(
        {
            "algorithm": "compare",
            "capacity_pages": effective_capacity,
        }
    )
    report["alerts"] = _alerts_for(report)
    return report


def _ingest_points(payload: dict, name: str) -> dict:
    points = payload["points"]
    if not isinstance(points, list) or not points:
        raise ValueError("points must contain at least one performance record")

    performance = analyse(points)
    report = _base_report(name, "performance-points", len(points))
    report.update(
        {
            "points": points,
            "performance": performance,
            "anomalies": detect_anomalies(points),
            "smart": payload.get("smart", {}),
            "summary": payload.get("summary", {}),
        }
    )
    report["alerts"] = _alerts_for(report)
    return report


def _ingest_fio(payload: dict, name: str) -> dict:
    fio_result = parse_fio_json(payload)
    total_operations = int(
        sum(
            direction["total_ios"]
            for job in fio_result["jobs"]
            for direction in (job["read"], job["write"], job["trim"])
        )
    )
    if not total_operations:
        total_operations = int(
            sum(
                job[direction]["io_bytes"] > 0
                for job in fio_result["jobs"]
                for direction in ("read", "write", "trim")
            )
        )

    report = _base_report(name, "fio-json", total_operations)
    report.update(
        {
            "fio": fio_result,
            "io_statistics": fio_result["aggregate"],
            "performance": {},
            "anomalies": [],
            "alerts": {
                "summary": {
                    "total": 0,
                    "critical": 0,
                    "warning": 0,
                    "healthy": True,
                },
                "events": [],
            },
        }
    )
    return report


def ingest_result(
    payload: dict,
    name: str = "imported-result",
    cache_pages: int = 128,
) -> dict:
    """Normalize a supported external result into the common report schema."""
    if not isinstance(payload, dict):
        raise ValueError("import payload must be a JSON object")

    source = payload.get("result", payload)
    if not isinstance(source, dict):
        raise ValueError("result must be a JSON object")
    if "jobs" in source:
        return _ingest_fio(source, name)
    if "samples" in source:
        return _ingest_samples(source, name, cache_pages)
    if "points" in source:
        return _ingest_points(source, name)
    raise ValueError("unsupported result: expected jobs, samples, or points")
