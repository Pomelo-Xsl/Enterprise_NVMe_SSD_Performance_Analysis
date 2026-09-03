"""HTTP entry point for the NVMe analysis console.

Routes in this file expose device inventory, imported-result analysis, cache
simulation, alerts and report downloads. Device discovery remains read-only;
the service does not launch a benchmark or pressure workload.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import parse_application_config
from demo_case import DEMO_NAME, build_demo_payload
from device_discovery import collect_device_details, discover_system_devices
from exporters import (
    cache_comparison_csv,
    io_samples_csv,
    report_json,
    report_summary_csv,
)
from ingestion import ingest_result
from persistence import Repository
from scenario_runner import run_configured_scenario
from simulation import run_simulation


ROOT = Path(__file__).parent
DATABASE_PATH = Path(os.getenv("NVME_ANALYSIS_DB", str(ROOT / "nvme_analysis.db")))
REPOSITORY = Repository(DATABASE_PATH)
LOGGER = logging.getLogger(__name__)
BUILD_VERSION = "1.2.0"

app = FastAPI(
    title="企业级 NVMe SSD 缓存与性能分析系统",
    description="NVMe SSD 测试结果导入、缓存算法对比、IO 分析与异常告警平台",
    version=BUILD_VERSION,
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def prevent_stale_frontend_assets(request: Request, call_next):
    """Force browsers and reverse proxies to revalidate the local dashboard."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    response.headers["X-NVMe-Analyzer-Version"] = BUILD_VERSION
    return response


class ImportRequest(BaseModel):
    """External result envelope accepted by the Web analysis workflow."""

    name: str = Field(default="imported-result", min_length=2, max_length=100)
    cache_pages: int = Field(default=128, ge=1, le=1_000_000)
    payload: dict


@app.on_event("startup")
def startup() -> None:
    REPOSITORY.initialize()


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/version")
def application_version():
    return {"version": BUILD_VERSION, "device_detail_view": True}


def _system_devices() -> list[dict]:
    return discover_system_devices()


def _system_scan_enabled() -> bool:
    """Auto-enable safe discovery on Linux while allowing an explicit opt-out."""
    configured = os.getenv("NVME_USE_SYSTEM_SCAN", "auto").strip().lower()
    if configured in {"0", "false", "no", "off", "demo"}:
        return False
    if configured in {"1", "true", "yes", "on"}:
        return True
    return os.name == "posix" and bool(shutil.which("nvme") or shutil.which("lsblk"))


@app.get("/api/devices")
def devices():
    """Return read-only system discovery or safe demonstration metadata."""
    if _system_scan_enabled():
        try:
            return _system_devices()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            LOGGER.warning("NVMe read-only discovery failed: %s", error)
            return []

    return _demo_devices()


def _demo_devices() -> list[dict]:
    """Return stable read-only metadata when system discovery is disabled."""
    return [
        {
            "path": "/dev/nvme0n1",
            "model": "Samsung PM9A3 3.84TB",
            "serial": "S64DNF0R123456",
            "firmware": "GDC5902Q",
            "capacity": "3.84 TB",
            "namespace": "nvme0n1",
            "pcie": "PCIe 4.0 x4",
            "cache": "Supported · Enabled",
            "health": "良好",
            "source": "demonstration",
            "sector_size": 4096,
            "capacity_bytes": 3_840_000_000_000,
        },
        {
            "path": "/dev/nvme1n1",
            "model": "KIOXIA CD8-V 1.92TB",
            "serial": "YADC0A987654",
            "firmware": "0105",
            "capacity": "1.92 TB",
            "namespace": "nvme1n1",
            "pcie": "PCIe 4.0 x4",
            "cache": "Supported · Enabled",
            "health": "良好",
            "source": "demonstration",
            "sector_size": 4096,
            "capacity_bytes": 1_920_000_000_000,
        },
    ]


def _demo_device_detail(device: dict) -> dict:
    """Provide a complete UI example without touching a local block device."""
    second = device["namespace"] == "nvme1n1"
    smart = {
        "critical_warning": 0,
        "temperature_c": 39 if second else 42,
        "available_spare_percent": 100,
        "spare_threshold_percent": 10,
        "percentage_used": 7 if second else 12,
        "life_remaining_percent": 93 if second else 88,
        "data_units_read": 12_840_300 if second else 28_450_200,
        "data_units_written": 8_920_100 if second else 21_780_400,
        "data_read_bytes": (12_840_300 if second else 28_450_200) * 512_000,
        "data_written_bytes": (8_920_100 if second else 21_780_400) * 512_000,
        "host_read_commands": 38_214_090 if second else 74_930_120,
        "host_write_commands": 24_908_330 if second else 62_108_870,
        "controller_busy_minutes": 4_820 if second else 9_240,
        "power_cycles": 48 if second else 76,
        "power_on_hours": 8_640 if second else 15_320,
        "unsafe_shutdowns": 1 if second else 2,
        "media_errors": 0,
        "error_log_entries": 0,
        "warning_temperature_minutes": 0,
        "critical_temperature_minutes": 0,
    }
    return {
        "device": device,
        "health": {"level": "healthy", "label": "健康", "risks": []},
        "smart": smart,
        "controller": {
            "vendor_id": 5197 if second else 5198,
            "subsystem_vendor_id": 5197 if second else 5198,
            "controller_id": 1,
            "namespace_count": 1,
            "nvme_version": "1.4.0",
            "maximum_data_transfer_size": 7,
            "volatile_write_cache_supported": True,
        },
        "namespace": {
            "lba_size_bytes": device["sector_size"],
            "size_bytes": device["capacity_bytes"],
            "capacity_bytes": device["capacity_bytes"],
            "utilized_bytes": int(device["capacity_bytes"] * (0.61 if second else 0.74)),
            "thin_provisioning": False,
            "formatted_lba_index": 0,
        },
        "errors": {
            "active_entry_count": 0,
            "total_error_count": 0,
            "status_counts": {},
            "entries": [],
        },
        "collection": {
            "mode": "demonstration-read-only",
            "collected_at": "演示数据",
            "command_status": {
                "smart": "demo",
                "controller": "demo",
                "namespace": "demo",
                "errors": "demo",
            },
        },
    }


