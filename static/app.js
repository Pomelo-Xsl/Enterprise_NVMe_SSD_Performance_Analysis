const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  devices: [],
  runs: [],
  selectedRun: null,
  cacheResult: null,
  view: "overview",
  history: [],
  charts: new Map(),
};

const TITLES = {
  overview: "分析概览",
  devices: "设备信息",
  analysis: "结果分析",
  "cache-lab": "缓存算法实验室",
  alerts: "告警中心",
  reports: "报告中心",
};

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

function notify(message, duration = 2800) {
  const toast = ensureToast();
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(notify.timer);
  notify.timer = window.setTimeout(
    () => toast.classList.remove("visible"),
    duration,
  );
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch {
      // A non-JSON response keeps the generic message.
    }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function createSection(id, content) {
  const section = document.createElement("section");
  section.id = id;
  section.className = "view";
  section.innerHTML = content;
  $("main").append(section);
}

function installFeaturePages() {
  createSection(
    "cache-lab",
    `
      <div class="section-head">
        <div>
          <h2>缓存算法实验室</h2>
          <p>使用内存访问流对比 LRU-2、ARC 和 LIRS，不访问真实磁盘</p>
        </div>
        <button class="primary" id="run-cache-simulation">运行算法仿真</button>
      </div>
      <div class="panel">
        <div class="lab-form">
          <label>访问模式
            <select id="simulation-workload">
              <option value="mixed">混合访问</option>
              <option value="random">随机访问</option>
              <option value="sequential">顺序访问</option>
              <option value="hot-cold">冷热交替</option>
            </select>
          </label>
          <label>访问样本数
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
          <div class="panel-head"><h3>命中率与脏页驱逐</h3><span class="tag teal">CACHE</span></div>
          <div id="cache-chart" class="chart-small"></div>
        </div>
        <div class="panel">
          <div class="panel-head"><h3>冷热页统计</h3><span class="tag">HEAT</span></div>
          <div id="heat-content" class="empty-state">运行仿真后显示结果</div>
        </div>
      </div>
    `,
  );

  createSection(
    "alerts",
    `
      <div class="section-head">
        <div><h2>告警中心</h2><p>查看导入结果和分析场景产生的风险事件</p></div>
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
          <thead><tr><th>时间</th><th>等级</th><th>事件</th><th>来源</th><th>数值 / 阈值</th><th>状态</th></tr></thead>
          <tbody id="alert-list"></tbody>
        </table>
      </div>
    `,
  );

  createSection(
    "reports",
    `
      <div class="section-head">
        <div><h2>报告中心</h2><p>导出分析记录、IO 样本和缓存算法对比</p></div>
        <button class="secondary" id="refresh-reports">刷新</button>
      </div>
      <div class="panel table-panel">
        <table>
          <thead><tr><th>记录</th><th>来源</th><th>类型</th><th>样本数</th><th>状态</th><th>导出</th></tr></thead>
          <tbody id="report-list"></tbody>
        </table>
      </div>
    `,
  );
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
  const { remember = false } = options;
  if (remember && state.view !== view) {
    state.history.push(state.view);
  }
  state.view = view;

  $$(".view").forEach((section) => {
    section.classList.toggle("active", section.id === view);
  });
  $$("nav button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  $("#page-title").textContent = TITLES[view] || "企业级 NVMe SSD 分析系统";

  const back = ensureBackButton();
  back.classList.toggle("hidden", view === "overview");
  back.textContent = state.history.length
    ? `← 返回${TITLES[state.history[state.history.length - 1]] || "上一页"}`
    : "← 返回分析概览";

  if (view === "devices") loadDevices();
  if (view === "analysis") loadRuns();
  if (view === "alerts") loadAlerts();
  if (view === "reports") loadReports();
}

function goBack() {
  const previous = state.history.pop() || "overview";
  showView(previous);
}

function metricCard(label, value, hint, modifier = "") {
  return `
    <div class="metric ${modifier}">
      <p>${label}</p>
      <b>${value}</b>
      <small>${hint}</small>
    </div>
  `;
}

function firstNumber(...values) {
  return values.find((value) => Number.isFinite(Number(value)) && Number(value) > 0);
}

function formatLatency(value) {
  return value ? `${Number(value).toFixed(2)} <em>μs</em>` : "—";
}

function formatBandwidth(report) {
  const windows = report.io_statistics?.time_windows || [];
  if (windows.length) {
    const average =
      windows.reduce(
        (total, window) => total + Number(window.bandwidth_bytes_per_second || 0),
        0,
      ) / windows.length;
    return average ? `${(average / 1_000_000).toFixed(2)} <em>MB/s</em>` : "—";
  }

  const fio = report.fio?.aggregate || {};
  const fioBandwidth =
    Number(fio.read_bandwidth_kib_s || 0) +
    Number(fio.write_bandwidth_kib_s || 0);
  if (fioBandwidth) return `${(fioBandwidth / 1024).toFixed(2)} <em>MB/s</em>`;

  const performanceBandwidth = report.performance?.bandwidth?.average;
  return performanceBandwidth
    ? `${Number(performanceBandwidth).toFixed(2)} <em>MB/s</em>`
    : "—";
}

function readWriteRatio(report) {
  const directions = report.io_statistics?.directions;
  const fio = report.fio?.aggregate;
  const readRatio = directions?.read?.ratio ?? fio?.read_ratio;
  const writeRatio = directions?.write?.ratio ?? fio?.write_ratio;
  if (!Number.isFinite(Number(readRatio)) || !Number.isFinite(Number(writeRatio))) {
    return "—";
  }
  return `${Math.round(Number(readRatio) * 100)}<em>%</em> / ${Math.round(Number(writeRatio) * 100)}<em>%</em>`;
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(0)} MiB`;
  if (value >= 1024) return `${(value / 1024).toFixed(0)} KiB`;
  return value ? `${value} B` : "—";
}

function dominantEntry(source, valueKey = "operations") {
  const [entry] = Object.entries(source || {}).sort(
    ([, left], [, right]) =>
      Number(right[valueKey] || 0) - Number(left[valueKey] || 0),
  );
  return entry ? { key: entry[0], value: entry[1] } : null;
}

function disposeChart(id) {
  const chart = state.charts.get(id);
  if (chart) {
    chart.dispose();
    state.charts.delete(id);
  }
}

async function loadOverview() {
  try {
    const [summary, runs] = await Promise.all([
      api("/api/summary"),
      api("/api/scenarios/runs?limit=5"),
    ]);
    $("#overview-metrics").innerHTML = [
      metricCard("只读设备", summary.devices, "DEVICES"),
      metricCard("分析记录", summary.analysis_runs, "IMPORTED + LAB"),
      metricCard("待确认告警", summary.open_alerts, "OPEN ALERTS"),
      metricCard("缓存算法", summary.cache_algorithms, "LRU-2 · ARC · LIRS"),
    ].join("");

    $("#recent-runs").innerHTML = runs.length
      ? runs
          .map(
            (run) => `
              <button class="recent-run" data-run-id="${run.id}">
                <span><b>${run.scenario_name}</b><small>${run.created_at}</small></span>
                <span>${run.workload_kind} · ${run.sample_count} samples</span>
                <i>查看分析 →</i>
              </button>
            `,
          )
          .join("")
      : `<div class="empty-state">尚未导入结果。可以加载演示案例，或导入 Benchmark、PressureTest、FIO JSON。</div>`;
  } catch (error) {
    notify(error.message);
  }
}

async function loadDevices() {
  const list = $("#device-list");
  list.innerHTML = `<div class="panel skeleton"></div>`;
  try {
    state.devices = await api("/api/devices");
    list.innerHTML = state.devices
      .map(
        (device) => `
          <article class="panel device" tabindex="0" role="button" aria-expanded="false">
            <div><h3>${device.model}</h3><p>${device.path} · SN ${device.serial} · FW ${device.firmware}</p></div>
            <div class="device-info">
              <div><span>容量</span>${device.capacity}</div>
              <div><span>接口</span>${device.pcie}</div>
              <div><span>写缓存</span>${device.cache}</div>
              <div><span>健康</span><b style="color:#61e1ad">${device.health}</b></div>
            </div>
            <span class="device-toggle">展开详情 ↓</span>
            <div class="device-detail">
              <div><b>Namespace</b>${device.namespace}</div>
              <div><b>数据来源</b>${device.source}</div>
              <div><b>系统定位</b>只读分析，不执行 Benchmark 或 PressureTest</div>
            </div>
          </article>
        `,
      )
      .join("");

    $("#device-count").innerHTML =
      `${state.devices.length} <span>NVMe SSD</span>`;
    const featured = state.devices[0];
    if (featured) {
      $("#featured-device").innerHTML =
        `<b>${featured.model}</b><span>${featured.path} · ${featured.pcie}</span>`;
    }
  } catch (error) {
    list.innerHTML = `<div class="panel empty-state">${error.message}</div>`;
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

async function loadRuns(preferredId = null) {
  try {
    state.runs = await api("/api/scenarios/runs?limit=100");
    $("#analysis-select").innerHTML = state.runs.length
      ? state.runs
          .map(
            (run) =>
              `<option value="${run.id}">#${run.id} · ${run.scenario_name}</option>`,
          )
          .join("")
      : `<option value="">暂无分析记录</option>`;

    const selectedId =
      preferredId || state.selectedRun?.run_id || state.runs[0]?.id;
    if (!selectedId) {
      state.selectedRun = null;
      renderAnalysis();
      return;
    }
    $("#analysis-select").value = String(selectedId);
    state.selectedRun = await api(`/api/scenarios/runs/${selectedId}`);
    state.selectedRun.run_id = Number(selectedId);
    renderAnalysis();
  } catch (error) {
    notify(error.message);
  }
}

