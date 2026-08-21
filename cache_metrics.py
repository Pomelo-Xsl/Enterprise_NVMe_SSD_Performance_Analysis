"""Cache hit decomposition and algorithm-comparison statistics."""

from __future__ import annotations

from collections import Counter
from statistics import mean


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def decompose_events(events: list[dict]) -> dict:
    total = len(events)
    hits = sum(bool(event.get("hit")) for event in events)
    misses = total - hits
    hot_hits = sum(
        bool(event.get("hit")) and bool(event.get("hot")) for event in events
    )
    cold_hits = hits - hot_hits
    dirty_evictions = sum(bool(event.get("dirty_eviction")) for event in events)
    evictions = sum(event.get("evicted") is not None for event in events)
    clean_evictions = evictions - dirty_evictions
    unique_pages = len({event.get("page") for event in events})
    reuse_hits = Counter(event.get("page") for event in events if event.get("hit"))

    return {
        "accesses": total,
        "unique_pages": unique_pages,
        "hits": hits,
        "misses": misses,
        "hit_ratio": _ratio(hits, total),
        "miss_ratio": _ratio(misses, total),
        "hot_hits": hot_hits,
        "cold_hits": cold_hits,
        "hot_hit_ratio": _ratio(hot_hits, hits),
        "cold_hit_ratio": _ratio(cold_hits, hits),
        "evictions": evictions,
        "dirty_evictions": dirty_evictions,
        "clean_evictions": clean_evictions,
        "dirty_eviction_ratio": _ratio(dirty_evictions, evictions),
        "most_reused_pages": reuse_hits.most_common(10),
    }


def compare_results(results: dict[str, dict]) -> dict:
    algorithms = {}
    for name, result in results.items():
        metrics = decompose_events(result.get("events", []))
        state = result.get("state", {})
        metrics["resident_pages"] = state.get("resident_pages", 0)
        metrics["dirty_pages"] = state.get("dirty_pages", 0)
        algorithms[name] = metrics

    ranking = sorted(
        algorithms,
        key=lambda name: (
            -algorithms[name]["hit_ratio"],
            algorithms[name]["dirty_eviction_ratio"],
            name,
        ),
    )

    hit_ratios = [value["hit_ratio"] for value in algorithms.values()]
    return {
        "algorithms": algorithms,
        "ranking": ranking,
        "best_algorithm": ranking[0] if ranking else None,
        "average_hit_ratio": round(mean(hit_ratios), 6) if hit_ratios else 0.0,
        "hit_ratio_spread": (
            round(max(hit_ratios) - min(hit_ratios), 6) if hit_ratios else 0.0
        ),
    }
