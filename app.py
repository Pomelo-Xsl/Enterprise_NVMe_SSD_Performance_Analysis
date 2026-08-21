"""FastAPI application for NVMe cache and performance result analysis."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import parse_application_config
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

app = FastAPI(title="NVMe Insight Analysis", version="1.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


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


def _system_devices() -> list[dict]:
    raw = subprocess.run(
        ["nvme", "list", "-o", "json"],
        capture_output=True,
        text=True,
        timeout=8,
        check=True,
    )
    found = json.loads(raw.stdout).get("Devices", [])
    return [
        {
            "path": device.get("DevicePath", "Unknown"),
            "model": device.get("ModelNumber", "Unknown NVMe"),
            "serial": device.get("SerialNumber", "—"),
            "firmware": device.get("Firmware", "—"),
            "capacity": f"{device.get('UsedBytes', 0) / 1e12:.2f} TB",
            "namespace": device.get("DevicePath", "").split("/")[-1],
            "pcie": "读取设备信息",
            "cache": "待读取",
            "health": "待检查",
            "source": "system-read-only",
        }
        for device in found
    ]


@app.get("/api/devices")
def devices():
    """Return read-only system discovery or safe demonstration metadata."""
    if os.getenv("NVME_USE_SYSTEM_SCAN") == "1" and shutil.which("nvme"):
        try:
            discovered = _system_devices()
            if discovered:
                return discovered
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            pass

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
        },
    ]


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
