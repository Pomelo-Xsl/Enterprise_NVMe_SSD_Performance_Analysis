"""Deterministic business demo for the NVMe analysis workflow."""

from __future__ import annotations

import random


DEMO_NAME = "企业数据库冷热 IO 缓存分析案例"


def _block_size(index: int) -> int:
    """Use the block-size mix commonly seen in database and log workloads."""
    if index % 20 == 0:
        return 131_072
    if index % 5 == 0:
        return 16_384
    return 4096


def _sample(
    index: int,
    page: int,
    operation: str,
    latency_us: float,
    queue_depth: int,
) -> dict:
    return {
        "timestamp_ms": index * 5,
        "lba": page,
        "size_bytes": _block_size(index),
        "operation": operation,
        "latency_us": round(latency_us, 2),
        "queue_depth": queue_depth,
    }


def build_demo_payload(seed: int = 2026) -> dict:
    """Create a four-phase workload with heat, scan pressure and recovery.

    The data represents an order database: a small index and active-order set
    receive repeated reads while reports scan older pages. A maintenance phase
    introduces queue pressure and latency spikes before normal traffic recovers.
    """
    rng = random.Random(seed)
    samples = []

    for index in range(600):
        if index < 200:
            phase = "hot-transaction"
            is_hot = rng.random() < 0.88
            page = rng.randrange(16) if is_hot else 1024 + rng.randrange(128)
            queue_depth = 8
            latency = rng.uniform(65, 105) if is_hot else rng.uniform(120, 180)
            read_ratio = 0.82
        elif index < 400:
            phase = "mixed-reporting"
            is_hot = rng.random() < 0.62
            page = rng.randrange(24) if is_hot else 1200 + rng.randrange(320)
            queue_depth = 16
            latency = rng.uniform(85, 135) if is_hot else rng.uniform(150, 240)
            read_ratio = 0.68
        elif index < 450:
            phase = "maintenance-scan"
            page = 2048 + (index - 400)
            queue_depth = 32
            latency = rng.uniform(300, 460)
            read_ratio = 0.92
        else:
            phase = "traffic-recovery"
            is_hot = rng.random() < 0.78
            page = rng.randrange(20) if is_hot else 1600 + rng.randrange(192)
            queue_depth = 8
            latency = rng.uniform(75, 120) if is_hot else rng.uniform(125, 195)
            read_ratio = 0.78

        if index in {217, 331, 418, 426, 439}:
            latency += rng.uniform(650, 900)

        operation = "read" if rng.random() < read_ratio else "write"
        sample = _sample(index, page, operation, latency, queue_depth)
        sample["phase"] = phase
        samples.append(sample)

    return {
        "metadata": {
            "case_id": "enterprise-db-hot-cold-v1",
            "title": DEMO_NAME,
            "industry": "电商订单数据库",
            "description": (
                "演示事务热点、历史报表扫描、维护期延迟毛刺和业务恢复，"
                "用于比较缓存算法并验证冷热页识别。"
            ),
            "phases": [
                {"name": "热点事务", "range": "0-199"},
                {"name": "混合报表", "range": "200-399"},
                {"name": "维护扫描", "range": "400-449"},
                {"name": "流量恢复", "range": "450-599"},
            ],
            "expected_observations": [
                "ARC 和 LIRS 对重复热点页保持较高命中率",
                "维护扫描阶段出现带宽下降和延迟毛刺",
                "SMART 温度触发 warning 告警",
                "恢复阶段热点页重新占据缓存",
            ],
        },
        "samples": samples,
        "smart": {
            "temperature": 69,
            "percentage_used": 18,
            "available_spare": 100,
            "media_errors": 0,
            "error_log_entries": 0,
        },
    }