function analysisMetrics(report) {
  const latency = report.io_statistics?.latency || {};
  const performanceLatency = report.performance?.latency || {};
  const p50 = firstNumber(latency.p50_us, performanceLatency.p50);
  const p99 = firstNumber(latency.p99_us, performanceLatency.p99);
  return [
    metricCard(
      "P50 延迟",
      formatLatency(p50),
      "典型请求延迟",
      "analysis-kpi latency-typical",
    ),
    metricCard(
      "P99 延迟",
      formatLatency(p99),
      "尾部请求延迟",
      "analysis-kpi latency-tail",
    ),
    metricCard(
      "平均带宽",
      formatBandwidth(report),
      "分析时间窗口均值",
      "analysis-kpi bandwidth",
    ),
    metricCard(
      "读写比例",
      readWriteRatio(report),
      "READ / WRITE",
      "analysis-kpi ratio",
    ),
  ];
}

function analysisProfile(report) {
  const io = report.io_statistics || {};
  const dominantBlock = dominantEntry(io.block_sizes);
  const dominantQueue = dominantEntry(io.queue_depths);
  const comparison = report.cache_comparison || {};
  const bestName = comparison.best_algorithm;
  const best = comparison.algorithms?.[bestName] || {};
  const alerts = report.alerts?.summary || {};
  const stability = report.performance?.stability || "等待完整时序";

  return `
    <div class="analysis-insight-grid">
      <article class="panel analysis-insight-card">
        <div class="insight-card-head"><span>WORKLOAD</span><i></i></div>
        <h3>负载画像</h3>
        <dl class="analysis-facts">
          <div><dt>样本数量</dt><dd>${Number(report.sample_count || 0).toLocaleString()}</dd></div>
          <div><dt>主要块大小</dt><dd>${formatBytes(dominantBlock?.value?.block_size_bytes)}</dd></div>
          <div><dt>主要队列深度</dt><dd>${dominantQueue ? `QD ${dominantQueue.key}` : "—"}</dd></div>
          <div><dt>唯一 LBA</dt><dd>${io.unique_lbas ?? "—"}</dd></div>
        </dl>
      </article>
      <article class="panel analysis-insight-card">
        <div class="insight-card-head"><span>CACHE</span><i></i></div>
        <h3>缓存建议</h3>
        <div class="recommendation-value">${bestName ? bestName.toUpperCase() : "暂无访问流"}</div>
        <p>${bestName ? `命中率 ${(Number(best.hit_ratio || 0) * 100).toFixed(2)}%，脏页驱逐 ${best.dirty_evictions || 0} 次。` : "导入含逐 IO LBA 的结果后生成算法建议。"}</p>
      </article>
      <article class="panel analysis-insight-card">
        <div class="insight-card-head"><span>HEALTH</span><i></i></div>
        <h3>分析状态</h3>
        <div class="recommendation-value ${alerts.critical ? "risk" : ""}">${alerts.critical ? `${alerts.critical} 严重事件` : stability}</div>
        <p>待处理告警 ${Number(alerts.critical || 0) + Number(alerts.warning || 0)} 项，分析结果仅用于只读评估。</p>
      </article>
    </div>
  `;
}

