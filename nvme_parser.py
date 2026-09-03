"""Interpret identify and SMART data returned by nvme-cli.

Vendors and nvme-cli versions do not always agree on key spelling or whether a
number is encoded as text. Parsing is deliberately tolerant, but missing health
data remains distinguishable from a genuine zero-value counter.
"""

from __future__ import annotations
from models import DeviceInfo


def _number(data, *keys, default=0):
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value.split()[0].replace(",", ""))
            except ValueError:
                pass
    return default


def parse_smart_log(data: dict, device: DeviceInfo | None = None) -> DeviceInfo:
    """Normalise multiple nvme-cli smart-log JSON naming variants."""
    base = device or DeviceInfo(path=str(data.get("device", "unknown")))
    return DeviceInfo(
        path=base.path,
        model=base.model,
        serial=base.serial,
        firmware=base.firmware,
        capacity_bytes=base.capacity_bytes,
        temperature_c=_number(
            data, "temperature", "temperature_celsius", default=base.temperature_c or 0
        ),
        percentage_used=int(
            _number(
                data,
                "percentage_used",
                "percentage_used_percent",
                default=base.percentage_used or 0,
            )
        ),
        media_errors=int(_number(data, "media_errors", default=base.media_errors or 0)),
        error_log_entries=int(
            _number(
                data,
                "num_err_log_entries",
                "error_log_entries",
                default=base.error_log_entries or 0,
            )
        ),
    )


def parse_list_device(data: dict) -> DeviceInfo:
    return DeviceInfo(
        path=data.get("DevicePath", "unknown"),
        model=str(data.get("ModelNumber", "Unknown NVMe")).strip(),
        serial=str(data.get("SerialNumber", "—")).strip(),
        firmware=str(data.get("Firmware", "—")).strip(),
        capacity_bytes=int(_number(data, "UsedBytes", "PhysicalSize", default=0)),
    )


def device_risk(device: DeviceInfo) -> list[dict]:
    events = []
    for condition, severity, code, message in [
        (
            (device.temperature_c or 0) >= 75,
            "critical",
            "thermal-critical",
            "设备温度达到临界值",
        ),
        (
            (device.temperature_c or 0) >= 65,
            "warning",
            "thermal-warning",
            "设备温度偏高",
        ),
        (
            (device.percentage_used or 0) >= 90,
            "warning",
            "wear-warning",
            "介质寿命接近耗尽",
        ),
        ((device.media_errors or 0) > 0, "critical", "media-error", "检测到介质错误"),
        (
            (device.error_log_entries or 0) > 0,
            "warning",
            "error-log",
            "错误日志存在记录",
        ),
    ]:
        if condition:
            events.append({"severity": severity, "code": code, "message": message})
    return events


def parse_identify_controller(data: dict) -> dict:
    """Normalize fields returned by ``nvme id-ctrl -o json``."""

    volatile_write_cache = int(_number(data, "vwc", default=0))
    return {
        "vendor_id": int(_number(data, "vid", default=0)),
        "subsystem_vendor_id": int(_number(data, "ssvid", default=0)),
        "serial_number": str(data.get("sn", "—")).strip(),
        "model_number": str(data.get("mn", "Unknown NVMe")).strip(),
        "firmware_revision": str(data.get("fr", "—")).strip(),
        "recommended_arbitration_burst": int(_number(data, "rab", default=0)),
        "ieee_oui": int(_number(data, "ieee", default=0)),
        "controller_multi_path": int(_number(data, "cmic", default=0)),
        "maximum_data_transfer_size": int(_number(data, "mdts", default=0)),
        "controller_id": int(_number(data, "cntlid", default=0)),
        "version": int(_number(data, "ver", default=0)),
        "namespace_count": int(_number(data, "nn", default=0)),
        "volatile_write_cache_supported": bool(volatile_write_cache & 1),
        "optional_admin_commands": int(_number(data, "oacs", default=0)),
        "optional_nvm_commands": int(_number(data, "oncs", default=0)),
    }


def parse_identify_namespace(data: dict) -> dict:
    """Normalize fields returned by ``nvme id-ns -o json``."""

    formats = data.get("lbafs", [])
    formatted_lba_size = int(_number(data, "flbas", default=0)) & 0x0F
    selected_format = (
        formats[formatted_lba_size]
        if isinstance(formats, list) and formatted_lba_size < len(formats)
        else {}
    )
    lba_data_size_power = int(_number(selected_format, "ds", default=9))
    namespace_size = int(_number(data, "nsze", default=0))
    namespace_capacity = int(_number(data, "ncap", default=0))
    namespace_utilization = int(_number(data, "nuse", default=0))
    return {
        "namespace_size_lba": namespace_size,
        "namespace_capacity_lba": namespace_capacity,
        "namespace_utilization_lba": namespace_utilization,
        "lba_size_bytes": 1 << lba_data_size_power,
        "size_bytes": namespace_size * (1 << lba_data_size_power),
        "capacity_bytes": namespace_capacity * (1 << lba_data_size_power),
        "utilized_bytes": namespace_utilization * (1 << lba_data_size_power),
        "thin_provisioning": bool(int(_number(data, "nsfeat", default=0)) & 1),
        "formatted_lba_index": formatted_lba_size,
    }


def parse_error_log(data: list[dict] | dict) -> dict:
    """Summarize ``nvme error-log -o json`` output."""

    entries = data.get("errors", []) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError("error log entries must be a list")
    active_entries = []
    status_counts: dict[str, int] = {}
    for entry in entries:
        error_count = int(_number(entry, "error_count", default=0))
        if error_count <= 0:
            continue
        status = str(entry.get("status_field", entry.get("status", "unknown")))
        status_counts[status] = status_counts.get(status, 0) + 1
        active_entries.append(
            {
                "error_count": error_count,
                "submission_queue_id": int(
                    _number(entry, "sqid", "submission_queue_id", default=0)
                ),
                "command_id": int(_number(entry, "cmdid", default=0)),
                "status": status,
                "parameter_error_location": int(
                    _number(entry, "parm_error_location", default=0)
                ),
                "lba": int(_number(entry, "lba", default=0)),
                "namespace_id": int(_number(entry, "nsid", default=0)),
            }
        )
    return {
        "active_entry_count": len(active_entries),
        "total_error_count": sum(item["error_count"] for item in active_entries),
        "status_counts": status_counts,
        "entries": active_entries,
    }


def parse_device_bundle(bundle: dict) -> dict:
    """Parse a collected set of list, SMART, identify and error-log data."""

    listed = parse_list_device(bundle.get("list", {}))
    smart = parse_smart_log(bundle.get("smart", {}), listed)
    return {
        "device": smart.to_dict(),
        "controller": parse_identify_controller(bundle.get("identify_controller", {})),
        "namespace": parse_identify_namespace(bundle.get("identify_namespace", {})),
        "errors": parse_error_log(bundle.get("error_log", [])),
        "risks": device_risk(smart),
    }
