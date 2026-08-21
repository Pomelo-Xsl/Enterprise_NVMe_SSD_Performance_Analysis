"""Reusable performance-analysis algorithms for NVMe Insight.

All functions operate on safe, collected samples and never access a device.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from statistics import median
from typing import Iterable, Sequence


@dataclass(frozen=True)
class SeriesStats:
    count: int
    minimum: float
    maximum: float
    average: float
    stddev: float
    variation_percent: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KneePoint:
    index: int
    baseline: float
    stable: float
    drop_percent: float
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


def values(samples: Iterable[dict], field: str) -> list[float]:
    """Extract a numeric series while ignoring incomplete samples."""
    result = []
    for sample in samples:
        value = sample.get(field)
        if isinstance(value, (int, float)):
            result.append(float(value))
    return result


def describe(series: Sequence[float]) -> SeriesStats:
    if not series:
        return SeriesStats(0, 0, 0, 0, 0, 0)
    average = sum(series) / len(series)
    variance = sum((value - average) ** 2 for value in series) / len(series)
    low, high = min(series), max(series)
    return SeriesStats(
        len(series),
        low,
        high,
        average,
        sqrt(variance),
        ((high - low) / average * 100) if average else 0,
    )


def percentile(series: Sequence[float], p: float) -> float:
    """Linearly interpolated percentile; p is in the inclusive 0..100 range."""
    if not series:
        return 0.0
    if not 0 <= p <= 100:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(series)
    position = (len(ordered) - 1) * p / 100
    left, right = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def latency_qos(samples: Iterable[dict], field: str = "latency") -> dict:
    series = values(samples, field)
    return {
        "average": describe(series).average,
        "p50": percentile(series, 50),
        "p90": percentile(series, 90),
        "p95": percentile(series, 95),
        "p99": percentile(series, 99),
        "p999": percentile(series, 99.9),
        "p9999": percentile(series, 99.99),
    }


def detect_knee(
    series: Sequence[float], window: int = 3, threshold_percent: float = 20
) -> KneePoint | None:
    """Find the first sustained drop relative to the initial performance window."""
    if len(series) < window * 2:
        return None
    baseline = sum(series[:window]) / window
    if baseline <= 0:
        return None
    for index in range(window, len(series) - window + 1):
        stable = sum(series[index : index + window]) / window
        drop = (baseline - stable) / baseline * 100
        if drop >= threshold_percent:
            consistency = (
                sum(
                    1
                    for value in series[index : index + window]
                    if value <= baseline * (1 - threshold_percent / 100)
                )
                / window
            )
            return KneePoint(index, baseline, stable, drop, consistency)
    return None


def recovery_rate(initial: float, recovered: float) -> float:
    return round((recovered / initial * 100), 2) if initial > 0 else 0.0


def stability_grade(stats: SeriesStats) -> str:
    if stats.count < 3:
        return "样本不足"
    if stats.variation_percent <= 5:
        return "优秀"
    if stats.variation_percent <= 15:
        return "稳定"
    if stats.variation_percent <= 30:
        return "需关注"
    return "波动明显"


def temperature_correlation(samples: Sequence[dict]) -> float:
    """Pearson correlation between bandwidth and temperature."""
    pairs = [
        (float(s["bandwidth"]), float(s["temperature"]))
        for s in samples
        if isinstance(s.get("bandwidth"), (int, float))
        and isinstance(s.get("temperature"), (int, float))
    ]
    if len(pairs) < 3:
        return 0.0
    xs, ys = zip(*pairs)
    x_mean, y_mean = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    denominator = sqrt(
        sum((x - x_mean) ** 2 for x in xs) * sum((y - y_mean) ** 2 for y in ys)
    )
    return round(numerator / denominator, 4) if denominator else 0.0


def moving_average(series: Sequence[float], window: int = 5) -> list[float]:
    """Trailing moving average that keeps the output aligned with samples."""
    if window < 1:
        raise ValueError("window must be positive")
    return [
        sum(series[max(0, index - window + 1) : index + 1]) / min(index + 1, window)
        for index in range(len(series))
    ]


def ewma(series: Sequence[float], alpha: float = 0.3) -> list[float]:
    """Exponentially weighted moving average for noisy performance series."""
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    output = []
    for value in series:
        output.append(
            float(value)
            if not output
            else alpha * float(value) + (1 - alpha) * output[-1]
        )
    return output


def zscore_anomalies(series: Sequence[float], threshold: float = 2.5) -> list[dict]:
    stats = describe(series)
    if stats.count < 3 or stats.stddev == 0:
        return []
    return [
        {
            "index": index,
            "value": value,
            "zscore": round((value - stats.average) / stats.stddev, 3),
        }
        for index, value in enumerate(series)
        if abs((value - stats.average) / stats.stddev) >= threshold
    ]


def linear_trend(series: Sequence[float]) -> dict:
    """Least-squares slope and normalized direction for a time series."""
    count = len(series)
    if count < 2:
        return {"slope": 0.0, "direction": "insufficient-data"}
    mean_x, mean_y = (count - 1) / 2, sum(series) / count
    denominator = sum((index - mean_x) ** 2 for index in range(count))
    slope = (
        sum((index - mean_x) * (value - mean_y) for index, value in enumerate(series))
        / denominator
    )
    tolerance = max(abs(mean_y) * 0.002, 0.001)
    return {
        "slope": round(slope, 4),
        "direction": (
            "rising"
            if slope > tolerance
            else "falling" if slope < -tolerance else "flat"
        ),
    }


def analyse(samples: Sequence[dict]) -> dict:
    bandwidth = values(samples, "bandwidth")
    iops = values(samples, "iops")
    knee = detect_knee(bandwidth)
    return {
        "bandwidth": describe(bandwidth).to_dict(),
        "iops": describe(iops).to_dict(),
        "latency": latency_qos(samples),
        "knee": knee.to_dict() if knee else None,
        "stability": stability_grade(describe(bandwidth)),
        "thermal_correlation": temperature_correlation(samples),
        "median_bandwidth": median(bandwidth) if bandwidth else 0,
        "trend": linear_trend(bandwidth),
        "anomalies": zscore_anomalies(bandwidth),
        "smoothed_bandwidth": {
            "moving_average": moving_average(bandwidth),
            "ewma": ewma(bandwidth),
        },
    }