function renderAnalysisChart(report) {
  const samples = report.samples || [];
  const windows = report.io_statistics?.time_windows || [];
  const element = $("#analysis-chart");
  if (!element || (!samples.length && !windows.length) || typeof echarts === "undefined") return;

  const timeline = windows.length
    ? windows.map((window) => ({
        label: `${(Number(window.start_ms || 0) / 1000).toFixed(1)}s`,
        bandwidth: Number(window.bandwidth_bytes_per_second || 0) / 1_000_000,
        latency: Number(window.p99_latency_us || 0),
      }))
    : samples.map((sample) => ({
        label: `${Number(sample.timestamp_ms || 0)}ms`,
        bandwidth:
          (Number(sample.size_bytes || 0) / Math.max(Number(sample.latency_us || 0), 1)),
        latency: Number(sample.latency_us || 0),
      }));

  disposeChart("analysis-chart");
  const chart = echarts.init(element);
  state.charts.set("analysis-chart", chart);
  chart.setOption({
    backgroundColor: "transparent",
    grid: { left: 58, right: 60, top: 58, bottom: 42 },
    tooltip: { trigger: "axis" },
    legend: {
      data: ["估算带宽 MB/s", "延迟 μs"],
      textStyle: { color: "#aebdb6" },
    },
    xAxis: {
      type: "category",
      data: timeline.map((point) => point.label),
      axisLabel: { color: "#87958f" },
      axisLine: { lineStyle: { color: "#294039" } },
      axisTick: { show: false },
    },
    yAxis: [
      {
        name: "MB/s",
        nameTextStyle: { color: "#66766f" },
        axisLabel: { color: "#87958f" },
        splitLine: { lineStyle: { color: "#1c2c26" } },
      },
      {
        name: "μs",
        nameTextStyle: { color: "#66766f" },
        axisLabel: { color: "#87958f" },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "估算带宽 MB/s",
        type: "line",
        smooth: true,
        symbol: "none",
        data: timeline.map((point) => point.bandwidth),
        lineStyle: { color: "#61e1ad", width: 2.5 },
        areaStyle: { color: "rgba(97, 225, 173, 0.08)" },
      },
      {
        name: "延迟 μs",
        type: "line",
        yAxisIndex: 1,
        smooth: true,
        symbol: "none",
        data: timeline.map((point) => point.latency),
        lineStyle: { color: "#f6b75a", width: 2 },
      },
    ],
  });
}

