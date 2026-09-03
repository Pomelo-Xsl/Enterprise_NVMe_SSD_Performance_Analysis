"""Turn analysis measurements into operator-facing alerts.

Thresholds come from the application configuration rather than being hidden in
the rule functions. Keeping that boundary here also makes an alert reproducible
when an imported result is reviewed later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from config import AlertThresholds


SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Alert:
    code: str
    severity: str
    message: str
    value: float | int | str
    threshold: float | int | str
    source: str

    def to_dict(self) -> dict:
        return asdict(self)


def _append_if(
    events: list[Alert],
    condition: bool,
    *,
    code: str,
    severity: str,
    message: str,
    value,
    threshold,
    source: str,
) -> None:
    """Append an alert while keeping individual rules easy to scan."""
    if condition:
        events.append(Alert(code, severity, message, value, threshold, source))


def evaluate_health(
    smart: dict,
    thresholds: AlertThresholds = AlertThresholds(),
) -> list[Alert]:
    events: list[Alert] = []
    temperature = float(smart.get("temperature", 0))
    percentage_used = float(smart.get("percentage_used", 0))
    media_errors = int(smart.get("media_errors", 0))
    error_log_entries = int(smart.get("error_log_entries", 0))

    _append_if(
        events,
        temperature >= thresholds.temperature_critical,
        code="temperature-critical",
        severity="critical",
        message="SSD 温度达到临界阈值",
        value=temperature,
        threshold=thresholds.temperature_critical,
        source="smart",
    )
    _append_if(
        events,
        thresholds.temperature_warning <= temperature < thresholds.temperature_critical,
        code="temperature-warning",
        severity="warning",
        message="SSD 温度高于建议阈值",
        value=temperature,
        threshold=thresholds.temperature_warning,
        source="smart",
    )
    _append_if(
        events,
        percentage_used >= 90,
        code="wear-high",
        severity="warning",
        message="SSD 使用寿命接近耗尽",
        value=percentage_used,
        threshold=90,
        source="smart",
    )
    _append_if(
        events,
        media_errors > 0,
        code="media-error",
        severity="critical",
        message="SMART 报告介质错误",
        value=media_errors,
        threshold=0,
        source="smart",
    )
    _append_if(
        events,
        error_log_entries > 0,
        code="error-log",
        severity="warning",
        message="SMART 错误日志条目非零",
        value=error_log_entries,
        threshold=0,
        source="smart",
    )
    return events


def evaluate_performance(
    analysis: dict,
    anomalies: list[dict],
    thresholds: AlertThresholds = AlertThresholds(),
):
    events = []
    bandwidth = analysis.get("bandwidth", {})
    variation = float(bandwidth.get("variation_percent", 0))
    trend = analysis.get("trend", {}).get("direction")
    _append_if(
        events,
        variation >= 30,
        code="bandwidth-volatile",
        severity="warning",
        message="带宽波动超过允许范围",
        value=variation,
        threshold=30,
        source="performance",
    )
    _append_if(
        events,
        trend == "falling",
        code="bandwidth-declining",
        severity="warning",
        message="带宽呈持续下降趋势",
        value=trend,
        threshold="not-falling",
        source="performance",
    )
    for anomaly in anomalies:
        if anomaly.get("type") == "latency-spike":
            events.append(
                Alert(
                    "latency-spike",
                    "warning",
                    "检测到 IO 延迟毛刺",
                    anomaly.get("value", 0),
                    thresholds.latency_spike_zscore,
                    "latency",
                )
            )
    return events


def evaluate_result(
    result: dict,
    thresholds: AlertThresholds = AlertThresholds(),
) -> list[Alert]:
    health_events = evaluate_health(result.get("smart", {}), thresholds)
    performance_events = evaluate_performance(
        result.get("analysis", {}),
        result.get("anomalies", []),
        thresholds,
    )
    return sorted(
        health_events + performance_events,
        key=lambda event: (SEVERITY_ORDER.get(event.severity, 9), event.code),
    )


def summary(events: list[Alert]) -> dict:
    return {
        "total": len(events),
        "critical": sum(e.severity == "critical" for e in events),
        "warning": sum(e.severity == "warning" for e in events),
        "healthy": not events,
    }
