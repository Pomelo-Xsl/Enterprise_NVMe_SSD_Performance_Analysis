# Enterprise NVMe SSD Performance Analysis System

用于展示 NVMe SSD 的设备信息、测试任务、性能拐点、温度关联、SMART 健康状态和报告的 FastAPI Web 应用。

> 安全提示：当前版本是安全演示原型。创建测试任务只生成模拟数据，不会调用 `fio` 或写入任何磁盘。

## 环境要求

- Python 3.10 或更高版本
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
