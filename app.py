"""Enterprise NVMe SSD Cache & Performance Analysis System."""
from __future__ import annotations

import asyncio
import json
import os
import random
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
DB = ROOT / "nvme_analysis.db"
app = FastAPI(title="NVMe Insight", version="1.0.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


def connection():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with connection() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS tasks (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, device TEXT NOT NULL,
          test_type TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
          runtime INTEGER NOT NULL, block_size TEXT NOT NULL, io_depth INTEGER NOT NULL,
          jobs INTEGER NOT NULL, progress INTEGER NOT NULL DEFAULT 0, result TEXT)
        """)
        if "progress" not in {r["name"] for r in con.execute("PRAGMA table_info(tasks)")}:
            con.execute("ALTER TABLE tasks ADD COLUMN progress INTEGER NOT NULL DEFAULT 0")
        if not con.execute("SELECT 1 FROM tasks LIMIT 1").fetchone():
            seed = build_result("/dev/nvme0n1", "持续顺序写", 1800)
            con.execute("""INSERT INTO tasks (name,device,test_type,status,created_at,runtime,block_size,io_depth,jobs,progress,result)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", ("企业盘持续写入基线", "/dev/nvme0n1", "持续顺序写", "已完成", now(), 1800, "128K", 32, 1, 100, json.dumps(seed)))


def now(): return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def build_result(device: str, test_type: str, runtime: int):
    random.seed(f"{device}{test_type}{runtime}")
    points, capacity = [], 6900 if "顺序" in test_type or "突发" in test_type else 550
    knee = max(6, int(runtime / 60 * .37))
    for minute in range(max(12, min(30, int(runtime / 60) + 1))):
        after = minute >= knee
        perf = capacity * (.62 if after else 1) * random.uniform(.95, 1.04)
        points.append({"minute": minute, "bandwidth": round(perf), "iops": round(perf * (74 if capacity > 1000 else 1000)), "latency": round((118 if not after else 310) * random.uniform(.88, 1.14)), "temperature": round(39 + minute * 1.1 + (3 if after else 0), 1)})
    peak, steady = max(p["bandwidth"] for p in points), round(sum(p["bandwidth"] for p in points[knee:]) / len(points[knee:]))
    return {"device": device, "cache": "Enabled", "points": points, "knee": knee,
      "summary": {"peak_bw": peak, "steady_bw": steady, "drop": round((1-steady/peak)*100, 1), "knee_gb": knee*60*peak/1024, "random_iops": 528000, "p99": 812, "p9999": 4700, "max_temp": max(p["temperature"] for p in points), "recovery": 94.2},
      "smart": {"temperature": max(p["temperature"] for p in points), "percentage_used": 3, "available_spare": 100, "media_errors": 0, "data_written": "1.83 TB"}}


class TaskInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    device: str
    test_type: Literal["短时突发写", "持续顺序写", "4K 随机写", "GC 压力测试"]
    runtime: int = Field(ge=60, le=7200)
    block_size: str = "128K"
    io_depth: int = Field(ge=1, le=256, default=32)
    jobs: int = Field(ge=1, le=32, default=1)


@app.on_event("startup")
def startup(): init_db()


@app.get("/", response_class=HTMLResponse)
def index(): return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/devices")
def devices():
    if os.getenv("NVME_USE_SYSTEM_SCAN") == "1" and shutil.which("nvme"):
        try:
            raw = subprocess.run(["nvme", "list", "-o", "json"], capture_output=True, text=True, timeout=8, check=True)
            found = json.loads(raw.stdout).get("Devices", [])
            if found:
                return [{"path": d.get("DevicePath", "Unknown"), "model": d.get("ModelNumber", "Unknown NVMe"), "serial": d.get("SerialNumber", "—"), "firmware": d.get("Firmware", "—"), "capacity": f"{d.get('UsedBytes', 0)/1e12:.2f} TB", "namespace": d.get("DevicePath", "").split("/")[-1], "pcie": "读取设备信息", "cache": "待读取", "health": "待检查", "source": "system"} for d in found]
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            pass
    return [{"path":"/dev/nvme0n1","model":"Samsung PM9A3 3.84TB","serial":"S64DNF0R123456","firmware":"GDC5902Q","capacity":"3.84 TB","namespace":"nvme0n1","pcie":"PCIe 4.0 x4","cache":"Supported · Enabled","health":"良好"},
            {"path":"/dev/nvme1n1","model":"KIOXIA CD8-V 1.92TB","serial":"YADC0A987654","firmware":"0105","capacity":"1.92 TB","namespace":"nvme1n1","pcie":"PCIe 4.0 x4","cache":"Supported · Enabled","health":"良好"}]


@app.get("/api/tasks")
def tasks():
    with connection() as con: return [dict(r) | {"result": json.loads(r["result"]) if r["result"] else None} for r in con.execute("SELECT * FROM tasks ORDER BY id DESC")]


@app.get("/api/summary")
def summary():
    with connection() as con:
        counts = {r["status"]: r["total"] for r in con.execute("SELECT status, COUNT(*) total FROM tasks GROUP BY status")}
    return {"devices": len(devices()), "completed": counts.get("已完成", 0), "running": counts.get("运行中", 0), "mode": "演示模式（安全）" if os.getenv("NVME_USE_SYSTEM_SCAN") != "1" else "系统扫描模式（只读）"}


@app.post("/api/tasks", status_code=201)
async def create_task(data: TaskInput):
    with connection() as con:
        cur = con.execute("""INSERT INTO tasks (name,device,test_type,status,created_at,runtime,block_size,io_depth,jobs,progress)
          VALUES (?,?,?,?,?,?,?,?,?,?)""", (data.name, data.device, data.test_type, "运行中", now(), data.runtime, data.block_size, data.io_depth, data.jobs, 5))
        task_id = cur.lastrowid
    asyncio.create_task(finish_task(task_id, data))
    return {"id": task_id, "status": "运行中"}


async def finish_task(task_id: int, data: TaskInput):
    for progress in (25, 55, 80):
        await asyncio.sleep(1)
        with connection() as con:
            row = con.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row or row["status"] == "已停止": return
            con.execute("UPDATE tasks SET progress=? WHERE id=?", (progress, task_id))
    await asyncio.sleep(1)
    result = build_result(data.device, data.test_type, data.runtime)
    with connection() as con: con.execute("UPDATE tasks SET status=?,progress=?,result=? WHERE id=?", ("已完成", 100, json.dumps(result), task_id))


@app.get("/api/tasks/{task_id}")
def task(task_id: int):
    with connection() as con: row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row: raise HTTPException(404, "任务不存在")
    d = dict(row); d["result"] = json.loads(d["result"]) if d["result"] else None
    return d


@app.post("/api/tasks/{task_id}/stop")
def stop_task(task_id: int):
    with connection() as con:
        row = con.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row: raise HTTPException(404, "任务不存在")
        if row["status"] != "运行中": raise HTTPException(409, "只有运行中的任务可以停止")
        con.execute("UPDATE tasks SET status=? WHERE id=?", ("已停止", task_id))
    return {"id": task_id, "status": "已停止"}


@app.get("/api/tasks/{task_id}/report")
def report(task_id: int):
    item = task(task_id)
    if not item["result"]: raise HTTPException(409, "测试尚未完成")
    s = item["result"]["summary"]
    text = f"""NVMe SSD 缓存与性能分析报告\n{'='*42}\n任务：{item['name']}\n设备：{item['device']}\n类型：{item['test_type']}\n生成时间：{now()}\n\n峰值顺序写带宽：{s['peak_bw']} MB/s\n稳态带宽：{s['steady_bw']} MB/s\n性能下降：{s['drop']}%\n性能拐点：{s['knee_gb']:.0f} GB\n4K 随机写：{s['random_iops']:,} IOPS\nP99 延迟：{s['p99']} μs\n最高温度：{s['max_temp']} ℃\nIdle 10 分钟恢复率：{s['recovery']}%\n\n结论：设备初期缓存性能较高，持续写入后进入稳定阶段；未发现 SMART 介质错误。\n"""
    return Response(text, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=nvme-report-{task_id}.txt"})
