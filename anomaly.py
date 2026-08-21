"""Rule-based anomaly detector for benchmark sample streams."""

from __future__ import annotations

from analysis import describe, zscore_anomalies


def detect_anomalies(
    samples: list[dict],
    bandwidth_drop: float = 25,
    latency_spike: float = 2.5,
) -> list[dict]:
    """Detect low-bandwidth points and statistically unusual latency.

    The bandwidth rule is intentionally relative to the current run, which
    makes it useful across devices with very different nominal throughput.
    """
    if not samples:
        return []

    bandwidth_values = [float(sample.get("bandwidth", 0)) for sample in samples]
    latency_values = [float(sample.get("latency", 0)) for sample in samples]
    events = []
    average_bandwidth = describe(bandwidth_values).average
    lower_bandwidth_limit = average_bandwidth * (1 - bandwidth_drop / 100)

    for index, bandwidth in enumerate(bandwidth_values):
        if average_bandwidth and bandwidth < lower_bandwidth_limit:
            events.append(
                {
                    "index": index,
                    "type": "performance-jitter",
                    "severity": "warning",
                    "value": bandwidth,
                    "message": "带宽明显低于整体平均值",
                }
            )

    for point in zscore_anomalies(latency_values, latency_spike):
        events.append(
            {
                "index": point["index"],
                "type": "latency-spike",
                "severity": "warning",
                "value": point["value"],
                "zscore": point["zscore"],
                "message": "检测到延迟毛刺",
            }
        )
    events.sort(key=lambda event: (event["index"], event["type"]))
    return events
