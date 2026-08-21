"""Build portable, complete SSD cache-performance reports."""

from __future__ import annotations

from datetime import datetime, timezone

from alerts import evaluate_result, summary


def build_report(task: dict, cache_comparison: dict | None = None) -> dict:
    """Build a stable report envelope shared by Web and CLI exports."""
    result = task.get("result", task)
    alerts = evaluate_result(result)
    analysis = result.get("analysis", {})
    bandwidth = analysis.get("bandwidth", {})
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "safety": {"mode": "safe-simulation", "writes_performed": False},
        "task": {
            "id": task.get("id"),
            "name": task.get("name"),
            "device": task.get("device"),
            "type": task.get("test_type"),
            "configuration": {
                "block_size": task.get("block_size"),
                "io_depth": task.get("io_depth"),
                "jobs": task.get("jobs"),
                "runtime": task.get("runtime"),
            },
        },
        "device": {"smart": result.get("smart", {}), "cache": result.get("cache")},
        "performance": {
            "summary": result.get("summary", {}),
            "statistics": analysis,
            "bandwidth_stability": bandwidth.get("variation_percent"),
            "anomalies": result.get("anomalies", []),
        },
        "cache_algorithms": cache_comparison or {},
        "alerts": {
            "summary": summary(alerts),
            "events": [event.to_dict() for event in alerts],
        },
        "samples": result.get("points", []),
    }


def executive_conclusion(report: dict) -> str:
    alert_summary = report["alerts"]["summary"]
    performance_summary = report["performance"]["summary"]
    if alert_summary["critical"]:
        return "发现关键健康或性能风险，建议暂停进一步压力测试并检查设备。"
    if alert_summary["warning"]:
        return "测试发现需关注项，建议结合 SMART 与缓存算法对比复核。"
    peak_bandwidth = performance_summary.get("peak_bw", "—")
    steady_bandwidth = performance_summary.get("steady_bw", "—")
    return (
        f"设备测试表现正常；峰值带宽 {peak_bandwidth} MB/s，"
        f"稳态带宽 {steady_bandwidth} MB/s。"
    )