function renderAnalysis() {
  const report = state.selectedRun;
  if (!report) {
    $("#analysis-content").innerHTML = `
      <div class="panel empty-state">
        <h3>导入已有测试结果</h3>
        <p>支持 FIO JSON、规范化 IO samples，以及 Benchmark/PressureTest points。</p>
        <button class="primary import-trigger">选择 JSON 文件</button>
      </div>`;
    return;
  }

  const id = report.run_id;
  const caseMetadata = report.metadata || {};
  const casePanel = caseMetadata.title
    ? `
      <div class="panel demo-case-panel">
        <div>
          <p class="eyebrow">DEMO CASE · ${caseMetadata.industry || "NVME"}</p>
          <h3>${caseMetadata.title}</h3>
          <p>${caseMetadata.description || ""}</p>
        </div>
        <div class="case-observations">
          ${(caseMetadata.expected_observations || [])
            .map((item) => `<span>✓ ${item}</span>`)
            .join("")}
        </div>
      </div>`
    : "";
  $("#analysis-subtitle").textContent =
    `${report.configuration?.scenario?.name || "分析记录"} · ${report.source_format || report.mode}`;
  $("#analysis-content").innerHTML = `
    ${casePanel}
    <div class="analysis-record-strip">
      <div><span>ANALYSIS RECORD</span><b>#${id || "LOCAL"}</b></div>
      <div><span>数据来源</span><b>${report.source_format || report.mode || "未知"}</b></div>
      <div><span>生成时间</span><b>${report.generated_at ? new Date(report.generated_at).toLocaleString("zh-CN", { hour12: false }) : "—"}</b></div>
      <div class="analysis-safe"><i></i><b>只读分析</b></div>
    </div>
    <div class="analysis-kpi-grid">${analysisMetrics(report).join("")}</div>
    <div class="panel analysis-chart-panel">
      <div class="panel-head">
        <div><p class="eyebrow">PERFORMANCE TIMELINE</p><h3>IO 时序分析</h3><p>带宽与尾延迟的时间窗口关系</p></div>
        <div class="download-group">
          <a href="/api/scenarios/runs/${id}/export/json">JSON</a>
          <a href="/api/scenarios/runs/${id}/export/summary">汇总</a>
          <a href="/api/scenarios/runs/${id}/export/samples">IO</a>
          <a href="/api/scenarios/runs/${id}/export/cache">缓存</a>
        </div>
      </div>
      <div id="analysis-chart" class="chart"></div>
      ${report.samples?.length || report.io_statistics?.time_windows?.length ? "" : '<div class="empty-state">该格式没有逐 IO 时序样本，汇总指标仍可正常导出。</div>'}
    </div>
    ${analysisProfile(report)}
  `;
  requestAnimationFrame(() => renderAnalysisChart(report));
}

