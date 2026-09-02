# 企业级 NVMe SSD 缓存与性能分析系统

> Enterprise NVMe SSD Cache & Performance Analysis System
> 界面简称：NVMe Analyzer

企业级 NVMe SSD 缓存与性能分析系统用于接收 SSD Benchmark、SSD PressureTest、
FIO 等外部工具产生的结果，完成缓存算法对比、IO 统计、异常检测、告警和报告导出。

本项目定位为“结果分析平台”，不再提供磁盘 Benchmark、持续写入、随机写入或压力测试
执行功能。它不会启动 `fio`，也不会向 NVMe 设备写入数据。

## 核心能力

- 导入 FIO JSON、规范化 IO samples、Benchmark/PressureTest 性能 points；
- 分析 P50、P95、P99、P999、P9999 延迟和读写 IO 占比；
- 统计块大小、队列深度、带宽、IOPS 和唯一 LBA；
- 使用 LRU-2、ARC、LIRS 对相同访问流进行缓存算法对比；
- 识别热页、冷页、页面晋升和降级；
- 分解热命中、冷命中、脏页驱逐和干净页驱逐；
- 解析 `nvme-cli` SMART、控制器、Namespace 和错误日志 JSON；
- 检测性能抖动、带宽下降和 IO 延迟毛刺；
- 持久化分析结果与告警，支持确认告警；
- 导出 JSON、汇总 CSV、IO 样本 CSV 和缓存算法 CSV。

## 已移除的重复功能

以下能力应由独立的 SSD Benchmark 和 SSD PressureTest 系统负责：

- Web 新建测试任务；
- 短时突发写、持续顺序写、4K 随机写和 GC 压力测试；
- 测试进度、停止测试和测试任务数据库；
- CLI `run-bench`；
- 基准测试配置档案和相关任务审计代码。

缓存算法实验室仍会在内存中生成页访问序列，但不会访问块设备。这属于算法分析，
不是 SSD 性能测试。

## 环境要求与启动

- Python 3.9 或更高版本；
- Linux 或 macOS；
- 可选：`nvme-cli`，仅用于只读设备发现。

```bash
cd Enterprise_NVMe_SSD_Performance_Analysis
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000`，接口文档位于
`http://127.0.0.1:8000/docs`。

首次启动会创建 `nvme_analysis.db`。已有数据库中的旧 `tasks` 表不会被读取或修改，
以便升级时保留历史数据；新版本只使用分析记录和告警表。

## 导入已有测试结果

进入 Web 的“结果分析”页面，点击“导入 JSON”。系统根据数据结构自动判断格式。

### 规范化 IO 样本

该格式可以执行最完整的 IO、冷热页和缓存算法分析：

```json
{
  "samples": [
    {
      "timestamp_ms": 0,
      "lba": 1024,
      "size_bytes": 4096,
      "operation": "read",
      "latency_us": 85.2,
      "queue_depth": 16
    }
  ],
  "smart": {
    "temperature": 48,
    "percentage_used": 3,
    "media_errors": 0
  }
}
```

### Benchmark 或 PressureTest 性能点

```json
{
  "points": [
    {
      "minute": 0,
      "bandwidth": 6800,
      "iops": 520000,
      "latency": 120,
      "temperature": 42
    }
  ],
  "smart": {
    "temperature": 42,
    "percentage_used": 3
  }
}
```

也兼容旧系统的嵌套形式：

```json
{
  "name": "existing-benchmark",
  "result": {
    "points": []
  }
}
```

### FIO JSON

直接导入以下命令产生的文件：

```bash
fio workload.fio --output-format=json --output=fio-result.json
```

FIO 汇总格式不包含逐 IO LBA 时，系统只显示带宽、IOPS、读写量和延迟汇总，
不会虚构冷热页或缓存命中数据。

## 一键演示案例

首页右上角提供“演示案例”按钮，不需要准备测试文件。案例模拟电商订单数据库的
600 条 IO 访问，包含四个阶段：

1. 热点事务：订单索引和活跃订单页被频繁读取；
2. 混合报表：事务访问与历史数据查询同时运行；
3. 维护扫描：顺序扫描冷页，并产生队列压力和延迟毛刺；
4. 流量恢复：维护结束后，热点数据重新进入缓存。

加载案例后，系统会自动完成：

- P50/P95/P99/P999/P9999 延迟分析；
- LRU-2、ARC、LIRS 缓存算法对比；
- 冷热页与脏页驱逐统计；
- 性能抖动和延迟毛刺检测；
- SMART 温度告警；
- JSON 和 CSV 报告生成。

