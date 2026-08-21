# Enterprise NVMe SSD Performance Analysis System

用于展示 NVMe SSD 设备、测试任务、缓存置换算法、性能拐点、温度关联、
SMART 健康状态、异常告警和报告的 FastAPI Web 应用。系统包含 Web 控制台、
YAML 场景执行器、CLI、SQLite 持久化层以及可独立复用的分析算法。

> 安全提示：当前版本是安全演示原型。创建测试任务只生成模拟数据，不会调用 `fio` 或写入任何磁盘。

## 环境要求

- Python 3.9 或更高版本
- Linux（生产环境建议 Ubuntu 20.04+）或 macOS（本地开发）
- 可选：`nvme-cli`。仅用于只读扫描 NVMe 设备

## 本地启动

在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000`。首次启动会自动创建 `nvme_analysis.db`，并生成一条示例测试记录。

停止服务时，在启动终端按 `Ctrl+C`。

## 可选：只读扫描服务器 NVMe 设备

默认页面使用安全的模拟设备。Linux 上安装 `nvme-cli` 后，可显式启用只读扫描：

```bash
sudo apt update && sudo apt install -y nvme-cli
NVME_USE_SYSTEM_SCAN=1 uvicorn app:app --host 127.0.0.1 --port 8000
```

该开关只运行 `nvme list -o json`；它不会启动压测，也不会修改设备数据。

## Linux 生产部署（systemd + Nginx）

以下示例假定项目位于 `/opt/nvme-insight`，并以专用的低权限账户运行。

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin nvmeinsight
sudo mkdir -p /opt/nvme-insight
sudo chown -R nvmeinsight:nvmeinsight /opt/nvme-insight
```

将项目文件复制到 `/opt/nvme-insight` 后，以 `nvmeinsight` 用户创建虚拟环境并安装依赖：

```bash
sudo -u nvmeinsight python3 -m venv /opt/nvme-insight/.venv
sudo -u nvmeinsight /opt/nvme-insight/.venv/bin/pip install -r /opt/nvme-insight/requirements.txt
```

创建 `/etc/systemd/system/nvme-insight.service`：

```ini
[Unit]
Description=NVMe Insight Web Service
After=network.target

[Service]
User=nvmeinsight
Group=nvmeinsight
WorkingDirectory=/opt/nvme-insight
Environment=PYTHONUNBUFFERED=1
# 如需只读设备扫描，取消下一行注释：
# Environment=NVME_USE_SYSTEM_SCAN=1
ExecStart=/opt/nvme-insight/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 2
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

启动并设置开机自启：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nvme-insight
sudo systemctl status nvme-insight
```

查看日志：

```bash
sudo journalctl -u nvme-insight -f
```

### Nginx 反向代理

安装 Nginx：

```bash
sudo apt install -y nginx
```

创建 `/etc/nginx/sites-available/nvme-insight`：

```nginx
server {
    listen 80;
    server_name nvme-insight.example.com;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用并检查配置：

```bash
sudo ln -s /etc/nginx/sites-available/nvme-insight /etc/nginx/sites-enabled/nvme-insight
sudo nginx -t
sudo systemctl reload nginx
```

生产环境应使用受信任的 TLS 证书（例如 Certbot）并限制管理页面的访问来源。

## 升级

```bash
cd /opt/nvme-insight
sudo -u nvmeinsight /opt/nvme-insight/.venv/bin/pip install -r requirements.txt
sudo systemctl restart nvme-insight
```

升级前备份 `nvme_analysis.db`。不要将它或任何包含真实设备序列号的运行数据提交到公共仓库。

## 接入真实压测前

请先实现设备白名单、管理员授权、双重确认、审计日志和 `fio` 子进程隔离。禁止让 Web 请求直接对任意 `/dev/nvme*` 设备执行写入操作。

## 功能架构

当前版本提供以下业务能力：

- LRU-2、ARC、LIRS 缓存置换算法与相同负载下的横向仿真；
- 基于滑动时间窗口、读写权重和迟滞阈值的冷热页识别；
- 热命中、冷命中、未命中、脏页驱逐、干净页驱逐分解；
- P50、P95、P99、P999、P9999 延迟，块大小、读写占比、队列深度统计；
- 按时间窗聚合带宽和 IOPS，识别延迟毛刺、性能抖动和缓存异常；
- 解析 `fio --output-format=json`、fio 时序日志和 `nvme-cli` JSON；
- SQLite 保存场景结果与告警，支持告警过滤和确认；
- JSON、汇总 CSV、IO 样本 CSV、缓存算法 CSV 报告导出；
- 安全模拟任务、设备详情展开、返回导航、算法实验室、告警和报告页面。

所有内置工作负载都只在内存中生成样本。除非显式设置
`NVME_USE_SYSTEM_SCAN=1`，系统也不会调用本机的 `nvme-cli`。

## YAML 场景配置

默认配置位于 `config/default.yaml`，包含场景、工作负载、缓存、告警和日志配置。
可以复制此文件建立不同测试场景：

```yaml
scenario:
  name: mixed-cache-baseline
  profile: mixed-io
  runtime: 600
  cache_pages: 256
  safe_simulation: true
  tags: [baseline, nightly]

