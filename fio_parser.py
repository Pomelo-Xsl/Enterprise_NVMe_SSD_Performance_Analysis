"""Parsers for FIO JSON/JSON+ output and bw/iops/latency log files."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class FioDirectionResult:
    operation: str
    io_bytes: int
    bandwidth_kib_s: float
    iops: float
    runtime_ms: int
    latency_mean_us: float
    latency_percentiles_us: dict[str, float]

    def to_dict(self) -> dict:
        return asdict(self)


def _number(data: dict, key: str, default=0):
    value = data.get(key, default)
    return value if isinstance(value, (int, float)) else default


def _latency_section(direction: dict) -> tuple[float, dict[str, float]]:
    for key, divisor in (("clat_ns", 1000), ("clat_us", 1), ("lat_ns", 1000)):
        section = direction.get(key)
        if isinstance(section, dict):
            mean_value = float(section.get("mean", 0)) / divisor
            raw_percentiles = section.get("percentile", {}) or {}
            percentiles = {
                str(name): float(value) / divisor
                for name, value in raw_percentiles.items()
            }
            return mean_value, percentiles
    return 0.0, {}


def parse_direction(operation: str, data: dict) -> FioDirectionResult:
    mean_latency, percentiles = _latency_section(data)
    return FioDirectionResult(
        operation=operation,
        io_bytes=int(_number(data, "io_bytes", _number(data, "io_kbytes") * 1024)),
        bandwidth_kib_s=float(_number(data, "bw", _number(data, "bw_bytes") / 1024)),
        iops=float(_number(data, "iops", 0)),
        runtime_ms=int(_number(data, "runtime", 0)),
        latency_mean_us=mean_latency,
        latency_percentiles_us=percentiles,
    )


def parse_fio_json(data: dict) -> dict:
    jobs = data.get("jobs", [])
    if not isinstance(jobs, list):
        raise ValueError("fio jobs must be a list")

    parsed_jobs = []
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            continue
        parsed_jobs.append(
            {
                "name": job.get("jobname", f"job-{index}"),
                "group_id": job.get("groupid", 0),
                "error": job.get("error", 0),
                "elapsed_seconds": job.get("elapsed", 0),
                "read": parse_direction("read", job.get("read", {})).to_dict(),
                "write": parse_direction("write", job.get("write", {})).to_dict(),
                "trim": parse_direction("trim", job.get("trim", {})).to_dict(),
                "job_options": job.get("job options", {}),
            }
        )

    result = {
        "fio_version": data.get("fio version", data.get("fio_version", "unknown")),
        "timestamp": data.get("timestamp", 0),
        "timestamp_ms": data.get("timestamp_ms", 0),
        "time": data.get("time"),
        "global_options": data.get("global options", {}),
        "jobs": parsed_jobs,
        "job_count": len(parsed_jobs),
        "disk_util": data.get("disk_util", []),
    }
    result["aggregate"] = summarize_jobs(result)
    return result


def load_fio_json(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as source:
        return parse_fio_json(json.load(source))


def parse_fio_log_lines(
    lines: Iterable[str],
    value_name: str,
) -> list[dict]:
    """Parse standard FIO log rows: time,value,data_direction,block_size."""

    samples = []
    direction_map = {0: "read", 1: "write", 2: "trim"}
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        columns = [column.strip() for column in line.split(",")]
        if len(columns) < 2:
            raise ValueError(f"invalid fio log row at line {line_number}")
        try:
            timestamp_ms = int(columns[0])
            value = float(columns[1])
            direction_code = int(columns[2]) if len(columns) > 2 else 0
            block_size = int(columns[3]) if len(columns) > 3 else 0
        except ValueError as error:
            raise ValueError(f"invalid numeric value at line {line_number}") from error
        samples.append(
            {
                "timestamp_ms": timestamp_ms,
                value_name: value,
                "operation": direction_map.get(direction_code, "unknown"),
                "block_size": block_size,
            }
        )
    return samples


def load_fio_log(path: str | Path, value_name: str) -> list[dict]:
    with open(path, encoding="utf-8") as source:
        return parse_fio_log_lines(source, value_name)


def summarize_jobs(parsed: dict) -> dict:
    read_bytes = sum(job["read"]["io_bytes"] for job in parsed.get("jobs", []))
    write_bytes = sum(job["write"]["io_bytes"] for job in parsed.get("jobs", []))
    read_iops = sum(job["read"]["iops"] for job in parsed.get("jobs", []))
    write_iops = sum(job["write"]["iops"] for job in parsed.get("jobs", []))
    read_bw = sum(job["read"]["bandwidth_kib_s"] for job in parsed.get("jobs", []))
    write_bw = sum(job["write"]["bandwidth_kib_s"] for job in parsed.get("jobs", []))
    return {
        "read_bytes": read_bytes,
        "write_bytes": write_bytes,
        "read_iops": read_iops,
        "write_iops": write_iops,
        "read_bandwidth_kib_s": read_bw,
        "write_bandwidth_kib_s": write_bw,
        "read_ratio": (
            read_bytes / (read_bytes + write_bytes) if read_bytes + write_bytes else 0.0
        ),
        "write_ratio": (
            write_bytes / (read_bytes + write_bytes)
            if read_bytes + write_bytes
            else 0.0
        ),
    }
