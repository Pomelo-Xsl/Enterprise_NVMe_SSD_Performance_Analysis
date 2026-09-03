"""Synthetic traces used when no captured IO samples are supplied.

Sequential, random, mixed and alternating-hot-set generators model distinct
access shapes rather than claiming to reproduce a specific SSD. A caller-owned
seed makes regression tests and demonstrations repeatable.
"""

from __future__ import annotations

import random
from typing import Iterable

from models import IOSample


DEFAULT_SAMPLE_INTERVAL_MS = 10


def _sample(
    index: int,
    page: int,
    operation: str,
    block_size: int,
    queue_depth: int,
    latency_us: float,
) -> IOSample:
    return IOSample(
        timestamp_ms=index * DEFAULT_SAMPLE_INTERVAL_MS,
        lba=page,
        size_bytes=block_size,
        operation=operation,
        latency_us=latency_us,
        queue_depth=queue_depth,
    )


def _validate_ratio(name: str, value: float) -> None:
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between zero and one")


def sequential(
    count: int,
    start_page: int = 0,
    block_size: int = 4096,
    write_ratio: float = 0.0,
) -> list[IOSample]:
    """Generate increasing LBAs with an optional write prefix."""
    if count < 1:
        raise ValueError("count must be positive")
    _validate_ratio("write_ratio", write_ratio)

    return [
        _sample(
            index,
            start_page + index,
            "write" if index / count < write_ratio else "read",
            block_size,
            1,
            80 + index % 7,
        )
        for index in range(count)
    ]


def random_io(
    count: int,
    page_count: int,
    seed: int = 7,
    read_ratio: float = 0.7,
    block_size: int = 4096,
) -> list[IOSample]:
    """Generate reproducible random IO with realistic queue-depth choices."""
    if count < 1 or page_count < 1:
        raise ValueError("count and page_count must be positive")
    _validate_ratio("read_ratio", read_ratio)

    rng = random.Random(seed)
    return [
        _sample(
            i,
            rng.randrange(page_count),
            "read" if rng.random() < read_ratio else "write",
            block_size,
            rng.choice([1, 4, 16, 32]),
            rng.uniform(60, 250),
        )
        for i in range(count)
    ]


def mixed_io(count: int, page_count: int, seed: int = 7) -> list[IOSample]:
    """Generate a deterministic 60/40 read/write workload."""
    stream = []
    for index, sample in enumerate(random_io(count, page_count, seed, 0.5)):
        operation = "write" if index % 5 in (0, 1) else "read"
        stream.append(
            IOSample(
                sample.timestamp_ms,
                sample.lba,
                sample.size_bytes,
                operation,
                sample.latency_us,
                sample.queue_depth,
            )
        )
    return stream


def hot_cold_alternating(
    rounds: int, hot_pages: int = 8, cold_pages: int = 128, seed: int = 7
) -> list[IOSample]:
    """Alternate focused hot-set phases with wide cold-set phases."""
    if rounds < 1 or hot_pages < 1 or cold_pages < 1:
        raise ValueError("positive workload dimensions required")
    rng = random.Random(seed)
    stream = []
    index = 0
    for phase in range(rounds):
        for _ in range(20):
            hot = phase % 2 == 0
            page = (
                rng.randrange(hot_pages)
                if hot
                else hot_pages + rng.randrange(cold_pages)
            )
            stream.append(
                _sample(
                    index,
                    page,
                    "write" if rng.random() < 0.2 else "read",
                    4096,
                    8,
                    70 if hot else 180,
                )
            )
            index += 1
    return stream


def to_points(samples: Iterable[IOSample]) -> list[dict]:
    """Adapt IO samples to the dashboard's time-series shape."""
    return [
        {
            "minute": sample.timestamp_ms / 60_000,
            "bandwidth": round(
                sample.size_bytes / max(sample.latency_us, 1),
                2,
            ),
            "iops": round(1_000_000 / max(sample.latency_us, 1), 2),
            "latency": sample.latency_us,
            "temperature": 40 + min(35, sample.queue_depth * 0.4),
        }
        for sample in samples
    ]