workload:
  kind: mixed
  count: 2000
  page_count: 8192
  read_ratio: 0.7
  block_size: 4096
  seed: 7

cache:
  algorithm: compare
  capacity_pages: 256
  hot_window_ms: 10000
  hot_threshold: 4.0
  cold_threshold: 2.0
  read_weight: 1.0
  write_weight: 1.5

alerts:
  temperature_warning: 65
  temperature_critical: 75
  latency_spike_zscore: 2.5
  bandwidth_drop_percent: 25

logging:
  directory: logs
  level: INFO
  max_bytes: 2000000
  backup_count: 5
```

系统拒绝 `safe_simulation: false`，并对时长、容量、块大小、阈值、日志轮转等参数
进行边界校验，避免配置错误直接进入执行链路。

## CLI 使用方法

先校验配置，再运行并保存完整报告：

```bash
python cli.py validate-config --config config/default.yaml
python cli.py run-scenario \
  --config config/default.yaml \
  --database nvme_analysis.db \
  --output scenario-result.json
```

兼容软件说明书约定的四个核心子命令：

```bash
# 生成安全模拟基准结果
python cli.py run-bench --runtime 600 --output result.json

# 自动识别普通性能点、规范化 IO 样本或 fio JSON
python cli.py analyze-result result.json

# 使用页访问序列对比 LRU-2、ARC、LIRS
python cli.py show-cache-stat --pages 1,2,1,3,1,4,2,1 --capacity 3

# 导出任务结果
python cli.py export-report result.json --format csv --output samples.csv
```

完整场景报告可按用途拆分：

```bash
python cli.py export-full-report scenario-result.json --section json --output report.json
python cli.py export-full-report scenario-result.json --section summary --output summary.csv
python cli.py export-full-report scenario-result.json --section samples --output io-samples.csv
python cli.py export-full-report scenario-result.json --section cache --output cache.csv
```

## Web API

主要接口如下：

| 接口 | 说明 |
| --- | --- |
| `GET /api/devices` | 获取模拟设备或只读扫描结果 |
| `GET /api/tasks` | 获取交互式安全模拟任务 |
| `POST /api/tasks` | 新建安全模拟任务 |
| `GET /api/simulations/cache` | 运行缓存算法对比 |
| `POST /api/scenarios/run` | 使用 JSON 形式的 YAML 等价配置运行场景 |
| `GET /api/scenarios/runs` | 查询持久化场景 |
| `GET /api/scenarios/runs/{id}` | 获取完整场景报告 |
| `GET /api/scenarios/runs/{id}/export/{section}` | 导出 JSON/summary/samples/cache |
| `GET /api/alerts` | 按运行、等级和确认状态查询告警 |
| `POST /api/alerts/{id}/acknowledge` | 确认告警 |

FastAPI 自动接口文档位于 `http://127.0.0.1:8000/docs`。

## 测试

运行全量单元与集成测试：

```bash
python -m unittest discover -s tests -v
```

测试覆盖顺序、随机、混合和冷热交替工作负载，三种缓存算法、冷热识别、
IO 统计、FIO/NVMe 解析、配置校验、报告导出、告警、SQLite 持久化和完整场景链路。

## 运行数据

- `nvme_analysis.db`：任务、场景结果和告警；
- `logs/nvme-insight.log`：分级运行日志并按大小轮转；
- `logs/nvme-alerts.log`：告警持久化日志；
- CLI `--output` 指定的 JSON/CSV：可直接交给绘图或数据分析工具。

数据库与日志是运行时文件，不应提交到公共代码仓库。生产升级前应先备份数据库。
