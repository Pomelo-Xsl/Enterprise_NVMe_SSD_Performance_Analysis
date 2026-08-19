# 企业级 NVMe SSD 缓存与性能分析系统

本项目提供一个 FastAPI 驱动的 Web 管理界面，用于展示 NVMe SSD 的设备信息、测试任务、性能拐点、温度关联、SMART 健康状态和报告。

## 启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000
```

在浏览器打开 `http://127.0.0.1:8000`。

首次启动会自动创建 `nvme_analysis.db`，并生成一个可用于展示的历史测试任务。

## 安全说明

当前 V1.0 是可演示的安全原型：设备信息和测试结果为模拟数据，创建测试任务不会调用 `fio` 或向磁盘写数据。接入真实设备前，应增加设备白名单、管理员授权、双重确认和 `fio` 子进程隔离，以避免误覆盖数据。