演示数据使用固定随机种子，每次生成结果一致，便于产品演示和验收测试。整个过程
只在内存中构造 IO 样本，不会访问真实 NVMe 设备。

## CLI

```bash
# 分析已有结果
python cli.py analyze-result benchmark-result.json

# 对给定页访问序列比较缓存算法
python cli.py show-cache-stat --pages 1,2,1,3,1,4,2,1 --capacity 3

# 校验并运行内存缓存分析场景
python cli.py validate-config --config config/default.yaml
python cli.py run-scenario \
  --config config/default.yaml \
  --database nvme_analysis.db \
  --output scenario-result.json

# 按用途导出分析报告
python cli.py export-full-report scenario-result.json --section json --output report.json
python cli.py export-full-report scenario-result.json --section summary --output summary.csv
python cli.py export-full-report scenario-result.json --section samples --output io-samples.csv
python cli.py export-full-report scenario-result.json --section cache --output cache.csv
```

## YAML 算法分析配置

默认配置位于 `config/default.yaml`。配置控制内存访问流、缓存容量、冷热阈值、
告警规则和日志轮转，不会生成真实设备 IO。

```yaml
scenario:
  name: mixed-cache-analysis
  safe_simulation: true

workload:
  kind: mixed
  count: 2000
  page_count: 8192
  read_ratio: 0.7
  block_size: 4096

cache:
  algorithm: compare
  capacity_pages: 256
  hot_window_ms: 10000
  hot_threshold: 4.0
  cold_threshold: 2.0
```

系统拒绝 `safe_simulation: false`，防止该分析服务被误用为磁盘测试执行器。

## Web API

| 接口                                            | 说明                         |
| ----------------------------------------------- | ---------------------------- |
| `GET /api/summary`                              | 获取分析平台概览             |
| `GET /api/devices`                              | 获取演示设备或只读扫描结果   |
| `POST /api/analysis/import`                     | 导入并持久化外部 JSON 结果   |
| `GET /api/simulations/cache`                    | 运行内存缓存算法对比         |
| `POST /api/scenarios/run`                       | 运行 YAML 等价的内存分析场景 |
| `GET /api/scenarios/runs`                       | 查询分析记录                 |
| `GET /api/scenarios/runs/{id}`                  | 获取完整分析结果             |
| `GET /api/scenarios/runs/{id}/export/{section}` | 导出报告                     |
| `GET /api/alerts`                               | 查询持久化告警               |
| `POST /api/alerts/{id}/acknowledge`             | 确认告警                     |

`/api/tasks`、`/api/tasks/{id}/stop` 等压测任务接口已经移除。

## 只读设备扫描

Linux 检测到 `nvme-cli` 或 `lsblk` 后会自动启用真实设备扫描。扫描过程只执行
`nvme list -o json` 和 `lsblk --json`，用于兼容不同版本的 nvme-cli JSON 结构并补齐
可能遗漏的 Namespace，不会运行测试或修改设备。

也可以显式开启：

```bash
NVME_USE_SYSTEM_SCAN=1 uvicorn app:app --host 127.0.0.1 --port 8000
```

需要强制使用演示设备时，可以显式关闭：

```bash
NVME_USE_SYSTEM_SCAN=0 uvicorn app:app --host 127.0.0.1 --port 8000
```

真实扫描启用后，如果命令失败或没有发现设备，接口会返回空列表并在页面显示诊断提示，
不再静默回退为两块演示设备，以免将扫描失败误判为真实设备数量。

## 测试

```bash
python -m unittest discover -s tests -v
```

测试覆盖缓存算法、冷热识别、IO 统计、FIO/NVMe 解析、外部结果导入、配置校验、
异常检测、告警、持久化和报告导出。测试代码用于验证分析系统正确性，
不执行 SSD Benchmark 或 PressureTest。

## Linux 部署

```ini
[Unit]
Description=Enterprise NVMe SSD Cache and Performance Analysis Service
After=network.target

[Service]
User=nvmeinsight
Group=nvmeinsight
WorkingDirectory=/opt/nvme-insight
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/nvme-insight/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 2
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Nginx 将请求反向代理到 `http://127.0.0.1:8000` 即可。生产环境应配置 TLS、
访问控制和上传文件大小限制。

## 运行数据

- `nvme_analysis.db`：分析结果和告警；
- `logs/nvme-insight.log`：分析运行日志；
- `logs/nvme-alerts.log`：告警日志；
- 导出的 JSON/CSV：供 Excel、Python、Grafana 等工具继续处理。

数据库、日志、真实设备序列号和外部测试结果不应提交到公共仓库。
