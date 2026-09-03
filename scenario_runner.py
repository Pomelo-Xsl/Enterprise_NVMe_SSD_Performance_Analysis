"""Execute an in-memory analysis scenario assembled from validated settings.

Despite the historical “scenario” name, this runner does not send IO to a disk.
It generates or consumes samples, evaluates page heat and cache policies, then
returns one report-shaped result with alerts and supporting statistics.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from alerts import evaluate_performance, summary
from analysis import detect_anomalies
from cache_metrics import compare_results
from cache_simulator import ARCCache, LIRSCache, LRU2Cache, compare_algorithms
from config import ApplicationConfiguration
from hot_cold import HotColdClassifier
from io_analysis import analyze_io
from workloads import hot_cold_alternating, mixed_io, random_io, sequential


ALGORITHMS = {
    "lru2": LRU2Cache,
    "arc": ARCCache,
    "lirs": LIRSCache,
}


def build_workload(configuration: ApplicationConfiguration):
    workload = configuration.workload
    if workload.kind == "sequential":
        return sequential(
            workload.count,
            block_size=workload.block_size,
            write_ratio=1 - workload.read_ratio,
        )
    if workload.kind == "random":
        return random_io(
            workload.count,
            workload.page_count,
            seed=workload.seed,
            read_ratio=workload.read_ratio,
            block_size=workload.block_size,
        )
    if workload.kind == "mixed":
        return mixed_io(
            workload.count,
            workload.page_count,
            seed=workload.seed,
        )
    rounds = max(1, (workload.count + 19) // 20)
    return hot_cold_alternating(
        rounds,
        hot_pages=max(1, min(32, workload.page_count // 8)),
        cold_pages=max(1, workload.page_count),
        seed=workload.seed,
    )[: workload.count]


def _heat_analysis(samples, configuration: ApplicationConfiguration) -> dict:
    cache = configuration.cache
    classifier = HotColdClassifier(
        window_ms=cache.hot_window_ms,
        hot_threshold=cache.hot_threshold,
        cold_threshold=cache.cold_threshold,
        read_weight=cache.read_weight,
        write_weight=cache.write_weight,
    )
    for sample in samples:
        classifier.observe(sample)
    return classifier.summary(samples[-1].timestamp_ms if samples else 0)


def _run_caches(samples, configuration: ApplicationConfiguration) -> dict:
    cache = configuration.cache
    if cache.algorithm == "compare":
        return compare_algorithms(samples, cache.capacity_pages)
    cache_class = ALGORITHMS[cache.algorithm]
    simulator = cache_class(
        cache.capacity_pages,
        hot_window_ms=cache.hot_window_ms,
    )
    return {cache.algorithm: simulator.run(samples)}


def run_configured_scenario(configuration: ApplicationConfiguration) -> dict:
    samples = build_workload(configuration)
    cache_results = _run_caches(samples, configuration)
    io_statistics = analyze_io(samples)

    performance_points = [
        {
            "timestamp_ms": sample.timestamp_ms,
            "bandwidth": sample.size_bytes * 1_000_000 / max(sample.latency_us, 1),
            "iops": 1_000_000 / max(sample.latency_us, 1),
            "latency": sample.latency_us,
            "temperature": 40 + min(35, sample.queue_depth * 0.4),
        }
        for sample in samples
    ]
    anomalies = detect_anomalies(
        performance_points,
        bandwidth_drop=configuration.alerts.bandwidth_drop_percent,
        latency_spike=configuration.alerts.latency_spike_zscore,
    )
    performance_analysis = {
        "bandwidth": {
            "variation_percent": (
                (
                    max(point["bandwidth"] for point in performance_points)
                    - min(point["bandwidth"] for point in performance_points)
                )
                / (
                    sum(point["bandwidth"] for point in performance_points)
                    / len(performance_points)
                )
                * 100
                if performance_points
                else 0
            )
        },
        "trend": {"direction": "flat"},
    }
    alerts = evaluate_performance(
        performance_analysis,
        anomalies,
        configuration.alerts,
    )
    return {
        "schema_version": "1.0",
        "mode": "safe-simulation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "scenario": asdict(configuration.scenario),
            "cache": asdict(configuration.cache),
            "workload": asdict(configuration.workload),
            "alerts": asdict(configuration.alerts),
        },
        "io_statistics": io_statistics,
        "page_heat": _heat_analysis(samples, configuration),
        "cache_results": cache_results,
        "cache_comparison": compare_results(cache_results),
        "anomalies": anomalies,
        "alerts": {
            "summary": summary(alerts),
            "events": [event.to_dict() for event in alerts],
        },
        "sample_count": len(samples),
        "samples": [sample.to_dict() for sample in samples],
    }
