"""Read-only NVMe device discovery for Linux analysis hosts.

The scanner prefers ``nvme list -o json`` and supplements it with ``lsblk``.
The second source is important for nvme-cli releases that omit a namespace
from their JSON output even though the kernel exposes the block device.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone

from nvme_parser import (
    parse_error_log,
    parse_identify_controller,
    parse_identify_namespace,
)


NAMESPACE_PATH = re.compile(r"^/dev/nvme\d+(?:c\d+)?n\d+$")


def _number(value, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        try:
            return max(0, int(float(cleaned)))
        except ValueError:
            return default
    return default


def _first(mapping: dict, *keys, default=None):
    lowered = {str(key).lower(): value for key, value in mapping.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return default


def _device_path(value) -> str:
    path = str(value or "").strip()
    if path and not path.startswith("/dev/"):
        path = f"/dev/{path}"
    return path


def _human_capacity(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "未知"
    if size_bytes >= 10**12:
        return f"{size_bytes / 10**12:.2f} TB"
    return f"{size_bytes / 10**9:.2f} GB"


def _normalize_device(raw: dict, inherited: dict | None = None) -> dict | None:
    inherited = inherited or {}
    path = _device_path(
        _first(
            raw,
            "DevicePath",
            "Device",
            "Path",
            "Name",
            "NameSpace",
            "Namespace",
        )
    )
    if not NAMESPACE_PATH.match(path):
        return None

    model = str(
        _first(raw, "ModelNumber", "Model", "ModelName", "mn", default="")
        or inherited.get("model")
        or "Unknown NVMe"
    ).strip()
    serial = str(
        _first(raw, "SerialNumber", "Serial", "sn", default="")
        or inherited.get("serial")
        or "—"
    ).strip()
    firmware = str(
        _first(raw, "Firmware", "FirmwareRevision", "Revision", "fr", default="")
        or inherited.get("firmware")
        or "—"
    ).strip()
    size_bytes = _number(
        _first(
            raw,
            "PhysicalSize",
            "Size",
            "Capacity",
            "TotalBytes",
            "UsedBytes",
            default=0,
        )
    )
    sector_size = _number(
        _first(raw, "SectorSize", "LogicalSectorSize", "LOG-SEC", default=0)
    )
    return {
        "path": path,
        "model": model,
        "serial": serial,
        "firmware": firmware,
        "capacity": _human_capacity(size_bytes),
        "capacity_bytes": size_bytes,
        "namespace": path.rsplit("/", 1)[-1],
        "sector_size": sector_size,
        "pcie": "NVMe · PCIe",
        "cache": "待读取",
        "health": "待检查",
        "source": "nvme-cli",
    }


def _walk_nvme_json(node, inherited: dict | None = None):
    """Yield namespace dictionaries from flat and nested nvme-cli schemas."""
    inherited = dict(inherited or {})
    if isinstance(node, list):
        for item in node:
            yield from _walk_nvme_json(item, inherited)
        return
    if not isinstance(node, dict):
        return

    controller_metadata = {
        "model": _first(node, "ModelNumber", "Model", "mn"),
        "serial": _first(node, "SerialNumber", "Serial", "sn"),
        "firmware": _first(node, "Firmware", "FirmwareRevision", "fr"),
    }
    inherited.update(
        {key: value for key, value in controller_metadata.items() if value not in (None, "")}
    )
    normalized = _normalize_device(node, inherited)
    if normalized:
        yield normalized

    for value in node.values():
        if isinstance(value, (dict, list)):
            yield from _walk_nvme_json(value, inherited)


def parse_nvme_list_json(payload: dict | list) -> list[dict]:
    """Parse all visible namespaces and deduplicate them by device path."""
    devices: dict[str, dict] = {}
    for device in _walk_nvme_json(payload):
        existing = devices.get(device["path"])
        if existing:
            devices[device["path"]] = _merge_device(existing, device)
        else:
            devices[device["path"]] = device
    return [devices[path] for path in sorted(devices, key=_namespace_sort_key)]


def parse_lsblk_json(payload: dict | list) -> list[dict]:
    """Parse NVMe namespaces from lsblk JSON, including nested blockdevices."""
    roots = payload.get("blockdevices", []) if isinstance(payload, dict) else payload
    found: dict[str, dict] = {}

    def visit(node):
        if not isinstance(node, dict):
            return
        path = _device_path(_first(node, "path", "name"))
        transport = str(_first(node, "tran", default="") or "").lower()
        if NAMESPACE_PATH.match(path) and (transport in {"", "nvme"}):
            size_bytes = _number(_first(node, "size", default=0))
            found[path] = {
                "path": path,
                "model": str(_first(node, "model", default="Unknown NVMe")).strip(),
                "serial": str(_first(node, "serial", default="—")).strip(),
                "firmware": str(_first(node, "rev", default="—")).strip(),
                "capacity": _human_capacity(size_bytes),
                "capacity_bytes": size_bytes,
                "namespace": path.rsplit("/", 1)[-1],
                "sector_size": _number(_first(node, "log-sec", "log_sec", default=0)),
                "pcie": "NVMe · PCIe",
                "cache": "待读取",
                "health": "待检查",
                "source": "lsblk",
            }
        for child in node.get("children", []) or []:
            visit(child)

    for root in roots or []:
        visit(root)
    return [found[path] for path in sorted(found, key=_namespace_sort_key)]


def _namespace_sort_key(path: str):
    numbers = [int(value) for value in re.findall(r"\d+", path)]
    return tuple(numbers) or (0,)


def _merge_device(primary: dict, supplement: dict) -> dict:
    merged = dict(primary)
    for key, value in supplement.items():
        if key == "source" and value and value not in str(merged.get(key, "")):
            merged[key] = f"{merged.get(key, '')}+{value}".strip("+")
        elif merged.get(key) in (None, "", "—", "未知", "Unknown NVMe", 0):
            merged[key] = value
    return merged


def merge_devices(*collections: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for collection in collections:
        for device in collection:
            path = device["path"]
            merged[path] = (
                _merge_device(merged[path], device) if path in merged else dict(device)
            )
    return [merged[path] for path in sorted(merged, key=_namespace_sort_key)]


def _temperature_celsius(value) -> float:
    temperature = float(_number(value, 0))
    # Some nvme-cli releases expose Kelvin while recent versions use Celsius.
    return round(temperature - 273.15, 1) if temperature > 200 else temperature


def _nvme_version(value: int) -> str:
    value = int(value or 0)
    if not value:
        return "未知"
    return f"{(value >> 16) & 0xFFFF}.{(value >> 8) & 0xFF}.{value & 0xFF}"


def _smart_details(data: dict) -> dict:
    percentage_used = _number(
        _first(data, "percentage_used", "percentage_used_percent", default=0)
    )
    data_units_read = _number(_first(data, "data_units_read", default=0))
    data_units_written = _number(_first(data, "data_units_written", default=0))
    return {
        "critical_warning": _number(_first(data, "critical_warning", default=0)),
        "temperature_c": _temperature_celsius(
            _first(data, "temperature", "temperature_celsius", default=0)
        ),
        "available_spare_percent": _number(
            _first(data, "avail_spare", "available_spare", default=0)
        ),
        "spare_threshold_percent": _number(
            _first(data, "spare_thresh", "available_spare_threshold", default=0)
        ),
        "percentage_used": percentage_used,
        "life_remaining_percent": max(0, 100 - percentage_used),
        "data_units_read": data_units_read,
        "data_units_written": data_units_written,
        "data_read_bytes": data_units_read * 512_000,
        "data_written_bytes": data_units_written * 512_000,
        "host_read_commands": _number(_first(data, "host_read_commands", default=0)),
        "host_write_commands": _number(_first(data, "host_write_commands", default=0)),
        "controller_busy_minutes": _number(
            _first(data, "controller_busy_time", default=0)
        ),
        "power_cycles": _number(_first(data, "power_cycles", default=0)),
        "power_on_hours": _number(_first(data, "power_on_hours", default=0)),
        "unsafe_shutdowns": _number(_first(data, "unsafe_shutdowns", default=0)),
        "media_errors": _number(_first(data, "media_errors", default=0)),
        "error_log_entries": _number(
            _first(data, "num_err_log_entries", "error_log_entries", default=0)
        ),
        "warning_temperature_minutes": _number(
            _first(data, "warning_temp_time", default=0)
        ),
        "critical_temperature_minutes": _number(
            _first(data, "critical_comp_time", default=0)
        ),
    }


def _health_summary(smart: dict, smart_available: bool) -> dict:
    risks: list[dict] = []
    if not smart_available:
        return {"level": "unknown", "label": "SMART 未读取", "risks": risks}
    if smart["critical_warning"]:
        risks.append({"level": "critical", "message": "设备报告 Critical Warning"})
    if smart["temperature_c"] >= 75:
        risks.append({"level": "critical", "message": "当前温度达到临界阈值"})
    elif smart["temperature_c"] >= 65:
        risks.append({"level": "warning", "message": "当前温度偏高"})
    if smart["percentage_used"] >= 90:
        risks.append({"level": "warning", "message": "介质寿命接近耗尽"})
    if smart["media_errors"]:
        risks.append({"level": "critical", "message": "检测到介质或数据完整性错误"})
    if risks:
        level = "critical" if any(item["level"] == "critical" for item in risks) else "warning"
        return {"level": level, "label": "需要关注", "risks": risks}
    return {"level": "healthy", "label": "健康", "risks": risks}


def collect_device_details(
    device: dict,
    runner: Callable = subprocess.run,
    which: Callable = shutil.which,
) -> dict:
    """Collect detailed, read-only identity and SMART data for one namespace."""
    nvme = which("nvme")
    payloads: dict[str, dict | list] = {}
    command_status: dict[str, str] = {}
    commands = {
        "smart": ["smart-log"],
        "controller": ["id-ctrl"],
        "namespace": ["id-ns"],
        "errors": ["error-log"],
    }
    if nvme:
        for name, arguments in commands.items():
            try:
                completed = runner(
                    [nvme, *arguments, device["path"], "-o", "json"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=True,
                )
                payloads[name] = json.loads(completed.stdout)
                command_status[name] = "ok"
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
                command_status[name] = f"unavailable: {exc}"
    else:
        command_status = {name: "nvme-cli unavailable" for name in commands}

    smart_payload = payloads.get("smart", {})
    smart = _smart_details(smart_payload if isinstance(smart_payload, dict) else {})
    controller_payload = payloads.get("controller", {})
    controller = parse_identify_controller(
        controller_payload if isinstance(controller_payload, dict) else {}
    )
    controller["nvme_version"] = _nvme_version(controller.get("version", 0))
    namespace_payload = payloads.get("namespace", {})
    namespace = parse_identify_namespace(
        namespace_payload if isinstance(namespace_payload, dict) else {}
    )
    try:
        errors = parse_error_log(payloads.get("errors", []))
    except ValueError:
        errors = parse_error_log([])
    smart_available = command_status.get("smart") == "ok"
    return {
        "device": device,
        "health": _health_summary(smart, smart_available),
        "smart": smart,
        "controller": controller,
        "namespace": namespace,
        "errors": errors,
        "collection": {
            "mode": "read-only",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "command_status": command_status,
        },
    }


def discover_system_devices(
    runner: Callable = subprocess.run,
    which: Callable = shutil.which,
) -> list[dict]:
    """Run read-only discovery commands and return every visible namespace.

    Each command is isolated so an incompatible nvme-cli does not stop lsblk
    from reporting namespaces already visible to the kernel, and vice versa.
    """
    nvme_devices: list[dict] = []
    lsblk_devices: list[dict] = []
    errors: list[str] = []
    attempted = 0
    nvme = which("nvme")
    if nvme:
        attempted += 1
        try:
            completed = runner(
                [nvme, "list", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=8,
                check=True,
            )
            nvme_devices = parse_nvme_list_json(json.loads(completed.stdout))
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"nvme list: {exc}")

    lsblk = which("lsblk")
    if lsblk:
        attempted += 1
        try:
            completed = runner(
                [
                    lsblk,
                    "--json",
                    "--bytes",
                    "--output",
                    "NAME,PATH,MODEL,SERIAL,SIZE,TYPE,TRAN,REV,LOG-SEC",
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=True,
            )
            lsblk_devices = parse_lsblk_json(json.loads(completed.stdout))
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"lsblk: {exc}")

    devices = merge_devices(nvme_devices, lsblk_devices)
    if devices or attempted == 0 or len(errors) < attempted:
        return devices
    raise RuntimeError("; ".join(errors))
