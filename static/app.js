const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  tasks: [],
  devices: [],
  selectedTask: null,
  taskFilter: "all",
  view: "overview",
  history: [],
  cacheResult: null,
  charts: new Map(),
};

const TITLES = {
  overview: "性能概览",
  devices: "设备管理",
  tasks: "测试任务",
  analysis: "性能分析",
  "cache-lab": "缓存算法实验室",
  alerts: "告警中心",
  reports: "报告中心",
};

function installExtendedStyles() {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "/static/extended.css";
  document.head.append(link);
}

function ensureToast() {
  let toast = $("#toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    document.body.prepend(toast);
  }
  return toast;
}

function notify(message, duration = 2600) {
  const toast = ensureToast();
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(notify.timer);
  notify.timer = window.setTimeout(() => {
    toast.classList.remove("visible");
  }, duration);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch {
      // Keep the generic error when the response has no JSON body.
    }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function addNavigationItem(view, icon, label) {
  const navigation = $("nav");
  if ($(`[data-view="${view}"]`, navigation)) {
    return;
  }
  const button = document.createElement("button");
  button.dataset.view = view;
  button.innerHTML = `${icon}　${label}`;
  navigation.append(button);
}

function createSection(id, content) {
  let section = $(`#${id}`);
  if (section) {
    return section;
  }
  section = document.createElement("section");
  section.id = id;
  section.className = "view";
  section.innerHTML = content;
  $("main").append(section);
  return section;
}

function installFeaturePages() {
  addNavigationItem("cache-lab", "◇", "缓存算法");
  addNavigationItem("alerts", "△", "告警中心");
  addNavigationItem("reports", "▤", "报告中心");

  createSection(
    "cache-lab",
    `
      <div class="section-head">
        <div>
          <h2>缓存算法实验室</h2>
          <p>对比 LRU‑2、ARC 和 LIRS 的命中与驱逐表现</p>
        </div>
        <button class="primary" id="run-cache-simulation">运行仿真</button>
      </div>
      <div class="panel">
        <div class="lab-form">
          <label>工作负载
            <select id="simulation-workload">
              <option value="mixed">混合读写</option>
              <option value="random">随机 IO</option>
              <option value="sequential">顺序 IO</option>
              <option value="hot-cold">冷热交替</option>
            </select>
          </label>
          <label>样本数
            <input id="simulation-count" type="number" min="20" max="10000" value="500">
          </label>
          <label>缓存页数
            <input id="simulation-capacity" type="number" min="1" max="100000" value="64">
          </label>
          <label>随机种子
            <input id="simulation-seed" type="number" value="7">
          </label>
        </div>
      </div>
      <div id="cache-summary" class="algorithm-grid"></div>
      <div class="grid">
        <div class="panel">
          <div class="panel-head">
            <h3>命中率与脏页驱逐</h3>
            <span class="tag teal">CACHE</span>
          </div>
          <div id="cache-chart" class="chart-small"></div>
        </div>
        <div class="panel">
          <div class="panel-head">
            <h3>冷热页统计</h3>
            <span class="tag">HEAT</span>
          </div>
          <div id="heat-content" class="empty-state">运行仿真后显示结果</div>
        </div>
      </div>
    `,
  );

  createSection(
    "alerts",
    `
      <div class="section-head">
        <div>
          <h2>告警中心</h2>
          <p>查看并确认健康与性能风险</p>
        </div>
        <div class="toolbar">
          <select id="alert-severity">
            <option value="">全部等级</option>
            <option value="critical">严重</option>
            <option value="warning">警告</option>
            <option value="info">信息</option>
          </select>
          <button class="secondary" id="refresh-alerts">刷新</button>
        </div>
      </div>
      <div id="alert-summary" class="summary-grid extended"></div>
      <div class="panel table-panel">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>等级</th>
              <th>事件</th>
              <th>来源</th>
              <th>数值 / 阈值</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody id="alert-list"></tbody>
        </table>
      </div>
    `,
  );

  createSection(
    "reports",
    `
      <div class="section-head">
        <div>
          <h2>报告中心</h2>
          <p>导出任务报告与配置场景运行记录</p>
        </div>
        <button class="secondary" id="refresh-reports">刷新</button>
      </div>
      <div class="panel table-panel">
        <table>
          <thead>
            <tr>
              <th>记录</th>
              <th>设备 / 场景</th>
              <th>类型</th>
              <th>样本数</th>
              <th>状态</th>
              <th>导出</th>
            </tr>
          </thead>
          <tbody id="report-list"></tbody>
        </table>
      </div>
    `,
  );

  if (!$("#task-filter")) {
    const toolbar = document.createElement("div");
    toolbar.className = "toolbar";
    toolbar.innerHTML = `
      <select id="task-filter" aria-label="任务状态筛选">
        <option value="all">全部状态</option>
        <option value="运行中">运行中</option>
        <option value="已完成">已完成</option>
        <option value="已停止">已停止</option>
      </select>
    `;
    const createButton = $("#new-task-2");
    if (createButton) {
      toolbar.append(createButton);
    }
    $("#tasks .section-head").append(toolbar);
  }
}

function ensureBackButton() {
  let button = $("#page-back");
  if (!button) {
    button = document.createElement("button");
    button.id = "page-back";
    button.className = "back-button hidden";
    $("#page-title").parentElement.prepend(button);
  }
  button.onclick = goBack;
  return button;
}

function showView(view, options = {}) {
  const { remember = false, fallback = "overview" } = options;
  if (remember && state.view !== view) {
    state.history.push(state.view || fallback);
  }
  state.view = view;
  $$(".view").forEach((section) => {
    section.classList.toggle("active", section.id === view);
  });
  $$("nav button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  $("#page-title").textContent = TITLES[view] || "NVMe Insight";

  const back = ensureBackButton();
  back.classList.toggle("hidden", view === "overview");
  back.textContent = state.history.length
    ? `← 返回${TITLES[state.history[state.history.length - 1]] || "上一页"}`
    : "← 返回性能概览";

  if (view === "devices") {
    loadDevices();
  } else if (view === "alerts") {
    loadAlerts();
  } else if (view === "reports") {
    loadReports();
  }
}

function goBack() {
  const previous = state.history.pop() || "overview";
  showView(previous);
  notify(`已返回${TITLES[previous] || "上一页"}`);
}

function disposeChart(id) {
  const chart = state.charts.get(id);
  if (chart) {
    chart.dispose();
    state.charts.delete(id);
  }
}

function renderLineChart(elementId, points) {
  const element = $(`#${elementId}`);
  if (!element || typeof echarts === "undefined") {
    return;
  }
  disposeChart(elementId);
  const chart = echarts.init(element);
  state.charts.set(elementId, chart);
  chart.setOption({
    grid: { left: 50, right: 50, top: 35, bottom: 30 },
    tooltip: { trigger: "axis" },
    legend: {
      data: ["带宽 MB/s", "温度 ℃"],
      textStyle: { color: "#aebdb6" },
    },
    xAxis: {
      type: "category",
      data: points.map((point) => `${point.minute ?? 0}m`),
      axisLabel: { color: "#87958f" },
      axisLine: { lineStyle: { color: "#33443d" } },
    },
    yAxis: [
      {
        axisLabel: { color: "#87958f" },
        splitLine: { lineStyle: { color: "#1c2c26" } },
      },
      {
        min: 30,
        max: 90,
        axisLabel: { color: "#87958f" },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "带宽 MB/s",
        type: "line",
        smooth: true,
        symbol: "none",
        data: points.map((point) => point.bandwidth),
        lineStyle: { color: "#61e1ad", width: 2 },
        areaStyle: { color: "rgba(97,225,173,.1)" },
      },
      {
        name: "温度 ℃",
        type: "line",
        smooth: true,
        yAxisIndex: 1,
        symbol: "none",
        data: points.map((point) => point.temperature),
        lineStyle: { color: "#f6b75a", width: 2 },
      },
    ],
  });
}

function metricCard(label, value, hint) {
  return `
    <div class="metric">
      <p>${label}</p>
      <b>${value}</b>
      <small>${hint}</small>
    </div>
  `;
}

function renderOverview() {
  const task = state.selectedTask;
  if (!task?.result) {
    return;
  }
  const result = task.result;
  const summary = result.summary;
  $("#metrics").innerHTML = [
    metricCard("峰值写带宽", `${summary.peak_bw} MB/s`, "缓存阶段"),
    metricCard("稳态写带宽", `${summary.steady_bw} MB/s`, "持续写入"),
    metricCard(
      "性能拐点",
      `${Math.round(summary.knee_gb)} GB`,
      `下降 ${summary.drop}%`,
    ),
    metricCard("最高温度", `${summary.max_temp} ℃`, "SMART 采样"),
  ].join("");

  renderLineChart("performance-chart", result.points);
  const analysis = result.analysis || {};
  $("#insight").innerHTML = `
    设备在累计写入 <b>${Math.round(summary.knee_gb)} GB</b> 后出现性能拐点，
    峰值 <b>${summary.peak_bw} MB/s</b>，稳态 <b>${summary.steady_bw} MB/s</b>。
    当前稳定性等级为 <b>${analysis.stability || "待分析"}</b>，
    带宽趋势为 <b>${analysis.trend?.direction || "待分析"}</b>，
    检测到 <b>${result.anomalies?.length || 0}</b> 个异常事件。
  `;

  const labels = {
    temperature: "温度",
    percentage_used: "已用寿命",
    available_spare: "可用备用空间",
    media_errors: "介质错误",
    data_written: "主机写入量",
  };
  $("#health").innerHTML = Object.entries(result.smart || {})
    .map(([key, value]) => {
      const suffix = ["percentage_used", "available_spare"].includes(key)
        ? "%"
        : "";
      return `<div><span>${labels[key] || key}</span><b>${value}${suffix}</b></div>`;
    })
    .join("");
}

async function loadTasks() {
  state.tasks = await api("/api/tasks");
  if (
    !state.selectedTask ||
    !state.tasks.some((task) => task.id === state.selectedTask.id)
  ) {
    state.selectedTask =
      state.tasks.find((task) => task.result) || state.tasks[0];
  } else {
    state.selectedTask = state.tasks.find(
      (task) => task.id === state.selectedTask.id,
    );
  }
  renderTasks();
  renderAnalysis();
  renderOverview();
}

function renderTasks() {
  const visible =
    state.taskFilter === "all"
      ? state.tasks
      : state.tasks.filter((task) => task.status === state.taskFilter);
  $("#task-list").innerHTML = visible.length
    ? visible
        .map(
          (task) => `
        <tr>
          <td>
            ${task.name}
            ${
              task.status === "运行中"
                ? `
              <div class="progress"><i style="width:${task.progress}%"></i></div>
            `
                : ""
            }
          </td>
          <td>${task.device}</td>
          <td>${task.test_type}</td>
          <td>${task.block_size} · QD${task.io_depth}</td>
          <td>${task.created_at}</td>
          <td>
            <span class="status ${task.status === "运行中" ? "running" : ""}">
              ${task.status}${task.status === "运行中" ? ` ${task.progress}%` : ""}
            </span>
          </td>
          <td>
            ${
              task.result
                ? `<button class="link-button task-result" data-id="${task.id}">查看 →</button>`
                : task.status === "运行中"
                  ? `<button class="stop stop-task" data-id="${task.id}">停止</button>`
                  : "—"
            }
          </td>
        </tr>
      `,
        )
        .join("")
    : `<tr><td colspan="7" class="empty-state">暂无匹配任务</td></tr>`;
}

function renderAnalysis() {
  const completed = state.tasks.filter((task) => task.result);
  $("#analysis-select").innerHTML = completed
    .map(
      (task) => `
      <option value="${task.id}" ${task.id === state.selectedTask?.id ? "selected" : ""}>
        #${task.id} · ${task.name}
      </option>
    `,
    )
    .join("");
  if (!state.selectedTask?.result) {
    $("#analysis-content").innerHTML =
      `<div class="panel empty-state">暂无已完成结果</div>`;
    return;
  }
  const task = state.selectedTask;
  const result = task.result;
  const summary = result.summary;
  const analysis = result.analysis || {};
  $("#analysis-subtitle").textContent =
    `${task.device} · ${task.test_type} · ${task.created_at}`;
  $("#analysis-content").innerHTML = `
    <div class="summary-grid">
      ${metricCard("峰值带宽", `${summary.peak_bw} MB/s`, "Peak")}
      ${metricCard("稳态带宽", `${summary.steady_bw} MB/s`, "Steady")}
      ${metricCard("性能下降", `${summary.drop}%`, "Drop")}
      ${metricCard("P99 延迟", `${summary.p99} μs`, "QoS")}
      ${metricCard("稳定性", analysis.stability || "—", "Statistics")}
      ${metricCard("异常事件", result.anomalies?.length || 0, "Anomaly")}
    </div>
    <div class="panel">
      <div class="panel-head">
        <div>
          <h3>性能与温度曲线</h3>
          <p>性能拐点与热量关联分析</p>
        </div>
        <div class="download-group">
          <a href="/api/tasks/${task.id}/report">TXT</a>
          <a href="/api/tasks/${task.id}/export/csv">CSV</a>
          <a href="/api/tasks/${task.id}/export/json">JSON</a>
        </div>
      </div>
      <div id="analysis-chart" class="chart"></div>
    </div>
  `;
  requestAnimationFrame(() => renderLineChart("analysis-chart", result.points));
}

async function loadDevices() {
  const list = $("#device-list");
  list.innerHTML = `<div class="panel skeleton"></div>`;
  try {
    state.devices = await api("/api/devices");
    list.innerHTML = state.devices
      .map(
        (device, index) => `
      <article class="panel device" tabindex="0" role="button" aria-expanded="false" data-index="${index}">
        <div>
          <h3>${device.model}</h3>
          <p>${device.path} · SN ${device.serial} · FW ${device.firmware}</p>
        </div>
        <div class="device-info">
          <div><span>容量</span>${device.capacity}</div>
          <div><span>接口</span>${device.pcie}</div>
          <div><span>写缓存</span>${device.cache}</div>
          <div><span>健康</span><b style="color:#61e1ad">${device.health}</b></div>
        </div>
        <span class="device-toggle">展开详情 ↓</span>
        <div class="device-detail">
          <div><b>Namespace</b>${device.namespace}</div>
          <div><b>数据来源</b>${device.source || "安全演示"}</div>
          <div><b>安全状态</b>未执行任何写入操作</div>
        </div>
      </article>
    `,
      )
      .join("");
    const featured = state.devices[0];
    if (featured) {
      $(".hero h2").innerHTML = `${state.devices.length} <span>NVMe SSD</span>`;
      $(".hero-device").innerHTML = `
        <b>${featured.model}</b>
        <span>${featured.path} · ${featured.pcie} · ${featured.cache}</span>
      `;
    }
    const deviceSelect = $("#task-form [name=device]");
    if (deviceSelect) {
      deviceSelect.innerHTML = state.devices
        .map(
          (device) =>
            `<option value="${device.path}">${device.path} · ${device.model}</option>`,
        )
        .join("");
    }
  } catch (error) {
    list.innerHTML = `<div class="panel empty-state">${error.message}</div>`;
    notify(error.message);
  }
}

function toggleDevice(card) {
  const expanded = !card.classList.contains("expanded");
  card.classList.toggle("expanded", expanded);
  card.setAttribute("aria-expanded", String(expanded));
  $(".device-toggle", card).textContent = expanded
    ? "收起详情 ↑"
    : "展开详情 ↓";
}

async function runCacheSimulation() {
  const workload = $("#simulation-workload").value;
  const count = Number($("#simulation-count").value);
  const capacity = Number($("#simulation-capacity").value);
  const seed = Number($("#simulation-seed").value);
  const button = $("#run-cache-simulation");
  button.disabled = true;
  button.textContent = "仿真中…";
  try {
    state.cacheResult = await api(
      `/api/simulations/cache?workload=${workload}&count=${count}&capacity=${capacity}&seed=${seed}`,
    );
    renderCacheSimulation();
    notify("缓存算法仿真完成");
  } catch (error) {
    notify(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "运行仿真";
  }
}

function renderCacheSimulation() {
  const result = state.cacheResult;
  if (!result) {
    return;
  }
  const comparison = result.cache_metrics;
  const algorithms = comparison.algorithms;
  $("#cache-summary").innerHTML = Object.entries(algorithms)
    .map(
      ([name, metrics]) => `
      <article class="algorithm-card ${name === comparison.best_algorithm ? "best" : ""}">
        <h3>${name}${name === comparison.best_algorithm ? " · BEST" : ""}</h3>
        <div class="score">${(metrics.hit_ratio * 100).toFixed(2)}%</div>
        <dl>
          <dt>热命中</dt><dd>${metrics.hot_hits}</dd>
          <dt>冷命中</dt><dd>${metrics.cold_hits}</dd>
          <dt>脏页驱逐</dt><dd>${metrics.dirty_evictions}</dd>
          <dt>干净页驱逐</dt><dd>${metrics.clean_evictions}</dd>
        </dl>
      </article>
    `,
    )
    .join("");

  const heat = result.page_heat;
  $("#heat-content").className = "heat-grid";
  $("#heat-content").innerHTML = [
    ["页面总数", heat.page_count],
    ["热页", heat.hot_pages],
    ["冷页", heat.cold_pages],
    ["晋升次数", heat.promotions],
  ]
    .map(
      ([label, value]) => `
    <div class="heat-cell"><span>${label}</span><b>${value}</b></div>
  `,
    )
    .join("");

  const element = $("#cache-chart");
  disposeChart("cache-chart");
  const chart = echarts.init(element);
  state.charts.set("cache-chart", chart);
  const names = Object.keys(algorithms);
  chart.setOption({
    grid: { left: 50, right: 20, top: 30, bottom: 30 },
    tooltip: { trigger: "axis" },
    legend: {
      data: ["命中率", "脏页驱逐率"],
      textStyle: { color: "#aebdb6" },
    },
    xAxis: {
      type: "category",
      data: names.map((name) => name.toUpperCase()),
      axisLabel: { color: "#87958f" },
    },
    yAxis: {
      type: "value",
      max: 100,
      axisLabel: { color: "#87958f", formatter: "{value}%" },
      splitLine: { lineStyle: { color: "#1c2c26" } },
    },
    series: [
      {
        name: "命中率",
        type: "bar",
        data: names.map((name) => algorithms[name].hit_ratio * 100),
        itemStyle: { color: "#61e1ad" },
      },
      {
        name: "脏页驱逐率",
        type: "bar",
        data: names.map((name) => algorithms[name].dirty_eviction_ratio * 100),
        itemStyle: { color: "#f6b75a" },
      },
    ],
  });
}

async function loadAlerts() {
  const severity = $("#alert-severity").value;
  try {
    const query = severity
      ? `?severity=${encodeURIComponent(severity)}&limit=200`
      : "?limit=200";
    const alerts = await api(`/api/alerts${query}`);
    const critical = alerts.filter(
      (event) => event.severity === "critical",
    ).length;
    const warning = alerts.filter(
      (event) => event.severity === "warning",
    ).length;
    const open = alerts.filter((event) => !event.acknowledged).length;
    $("#alert-summary").innerHTML = [
      metricCard("告警总数", alerts.length, "ALL"),
      metricCard("严重", critical, "CRITICAL"),
      metricCard("警告", warning, "WARNING"),
      metricCard("待确认", open, "OPEN"),
    ].join("");
    $("#alert-list").innerHTML = alerts.length
      ? alerts
          .map(
            (event) => `
          <tr class="${event.acknowledged ? "acknowledged" : ""}">
            <td>${event.created_at}</td>
            <td><span class="alert-${event.severity}">${event.severity}</span></td>
            <td>${event.message}</td>
            <td>${event.source}</td>
            <td>${event.value} / ${event.threshold}</td>
            <td>
              ${
                event.acknowledged
                  ? "已确认"
                  : `<button class="link-button acknowledge-alert" data-id="${event.id}">确认</button>`
              }
            </td>
          </tr>
        `,
          )
          .join("")
      : `<tr><td colspan="6" class="empty-state">暂无持久化告警。运行 YAML 场景后会在此展示。</td></tr>`;
  } catch (error) {
    notify(error.message);
  }
}

async function acknowledgeAlert(alertId) {
  try {
    await api(`/api/alerts/${alertId}/acknowledge`, { method: "POST" });
    notify("告警已确认");
    await loadAlerts();
  } catch (error) {
    notify(error.message);
  }
}

async function loadReports() {
  try {
    const runs = await api("/api/scenarios/runs?limit=100");
    const taskRows = state.tasks
      .filter((task) => task.result)
      .map(
        (task) => `
        <tr>
          <td>#${task.id} · ${task.created_at}</td>
          <td>${task.device}</td>
          <td>${task.test_type}</td>
          <td>${task.result.points?.length || 0}</td>
          <td><span class="status">${task.status}</span></td>
          <td><div class="download-group">
            <a href="/api/tasks/${task.id}/report">TXT</a>
            <a href="/api/tasks/${task.id}/export/csv">CSV</a>
            <a href="/api/tasks/${task.id}/export/json">JSON</a>
          </div></td>
        </tr>
      `,
      );
    const runRows = runs.map(
      (run) => `
      <tr>
        <td>#S${run.id} · ${run.created_at}</td>
        <td>${run.scenario_name}</td>
        <td>${run.workload_kind} / ${run.cache_algorithm}</td>
        <td>${run.sample_count}</td>
        <td><span class="status">${run.status}</span></td>
        <td><div class="download-group">
          <a href="/api/scenarios/runs/${run.id}/export/json">JSON</a>
          <a href="/api/scenarios/runs/${run.id}/export/summary">汇总</a>
          <a href="/api/scenarios/runs/${run.id}/export/samples">IO</a>
          <a href="/api/scenarios/runs/${run.id}/export/cache">缓存</a>
        </div></td>
      </tr>
    `,
    );
    $("#report-list").innerHTML =
      [...taskRows, ...runRows].join("") ||
      `<tr><td colspan="6" class="empty-state">暂无报告</td></tr>`;
  } catch (error) {
    notify(error.message);
  }
}

async function viewScenario(runId) {
  try {
    const data = await api(`/api/scenarios/runs/${runId}`);
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `nvme-scenario-${runId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    notify(error.message);
  }
}

async function stopTask(taskId) {
  try {
    await api(`/api/tasks/${taskId}/stop`, { method: "POST" });
    notify("任务已停止");
    await loadTasks();
  } catch (error) {
    notify(error.message);
  }
}

function openTask(taskId) {
  state.selectedTask = state.tasks.find((task) => task.id === taskId);
  renderAnalysis();
  showView("analysis", { remember: true, fallback: "tasks" });
}

function bindEvents() {
  $("nav").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-view]");
    if (!button) {
      return;
    }
    state.history = [];
    showView(button.dataset.view);
  });

  $(".hero").addEventListener("click", () => {
    showView("devices", { remember: true });
  });

  $("#device-list").addEventListener("click", (event) => {
    const card = event.target.closest(".device");
    if (card) {
      toggleDevice(card);
    }
  });

  $("#device-list").addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) {
      return;
    }
    const card = event.target.closest(".device");
    if (card) {
      event.preventDefault();
      toggleDevice(card);
    }
  });

  $("#rescan").addEventListener("click", loadDevices);
  $("#task-filter").addEventListener("change", (event) => {
    state.taskFilter = event.target.value;
    renderTasks();
  });
  $("#analysis-select").addEventListener("change", (event) => {
    state.selectedTask = state.tasks.find(
      (task) => task.id === Number(event.target.value),
    );
    renderAnalysis();
  });

  document.body.addEventListener("click", (event) => {
    const resultButton = event.target.closest(".task-result");
    const stopButton = event.target.closest(".stop-task");
    const acknowledgeButton = event.target.closest(".acknowledge-alert");
    const scenarioButton = event.target.closest(".view-scenario");
    if (resultButton) {
      openTask(Number(resultButton.dataset.id));
    } else if (stopButton) {
      stopTask(Number(stopButton.dataset.id));
    } else if (acknowledgeButton) {
      acknowledgeAlert(Number(acknowledgeButton.dataset.id));
    } else if (scenarioButton) {
      viewScenario(Number(scenarioButton.dataset.id));
    }
  });

  $("#run-cache-simulation").addEventListener("click", runCacheSimulation);
  $("#refresh-alerts").addEventListener("click", loadAlerts);
  $("#alert-severity").addEventListener("change", loadAlerts);
  $("#refresh-reports").addEventListener("click", loadReports);

  const modal = $("#task-modal");
  ["#new-task", "#new-task-2"].forEach((selector) => {
    $(selector).addEventListener("click", () => modal.showModal());
  });
  $$(".close").forEach((button) => {
    button.addEventListener("click", () => modal.close());
  });
  $("#task-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.target));
    ["runtime", "io_depth", "jobs"].forEach((name) => {
      payload[name] = Number(payload[name]);
    });
    try {
      await api("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      modal.close();
      notify("测试任务已启动，正在生成安全模拟数据");
      state.history = [];
      showView("tasks");
      await loadTasks();
    } catch (error) {
      notify(error.message);
    }
  });

  window.addEventListener("resize", () => {
    state.charts.forEach((chart) => chart.resize());
  });
}

async function bootstrap() {
  installExtendedStyles();
  ensureToast();
  installFeaturePages();
  ensureBackButton();
  bindEvents();
  try {
    await Promise.all([loadTasks(), loadDevices()]);
    showView("overview");
  } catch (error) {
    notify(error.message, 5000);
  }
  window.setInterval(() => {
    if (state.tasks.some((task) => task.status === "运行中")) {
      loadTasks();
    }
  }, 1200);
}

bootstrap();