@app.get("/api/devices/{namespace}/details")
def device_details(namespace: str):
    """Return read-only SMART and identify information for one known namespace."""
    discovered = devices()
    device = next(
        (item for item in discovered if item.get("namespace") == namespace),
        None,
    )
    if device is None:
        raise HTTPException(404, "NVMe Namespace 不存在或当前不可见")
    if not _system_scan_enabled():
        return _demo_device_detail(device)
    return collect_device_details(device)


@app.get("/api/summary")
def overview_summary():
    REPOSITORY.initialize()
    runs = REPOSITORY.list_runs(500)
    open_alerts = REPOSITORY.list_alerts(acknowledged=False, limit=1000)
    return {
        "devices": len(devices()),
        "analysis_runs": len(runs),
        "open_alerts": len(open_alerts),
        "cache_algorithms": 3,
        "mode": "结果分析模式",
    }


@app.post("/api/analysis/import")
def import_analysis(request: ImportRequest):
    try:
        result = ingest_result(
            request.payload,
            name=request.name,
            cache_pages=request.cache_pages,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error

    REPOSITORY.initialize()
    run_id = REPOSITORY.save_run(result)
    result["run_id"] = run_id
    return result


@app.post("/api/demo/load")
def load_demo_case():
    """Load a deterministic enterprise database example into the analysis UI."""
    result = ingest_result(
        build_demo_payload(),
        name=DEMO_NAME,
        cache_pages=64,
    )
    REPOSITORY.initialize()
    run_id = REPOSITORY.save_run(result)
    result["run_id"] = run_id
    return result


@app.get("/api/simulations/cache")
def cache_simulation(
    workload: Literal["sequential", "random", "mixed", "hot-cold"] = "mixed",
    count: int = 200,
    capacity: int = 32,
    seed: int = 7,
):
    """Compare algorithms in memory; this endpoint performs no device IO."""
    if not 1 <= count <= 10_000 or not 1 <= capacity <= 100_000:
        raise HTTPException(422, "count 或 capacity 超出安全模拟范围")
    return run_simulation(workload, count, capacity, seed)


@app.post("/api/scenarios/run")
def run_scenario(configuration: dict):
    """Run a configuration-driven in-memory cache analysis scenario."""
    try:
        parsed = parse_application_config(configuration)
        result = run_configured_scenario(parsed)
    except (TypeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    REPOSITORY.initialize()
    result["run_id"] = REPOSITORY.save_run(result)
    return result


@app.get("/api/scenarios/runs")
def scenario_runs(limit: int = 50):
    REPOSITORY.initialize()
    return REPOSITORY.list_runs(limit)


@app.get("/api/scenarios/runs/{run_id}")
def scenario_run(run_id: int):
    REPOSITORY.initialize()
    result = REPOSITORY.get_run(run_id)
    if result is None:
        raise HTTPException(404, "分析记录不存在")
    return result


@app.get("/api/scenarios/runs/{run_id}/export/{section}")
def export_scenario_run(
    run_id: int,
    section: Literal["json", "summary", "samples", "cache"],
):
    result = scenario_run(run_id)
    if section == "summary":
        content = report_summary_csv(result)
        media_type = "text/csv; charset=utf-8"
        suffix = "summary.csv"
    elif section == "samples":
        content = io_samples_csv(result.get("samples", []))
        media_type = "text/csv; charset=utf-8"
        suffix = "samples.csv"
    elif section == "cache":
        content = cache_comparison_csv(result.get("cache_comparison", {}))
        media_type = "text/csv; charset=utf-8"
        suffix = "cache.csv"
    else:
        content = report_json(result)
        media_type = "application/json; charset=utf-8"
        suffix = "report.json"

    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename=nvme-analysis-{run_id}-{suffix}"
        },
    )


@app.get("/api/alerts")
def persisted_alerts(
    run_id: Optional[int] = None,
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    limit: int = 100,
):
    REPOSITORY.initialize()
    return REPOSITORY.list_alerts(
        run_id=run_id,
        severity=severity,
        acknowledged=acknowledged,
        limit=limit,
    )


@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int):
    REPOSITORY.initialize()
    if not REPOSITORY.acknowledge_alert(alert_id):
        raise HTTPException(404, "告警不存在或已确认")
    return {"id": alert_id, "acknowledged": True}
