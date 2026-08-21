"""Domain entities shared by workload, cache, device, and report modules."""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class IOSample:
    timestamp_ms: int
    lba: int
    size_bytes: int
    operation: str
    latency_us: float
    queue_depth: int = 1

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "IOSample":
        """Restore a normalized sample produced by JSON or CSV ingestion."""
        operation = str(value.get("operation", "read")).lower()
        if operation not in {"read", "write"}:
            raise ValueError("operation must be read or write")
        sample = cls(
            timestamp_ms=int(value["timestamp_ms"]),
            lba=int(value["lba"]),
            size_bytes=int(value["size_bytes"]),
            operation=operation,
            latency_us=float(value["latency_us"]),
            queue_depth=int(value.get("queue_depth", 1)),
        )
        if sample.timestamp_ms < 0 or sample.lba < 0:
            raise ValueError("timestamp_ms and lba must be non-negative")
        if sample.size_bytes <= 0 or sample.latency_us < 0:
            raise ValueError("size_bytes must be positive and latency non-negative")
        if sample.queue_depth <= 0:
            raise ValueError("queue_depth must be positive")
        return sample


@dataclass
class CacheState:
    capacity_pages: int
    resident_pages: int = 0
    dirty_pages: int = 0
    hits: int = 0
    misses: int = 0
    cold_hits: int = 0
    hot_hits: int = 0
    dirty_evictions: int = 0
    clean_evictions: int = 0

    def hit_ratio(self):
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def to_dict(self):
        return asdict(self) | {"hit_ratio": self.hit_ratio()}


@dataclass(frozen=True)
class DeviceInfo:
    path: str
    model: str = "Unknown NVMe"
    serial: str = "—"
    firmware: str = "—"
    capacity_bytes: int = 0
    temperature_c: float | None = None
    percentage_used: int | None = None
    media_errors: int | None = None
    error_log_entries: int | None = None
    collected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self):
        return asdict(self)