async function importResult(file) {
  try {
    const payload = JSON.parse(await file.text());
    const name = file.name.replace(/\.json$/i, "") || "imported-result";
    notify("正在解析并保存结果…", 8000);
    const report = await api("/api/analysis/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, cache_pages: 128, payload }),
    });
    notify("结果导入与分析完成");
    await Promise.all([loadOverview(), loadRuns(report.run_id)]);
    state.history = [];
    showView("analysis");
  } catch (error) {
    notify(`导入失败：${error.message}`, 6000);
  } finally {
    $("#result-file").value = "";
  }
}

async function loadDemoCase() {
  const button = $("#load-demo");
  button.disabled = true;
  button.textContent = "正在生成案例…";
  try {
    const report = await api("/api/demo/load", { method: "POST" });
    notify("演示案例分析完成");
    await Promise.all([loadOverview(), loadRuns(report.run_id)]);
    state.history = [];
    showView("analysis");
  } catch (error) {
    notify(`案例加载失败：${error.message}`, 6000);
  } finally {
    button.disabled = false;
    button.textContent = "▶ 演示案例";
  }
}

async function runCacheSimulation() {
  const button = $("#run-cache-simulation");
  const workload = $("#simulation-workload").value;
  const count = Number($("#simulation-count").value);
  const capacity = Number($("#simulation-capacity").value);
  const seed = Number($("#simulation-seed").value);
  button.disabled = true;
  button.textContent = "分析中…";
  try {
    state.cacheResult = await api(
      `/api/simulations/cache?workload=${workload}&count=${count}&capacity=${capacity}&seed=${seed}`,
    );
    renderCacheSimulation();
    notify("缓存算法对比完成");
  } catch (error) {
    notify(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "运行算法仿真";
  }
}

function renderCacheSimulation() {
  const result = state.cacheResult;
  if (!result) return;
  const comparison = result.cache_metrics;
  const algorithms = comparison.algorithms;
  $("#cache-summary").innerHTML = Object.entries(algorithms)
    .map(
      ([name, metrics]) => `
        <article class="algorithm-card ${name === comparison.best_algorithm ? "best" : ""}">
          <h3>${name.toUpperCase()}${name === comparison.best_algorithm ? " · BEST" : ""}</h3>
          <div class="score">${(metrics.hit_ratio * 100).toFixed(2)}%</div>
          <dl><dt>热命中</dt><dd>${metrics.hot_hits}</dd><dt>冷命中</dt><dd>${metrics.cold_hits}</dd>
          <dt>脏页驱逐</dt><dd>${metrics.dirty_evictions}</dd><dt>干净页驱逐</dt><dd>${metrics.clean_evictions}</dd></dl>
        </article>`,
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
      ([label, value]) =>
        `<div class="heat-cell"><span>${label}</span><b>${value}</b></div>`,
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
    legend: { data: ["命中率", "脏页驱逐率"], textStyle: { color: "#aebdb6" } },
    xAxis: { type: "category", data: names.map((name) => name.toUpperCase()) },
    yAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
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
  const query = severity
    ? `?severity=${encodeURIComponent(severity)}&limit=200`
    : "?limit=200";
  try {
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
                <td>${event.created_at}</td><td><span class="alert-${event.severity}">${event.severity}</span></td>
                <td>${event.message}</td><td>${event.source}</td><td>${event.value} / ${event.threshold}</td>
                <td>${event.acknowledged ? "已确认" : `<button class="link-button acknowledge-alert" data-id="${event.id}">确认</button>`}</td>
              </tr>`,
          )
          .join("")
      : `<tr><td colspan="6" class="empty-state">暂无告警</td></tr>`;
  } catch (error) {
    notify(error.message);
  }
}

async function acknowledgeAlert(alertId) {
  try {
    await api(`/api/alerts/${alertId}/acknowledge`, { method: "POST" });
    await Promise.all([loadAlerts(), loadOverview()]);
    notify("告警已确认");
  } catch (error) {
    notify(error.message);
  }
}

async function loadReports() {
  try {
    const runs = await api("/api/scenarios/runs?limit=100");
    $("#report-list").innerHTML = runs.length
      ? runs
          .map(
            (run) => `
              <tr><td>#${run.id} · ${run.created_at}</td><td>${run.scenario_name}</td>
              <td>${run.workload_kind} / ${run.cache_algorithm}</td><td>${run.sample_count}</td>
              <td><span class="status">${run.status}</span></td>
              <td><div class="download-group">
                <a href="/api/scenarios/runs/${run.id}/export/json">JSON</a>
                <a href="/api/scenarios/runs/${run.id}/export/summary">汇总</a>
                <a href="/api/scenarios/runs/${run.id}/export/samples">IO</a>
                <a href="/api/scenarios/runs/${run.id}/export/cache">缓存</a>
              </div></td></tr>`,
          )
          .join("")
      : `<tr><td colspan="6" class="empty-state">暂无分析报告</td></tr>`;
  } catch (error) {
    notify(error.message);
  }
}

function bindEvents() {
  $("nav").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-view]");
    if (!button) return;
    state.history = [];
    showView(button.dataset.view);
  });

  document.body.addEventListener("click", (event) => {
    const importButton = event.target.closest(".import-trigger");
    const recentRun = event.target.closest(".recent-run");
    const alertButton = event.target.closest(".acknowledge-alert");
    if (importButton) {
      $("#result-file").click();
    } else if (recentRun) {
      loadRuns(Number(recentRun.dataset.runId));
      showView("analysis", { remember: true });
    } else if (alertButton) {
      acknowledgeAlert(Number(alertButton.dataset.id));
    }
  });

  $("#result-file").addEventListener("change", (event) => {
    const [file] = event.target.files;
    if (file) importResult(file);
  });
  $("#load-demo").addEventListener("click", loadDemoCase);
  $("#analysis-select").addEventListener("change", (event) =>
    loadRuns(Number(event.target.value)),
  );
  $("#refresh-overview").addEventListener("click", loadOverview);
  $("#rescan").addEventListener("click", loadDevices);
  $("#run-cache-simulation").addEventListener("click", runCacheSimulation);
  $("#refresh-alerts").addEventListener("click", loadAlerts);
  $("#alert-severity").addEventListener("change", loadAlerts);
  $("#refresh-reports").addEventListener("click", loadReports);

  $("#device-list").addEventListener("click", (event) => {
    const card = event.target.closest(".device");
    if (card) toggleDevice(card);
  });
  $("#device-list").addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) return;
    const card = event.target.closest(".device");
    if (card) {
      event.preventDefault();
      toggleDevice(card);
    }
  });
  $(".hero").addEventListener("click", () =>
    showView("devices", { remember: true }),
  );
  window.addEventListener("resize", () =>
    state.charts.forEach((chart) => chart.resize()),
  );
}

async function bootstrap() {
  ensureToast();
  installFeaturePages();
  ensureBackButton();
  bindEvents();
  await Promise.all([loadDevices(), loadOverview(), loadRuns()]);
  showView("overview");
}

bootstrap().catch((error) => notify(error.message, 6000));
