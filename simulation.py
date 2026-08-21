"""End-to-end safe cache and IO performance simulation orchestration."""

from __future__ import annotations

from analysis import analyse
from anomaly import detect_anomalies
from cache_metrics import compare_results
from cache_simulator import compare_algorithms
from hot_cold import classify_workload
from workloads import hot_cold_alternating, mixed_io, random_io, sequential, to_points

GENERATORS = {
    "sequential": sequential,
    "random": random_io,
    "mixed": mixed_io,
    "hot-cold": hot_cold_alternating,
}


def _generate_samples(
    workload: str,
    count: int,
    cache_pages: int,
    seed: int,
):
    """Call workload generators whose public signatures intentionally differ."""
    generator = GENERATORS[workload]
    if workload == "sequential":
        return generator(count)
    if workload == "hot-cold":
        rounds = max(1, (count + 19) // 20)
        return generator(rounds, seed=seed)[:count]

    working_set_pages = max(8, cache_pages * 4)
    return generator(count, working_set_pages, seed=seed)


def run_simulation(
    workload: str = "mixed",
    count: int = 200,
    cache_pages: int = 32,
    seed: int = 7,
) -> dict:
    """Run the complete in-memory cache and performance analysis chain."""
    if workload not in GENERATORS:
        raise ValueError(f"unknown workload: {workload}")
    if count < 1:
        raise ValueError("count must be positive")
    if cache_pages < 1:
        raise ValueError("cache_pages must be positive")

    samples = _generate_samples(workload, count, cache_pages, seed)
    performance_points = to_points(samples)
    cache_results = compare_algorithms(samples, cache_pages)
    return {
        "mode": "safe-simulation",
        "workload": workload,
        "sample_count": len(samples),
        "cache_comparison": cache_results,
        "cache_metrics": compare_results(cache_results),
        "page_heat": classify_workload(samples),
        "performance": analyse(performance_points),
        "anomalies": detect_anomalies(performance_points),
        "points": performance_points,
    }
