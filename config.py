"""Load and validate the settings shared by analysis scenarios.

Configuration errors are reported before a run begins. In particular, cache
sizes, workload mixes and alert thresholds are checked here so downstream code
can work with typed values instead of repeatedly guarding raw YAML data.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None


@dataclass(frozen=True)
class AlertThresholds:
    temperature_warning: float = 65.0
    temperature_critical: float = 75.0
    latency_spike_zscore: float = 2.5
    bandwidth_drop_percent: float = 25.0


@dataclass(frozen=True)
class Scenario:
    name: str
    profile: str = "sustained-write"
    runtime: int = 1800
    cache_pages: int = 1024
    safe_simulation: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CacheConfiguration:
    algorithm: str = "compare"
    capacity_pages: int = 1024
    hot_window_ms: int = 10_000
    hot_threshold: float = 4.0
    cold_threshold: float = 2.0
    read_weight: float = 1.0
    write_weight: float = 1.5


@dataclass(frozen=True)
class WorkloadConfiguration:
    kind: str = "mixed"
    count: int = 1000
    page_count: int = 4096
    read_ratio: float = 0.7
    block_size: int = 4096
    seed: int = 7


@dataclass(frozen=True)
class LoggingConfiguration:
    directory: str = "logs"
    level: str = "INFO"
    max_bytes: int = 2_000_000
    backup_count: int = 5


@dataclass(frozen=True)
class ApplicationConfiguration:
    scenario: Scenario
    cache: CacheConfiguration
    workload: WorkloadConfiguration
    alerts: AlertThresholds
    logging: LoggingConfiguration


def load_yaml(path: str | Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required; install requirements.txt")
    with open(path, encoding="utf-8") as source:
        data = yaml.safe_load(source) or {}
    if not isinstance(data, dict):
        raise ValueError("configuration root must be a mapping")
    return data


def parse_thresholds(data: dict[str, Any]) -> AlertThresholds:
    raw = data.get("alerts", {})
    result = AlertThresholds(
        **{key: raw[key] for key in AlertThresholds.__dataclass_fields__ if key in raw}
    )
    if not 0 < result.temperature_warning < result.temperature_critical <= 100:
        raise ValueError("invalid temperature thresholds")
    if not 0 < result.latency_spike_zscore <= 10:
        raise ValueError("invalid latency z-score")
    if not 0 < result.bandwidth_drop_percent < 100:
        raise ValueError("invalid bandwidth drop threshold")
    return result


def parse_scenario(data: dict[str, Any]) -> Scenario:
    raw = data.get("scenario", data)
    scenario = Scenario(
        name=str(raw.get("name", "unnamed")),
        profile=str(raw.get("profile", "sustained-write")),
        runtime=int(raw.get("runtime", 1800)),
        cache_pages=int(raw.get("cache_pages", 1024)),
        safe_simulation=bool(raw.get("safe_simulation", True)),
        tags=tuple(raw.get("tags", [])),
    )
    if not scenario.safe_simulation:
        raise ValueError("this application permits safe_simulation only")
    if not 30 <= scenario.runtime <= 7200 or scenario.cache_pages < 1:
        raise ValueError("invalid scenario limits")
    return scenario


def parse_cache(data: dict[str, Any]) -> CacheConfiguration:
    raw = data.get("cache", {})
    allowed_algorithms = {"lru2", "arc", "lirs", "compare"}
    result = CacheConfiguration(
        **{
            key: raw[key]
            for key in CacheConfiguration.__dataclass_fields__
            if key in raw
        }
    )
    if result.algorithm not in allowed_algorithms:
        raise ValueError("unsupported cache algorithm")
    if not 1 <= result.capacity_pages <= 10_000_000:
        raise ValueError("cache capacity_pages is out of range")
    if result.hot_window_ms <= 0:
        raise ValueError("hot_window_ms must be positive")
    if not 0 <= result.cold_threshold < result.hot_threshold:
        raise ValueError("hot threshold must exceed cold threshold")
    if result.read_weight <= 0 or result.write_weight <= 0:
        raise ValueError("cache access weights must be positive")
    return result


def parse_workload(data: dict[str, Any]) -> WorkloadConfiguration:
    raw = data.get("workload", {})
    allowed_kinds = {"sequential", "random", "mixed", "hot-cold"}
    result = WorkloadConfiguration(
        **{
            key: raw[key]
            for key in WorkloadConfiguration.__dataclass_fields__
            if key in raw
        }
    )
    if result.kind not in allowed_kinds:
        raise ValueError("unsupported workload kind")
    if not 1 <= result.count <= 1_000_000:
        raise ValueError("workload count is out of range")
    if not 1 <= result.page_count <= 100_000_000:
        raise ValueError("workload page_count is out of range")
    if not 0 <= result.read_ratio <= 1:
        raise ValueError("read_ratio must be between zero and one")
    if result.block_size not in {
        4096,
        8192,
        16384,
        32768,
        65536,
        131072,
        262144,
        524288,
        1048576,
    }:
        raise ValueError("unsupported workload block_size")
    return result


def parse_logging(data: dict[str, Any]) -> LoggingConfiguration:
    raw = data.get("logging", {})
    result = LoggingConfiguration(
        **{
            key: raw[key]
            for key in LoggingConfiguration.__dataclass_fields__
            if key in raw
        }
    )
    if result.level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ValueError("unsupported log level")
    if result.max_bytes < 1024 or not 1 <= result.backup_count <= 100:
        raise ValueError("invalid log rotation configuration")
    return result


def parse_application_config(data: dict[str, Any]) -> ApplicationConfiguration:
    return ApplicationConfiguration(
        scenario=parse_scenario(data),
        cache=parse_cache(data),
        workload=parse_workload(data),
        alerts=parse_thresholds(data),
        logging=parse_logging(data),
    )


def load_application_config(path: str | Path) -> ApplicationConfiguration:
    return parse_application_config(load_yaml(path))
