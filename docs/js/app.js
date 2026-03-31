/**
 * ASTC 期貨篩選器 - 前端邏輯
 * 6 大面板：篩選結果 | 圖表分析 | 換倉日曆 | 風險管理 | COT+季節性 | 交易日誌
 */

// ============================================================
// State
// ============================================================

let DATA = null;
let CALENDAR_DATA = null;
let SEASONALITY_DATA = null;
let OHLCV_DATA = null;
let TRADES = JSON.parse(localStorage.getItem("futures-trades") || "[]");
let POSITIONS = JSON.parse(localStorage.getItem("futures-positions") || "[]");
let currentSort = { key: "long_score", desc: true };
let currentFilter = "all";
let selectedSymbol = null;

// ============================================================
// Init
// ============================================================

document.addEventListener("DOMContentLoaded", async () => {
  await loadData();
  setupTabs();
  setupSort();
  setupCalcSymbolDropdowns();
  setupChartSymbolSelect();
  setupPositionCalc();
  setupTradeForm();
  renderAll();
});

async function loadData() {
  try {
    const res = await fetch("data/results.json");
    DATA = await res.json();
  } catch (e) {
    console.error("Failed to load results.json", e);
    DATA = { results: [], correlation_matrix: {}, categories: [] };
  }

  try {
    const res = await fetch("data/calendar.json");
    CALENDAR_DATA = await res.json();
  } catch (e) {
    CALENDAR_DATA = { events: [] };
  }

  try {
    const res = await fetch("data/seasonality.json");
    SEASONALITY_DATA = await res.json();
  } catch (e) {
    SEASONALITY_DATA = { data: {} };
  }

  try {
    const res = await fetch("data/ohlcv.json");
    OHLCV_DATA = await res.json();
  } catch (e) {
    OHLCV_DATA = {};
  }
}

// ============================================================
// Tabs
// ============================================================

function setupTabs() {
  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`panel-${tab.dataset.panel}`).classList.add("active");

      if (tab.dataset.panel === "chart") {
        const code = selectedSymbol || (DATA?.results?.[0]?.code);
        if (code) {
          selectedSymbol = code;
          loadTradingViewChart(code);
        }
      }
    });
  });
}

// ============================================================
// Render All
// ============================================================

function renderAll() {
  if (!DATA) return;
  renderHeader();
  renderSignalStats();
  renderCategoryFilters();
  renderResultsTable();
  renderRolloverPanel();
  renderRiskPanel();
  renderCalendarPanel();
  renderSeasonalityPanel();
  renderJournalPanel();
}

// ============================================================
// Header
// ============================================================

function renderHeader() {
  document.getElementById("header-date").textContent = DATA.generated_at || "-";
  document.getElementById("header-account").textContent = `帳戶: $${(DATA.account_balance || 7000).toLocaleString()}`;
  document.getElementById("header-count").textContent = `標的: ${DATA.total_contracts || 0}`;
}

// ============================================================
// Signal Stats
// ============================================================

function renderSignalStats() {
  const results = DATA.results || [];
  const counts = {
    "強烈做多": 0, "做多": 0, "中性": 0, "做空": 0, "強烈做空": 0,
  };
  results.forEach(r => { if (counts[r.signal] !== undefined) counts[r.signal]++; });

  const el = document.getElementById("signal-stats");
  el.innerHTML = [
    statCard(counts["強烈做多"], "強烈做多", "positive"),
    statCard(counts["做多"], "做多", "positive"),
    statCard(counts["中性"], "中性", ""),
    statCard(counts["做空"] + counts["強烈做空"], "做空", "negative"),
    statCard(results.filter(r => r.days_to_rollover && r.days_to_rollover <= 14).length, "需換倉", "warning"),
  ].join("");
}

function statCard(value, label, cls) {
  return `<div class="stat-card">
    <div class="stat-value ${cls}">${value}</div>
    <div class="stat-label">${label}</div>
  </div>`;
}

// ============================================================
// Category Filters
// ============================================================

function renderCategoryFilters() {
  const categories = DATA.categories || [];
  const el = document.getElementById("category-filters");
  el.innerHTML = `<button class="filter-btn ${currentFilter === "all" ? "active" : ""}" data-cat="all">全部</button>` +
    categories.map(c =>
      `<button class="filter-btn ${currentFilter === c ? "active" : ""}" data-cat="${c}">${c}</button>`
    ).join("");

  el.querySelectorAll(".filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      currentFilter = btn.dataset.cat;
      renderCategoryFilters();
      renderResultsTable();
    });
  });
}

// ============================================================
// Results Table
// ============================================================

function setupSort() {
  document.querySelectorAll("#results-table th[data-sort]").forEach(th => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (currentSort.key === key) {
        currentSort.desc = !currentSort.desc;
      } else {
        currentSort = { key, desc: true };
      }
      renderResultsTable();
    });
  });
}

function renderResultsTable() {
  let results = DATA.results || [];

  // Filter
  if (currentFilter !== "all") {
    results = results.filter(r => r.category === currentFilter);
  }

  // Sort
  results = [...results].sort((a, b) => {
    let va = a[currentSort.key], vb = b[currentSort.key];
    if (va == null) va = -Infinity;
    if (vb == null) vb = -Infinity;
    if (typeof va === "string") {
      return currentSort.desc ? vb.localeCompare(va) : va.localeCompare(vb);
    }
    return currentSort.desc ? vb - va : va - vb;
  });

  const tbody = document.getElementById("results-body");
  tbody.innerHTML = results.map(r => {
    const signalClass = {
      "強烈做多": "strong-long", "做多": "long", "中性": "neutral",
      "做空": "short", "強烈做空": "strong-short",
    }[r.signal] || "neutral";

    const scorePercent = Math.round((r.long_score / (r.total_conditions || 10)) * 100);
    const scoreFillClass = scorePercent >= 70 ? "high" : scorePercent >= 40 ? "mid" : "low";

    const rolloverHtml = r.days_to_rollover != null
      ? `<span class="days-badge ${r.days_to_rollover <= 3 ? "urgent" : r.days_to_rollover <= 14 ? "warning" : "ok"}">${r.days_to_rollover}天</span>`
      : "-";

    return `<tr data-code="${r.code}" class="${selectedSymbol === r.code ? "selected" : ""}">
      <td><strong>${r.code}</strong></td>
      <td>${r.name}</td>
      <td>${r.category}</td>
      <td><span class="signal ${signalClass}">${r.signal}</span></td>
      <td>
        <div class="score-bar">
          <span>${r.long_score}/${r.total_conditions}</span>
          <div class="score-bar-track"><div class="score-bar-fill ${scoreFillClass}" style="width:${scorePercent}%"></div></div>
        </div>
      </td>
      <td>${formatPrice(r.price)}</td>
      <td class="change ${r.change_1d >= 0 ? "positive" : "negative"}">${formatChange(r.change_1d)}</td>
      <td class="change ${r.change_20d >= 0 ? "positive" : "negative"}">${formatChange(r.change_20d)}</td>
      <td class="change ${r.change_60d >= 0 ? "positive" : "negative"}">${formatChange(r.change_60d)}</td>
      <td>${r.adx != null ? r.adx.toFixed(1) : "-"}</td>
      <td>${r.rsi14 != null ? r.rsi14.toFixed(1) : "-"}</td>
      <td>$${(r.margin || 0).toLocaleString()}</td>
      <td>${rolloverHtml}</td>
      <td><button class="btn" onclick="showDetail('${r.code}')">詳細</button></td>
    </tr>`;
  }).join("");

  // Row click -> select
  tbody.querySelectorAll("tr").forEach(tr => {
    tr.addEventListener("click", (e) => {
      if (e.target.tagName === "BUTTON") return;
      selectSymbol(tr.dataset.code);
    });
  });
}

function selectSymbol(code) {
  selectedSymbol = code;
  renderResultsTable();
  showDetail(code);
}

// ============================================================
// Detail Panel
// ============================================================

function showDetail(code) {
  const r = (DATA.results || []).find(x => x.code === code);
  if (!r) return;
  selectedSymbol = code;

  const panel = document.getElementById("condition-detail");
  panel.style.display = "block";

  document.getElementById("detail-title").textContent =
    `${r.code} ${r.name} (${r.name_en}) — ${r.signal}`;

  // Conditions
  const condLabels = {
    price_above_sma50: "價格 > SMA50",
    sma50_above_sma200: "SMA50 > SMA200",
    sma200_trending_up: "SMA200 向上",
    adx_above_25: "ADX > 25",
    price_above_donchian_mid: "價格 > Donchian中線",
    roc_20_positive: "20日動量 > 0",
    roc_60_positive: "60日動量 > 0",
    breakout_high: "突破20日高",
    weekly_trend_up: "週線趨勢向上",
    mtf_alignment: "多時間框架一致",
  };

  const condEl = document.getElementById("detail-conditions");
  condEl.innerHTML = Object.entries(r.conditions || {}).map(([key, val]) => {
    const label = condLabels[key] || key;
    return `<span class="condition-toggle ${val ? "pass" : "fail"}">${val ? "V" : "X"} ${label}</span>`;
  }).join("");

  // Risk info
  const riskEl = document.getElementById("detail-risk");
  riskEl.innerHTML = `
    <div><div class="stat-label">保證金</div><div class="stat-value">$${(r.margin || 0).toLocaleString()}</div></div>
    <div><div class="stat-label">ATR(14)</div><div class="stat-value">${r.atr14 != null ? r.atr14.toFixed(4) : "-"}</div></div>
    <div><div class="stat-label">止損距離 (2xATR)</div><div class="stat-value">${r.stop_distance != null ? r.stop_distance.toFixed(4) : "-"}</div></div>
    <div><div class="stat-label">每口風險</div><div class="stat-value">$${r.risk_per_contract != null ? r.risk_per_contract.toFixed(2) : "-"}</div></div>
    <div><div class="stat-label">建議口數</div><div class="stat-value">${r.suggested_contracts || 0}</div></div>
    <div><div class="stat-label">所需保證金</div><div class="stat-value ${r.can_afford ? "" : "negative"}">$${(r.margin_needed || 0).toLocaleString()}</div></div>
    <div><div class="stat-label">下次換倉</div><div class="stat-value ${r.days_to_rollover && r.days_to_rollover <= 7 ? "warning" : ""}">${r.next_rollover || "-"}</div></div>
    <div><div class="stat-label">合約月份</div><div class="stat-value">${r.contract_month || "-"}</div></div>
  `;

  // Scroll to detail
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ============================================================
// Chart Symbol Selector
// ============================================================

function setupChartSymbolSelect() {
  const select = document.getElementById("chart-symbol-select");
  if (!select) return;

  const results = DATA?.results || [];
  select.innerHTML = `<option value="">-- 選擇期貨 --</option>` +
    results.map(r => `<option value="${r.code}">${r.code} ${r.name} (${r.signal})</option>`).join("");

  select.addEventListener("change", () => {
    const code = select.value;
    if (code) {
      selectedSymbol = code;
      loadTradingViewChart(code);
    }
  });
}

// ============================================================
// TradingView Chart
// ============================================================

function loadTradingViewChart(code) {
  const r = (DATA.results || []).find(x => x.code === code);
  if (!r) return;

  // 同步下拉選單
  const select = document.getElementById("chart-symbol-select");
  if (select && select.value !== code) select.value = code;

  const symbol = r.tradingview || r.yfinance;
  const timeframe = document.getElementById("chart-timeframe").value;
  document.getElementById("chart-symbol").textContent = `${r.code} ${r.name} (${r.name_en})`;

  const container = document.getElementById("tradingview-chart");
  const intervalMap = { D: "D", W: "W", M: "M" };
  const tvUrl = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(symbol)}&interval=${intervalMap[timeframe] || "D"}`;

  const signalColor = {
    "強烈做多": "#3fb950", "做多": "#3fb950", "中性": "#8b949e",
    "做空": "#f85149", "強烈做空": "#f85149",
  }[r.signal] || "#8b949e";

  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:8px;">
      <div>
        <span style="font-size:28px;font-weight:700;color:var(--text-primary);">${formatPrice(r.price)}</span>
        <span style="font-size:15px;margin-left:10px;" class="${r.change_1d >= 0 ? 'positive' : 'negative'}">
          ${r.change_1d >= 0 ? '+' : ''}${r.change_1d?.toFixed(2) || 0}%
        </span>
        <span style="font-size:20px;font-weight:600;margin-left:12px;color:${signalColor};">${r.signal}</span>
        <span style="font-size:13px;margin-left:12px;color:var(--text-secondary);">
          ${r.long_score}/${r.total_conditions}分 | ADX ${r.adx?.toFixed(1) || '-'} | RSI ${r.rsi14?.toFixed(1) || '-'}
        </span>
      </div>
      <a href="${tvUrl}" target="_blank" rel="noopener"
         style="display:inline-block;padding:8px 20px;background:var(--accent-gold);color:#000;
                font-size:13px;font-weight:700;border-radius:6px;text-decoration:none;cursor:pointer;">
        在 TradingView 開啟完整圖表
      </a>
    </div>
    <div id="kline-chart" style="width:100%;height:420px;"></div>
  `;

  // 使用 Lightweight Charts 畫 K 線圖
  const ohlcv = OHLCV_DATA?.[code];
  if (!ohlcv || !ohlcv.length || typeof LightweightCharts === 'undefined') return;

  const chartEl = document.getElementById("kline-chart");
  const chart = LightweightCharts.createChart(chartEl, {
    width: chartEl.clientWidth,
    height: 420,
    layout: { background: { color: '#0d1117' }, textColor: '#c9d1d9' },
    grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: '#30363d' },
    timeScale: { borderColor: '#30363d', timeVisible: false },
  });

  const candleSeries = chart.addCandlestickSeries({
    upColor: '#3fb950', downColor: '#f85149',
    borderUpColor: '#3fb950', borderDownColor: '#f85149',
    wickUpColor: '#3fb950', wickDownColor: '#f85149',
  });
  candleSeries.setData(ohlcv);

  // 成交量
  const volSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: 'vol',
  });
  chart.priceScale('vol').applyOptions({
    scaleMargins: { top: 0.85, bottom: 0 },
  });
  volSeries.setData(ohlcv.map(d => ({
    time: d.time,
    value: d.volume,
    color: d.close >= d.open ? 'rgba(63,185,80,0.3)' : 'rgba(248,81,73,0.3)',
  })));

  chart.timeScale().fitContent();

  // Responsive
  const resizeObserver = new ResizeObserver(() => {
    chart.applyOptions({ width: chartEl.clientWidth });
  });
  resizeObserver.observe(chartEl);
}

document.getElementById("chart-timeframe")?.addEventListener("change", () => {
  if (selectedSymbol) loadTradingViewChart(selectedSymbol);
});

// ============================================================
// Rollover Panel
// ============================================================

function renderRolloverPanel() {
  const results = (DATA.results || []).filter(r => r.next_rollover);
  results.sort((a, b) => (a.days_to_rollover || 999) - (b.days_to_rollover || 999));

  // Stats
  const urgent = results.filter(r => r.days_to_rollover <= 3).length;
  const warning = results.filter(r => r.days_to_rollover > 3 && r.days_to_rollover <= 14).length;
  const ok = results.filter(r => r.days_to_rollover > 14).length;

  document.getElementById("rollover-stats").innerHTML = [
    statCard(urgent, "緊急 (3天內)", "negative"),
    statCard(warning, "注意 (14天內)", "warning"),
    statCard(ok, "安全", "positive"),
  ].join("");

  // List
  const listEl = document.getElementById("rollover-list");
  if (results.length === 0) {
    listEl.innerHTML = `<p style="padding:20px;text-align:center;color:var(--text-secondary)">目前沒有換倉提醒</p>`;
    return;
  }

  listEl.innerHTML = results.map(r => {
    const urgency = r.days_to_rollover <= 3 ? "urgent" : r.days_to_rollover <= 14 ? "warning" : "ok";
    const urgencyLabel = r.days_to_rollover <= 3 ? "必須立即換倉！" :
      r.days_to_rollover <= 7 ? "建議本週換倉" :
      r.days_to_rollover <= 14 ? "請準備換倉" : "正常";

    return `<div class="rollover-item rollover-${urgency}">
      <div>
        <strong>${r.code}</strong> ${r.name}
        <div style="font-size:12px;color:var(--text-secondary)">${r.contract_month || ""}</div>
      </div>
      <div style="text-align:center">
        <div style="font-size:12px;color:var(--text-secondary)">到期: ${r.next_expiry || "-"}</div>
        <div style="font-size:12px;color:var(--text-secondary)">換倉: ${r.next_rollover || "-"}</div>
      </div>
      <div style="text-align:right">
        <span class="days-badge ${urgency}">${r.days_to_rollover} 天</span>
        <div style="font-size:11px;color:var(--text-secondary);margin-top:4px">${urgencyLabel}</div>
      </div>
    </div>`;
  }).join("");
}

// ============================================================
// Risk Management Panel
// ============================================================

function renderRiskPanel() {
  renderAccountStats();
  renderCorrelationMatrix();
  renderVolatilityTable();
}

function renderAccountStats() {
  const balance = DATA.account_balance || 7000;
  const maxRisk = balance * (DATA.risk_per_trade || 0.02);

  // Calculate used margin from positions
  const usedMargin = POSITIONS.reduce((sum, p) => {
    const r = (DATA.results || []).find(x => x.code === p.symbol);
    return sum + (r ? r.margin * p.contracts : 0);
  }, 0);

  const available = balance - usedMargin;
  const usagePct = Math.round((usedMargin / balance) * 100);

  document.getElementById("account-stats").innerHTML = [
    statCard(`$${balance.toLocaleString()}`, "帳戶淨值", ""),
    statCard(`$${usedMargin.toLocaleString()}`, "已用保證金", usagePct > 70 ? "negative" : usagePct > 50 ? "warning" : ""),
    statCard(`$${available.toLocaleString()}`, "可用資金", available < 1000 ? "negative" : "positive"),
    statCard(`$${maxRisk.toFixed(0)}`, "單筆最大虧損 (2%)", ""),
    statCard(`${usagePct}%`, "保證金使用率", usagePct > 70 ? "negative" : usagePct > 50 ? "warning" : "positive"),
  ].join("");
}

function renderCorrelationMatrix() {
  const corr = DATA.correlation_matrix || {};
  const codes = Object.keys(corr);
  if (codes.length === 0) {
    document.getElementById("correlation-matrix").innerHTML =
      `<p style="padding:20px;text-align:center;color:var(--text-secondary)">需要更多資料才能計算相關性</p>`;
    return;
  }

  let html = `<table class="heatmap-table"><thead><tr><th></th>`;
  codes.forEach(c => { html += `<th>${c}</th>`; });
  html += `</tr></thead><tbody>`;

  codes.forEach(c1 => {
    html += `<tr><td><strong>${c1}</strong></td>`;
    codes.forEach(c2 => {
      const val = corr[c1]?.[c2];
      if (val == null) {
        html += `<td>-</td>`;
      } else {
        const color = corrColor(val);
        html += `<td style="background:${color};color:${Math.abs(val) > 0.5 ? "#fff" : "var(--text-primary)"}">${val.toFixed(2)}</td>`;
      }
    });
    html += `</tr>`;
  });

  html += `</tbody></table>`;
  document.getElementById("correlation-matrix").innerHTML = html;
}

function corrColor(val) {
  if (val >= 0.7) return "rgba(248, 81, 73, 0.6)";
  if (val >= 0.4) return "rgba(248, 81, 73, 0.3)";
  if (val >= 0.1) return "rgba(248, 81, 73, 0.1)";
  if (val >= -0.1) return "transparent";
  if (val >= -0.4) return "rgba(88, 166, 255, 0.1)";
  if (val >= -0.7) return "rgba(88, 166, 255, 0.3)";
  return "rgba(88, 166, 255, 0.6)";
}

function renderVolatilityTable() {
  const results = (DATA.results || []).filter(r => r.volatility_percentile != null);
  results.sort((a, b) => b.volatility_percentile - a.volatility_percentile);

  const tbody = document.getElementById("volatility-body");
  tbody.innerHTML = results.map(r => {
    const level = r.volatility_level || "-";
    const levelClass = level === "高" ? "negative" : level === "低" ? "positive" : "";
    const advice = level === "高" ? "縮小倉位" : level === "低" ? "可放大倉位" : "正常倉位";

    return `<tr>
      <td><strong>${r.code}</strong> ${r.name}</td>
      <td>${r.current_atr != null ? r.current_atr.toFixed(4) : "-"}</td>
      <td>${r.volatility_percentile != null ? r.volatility_percentile.toFixed(1) + "%" : "-"}</td>
      <td class="${levelClass}">${level}</td>
      <td>${advice}</td>
    </tr>`;
  }).join("");
}

// ============================================================
// Position Calculator
// ============================================================

function setupCalcSymbolDropdowns() {
  const results = DATA?.results || [];
  const options = results.map(r => `<option value="${r.code}">${r.code} - ${r.name}</option>`).join("");

  const calcSelect = document.getElementById("calc-symbol");
  if (calcSelect) calcSelect.innerHTML = options;

  const tradeSelect = document.getElementById("trade-symbol");
  if (tradeSelect) tradeSelect.innerHTML = options;
}

function setupPositionCalc() {
  ["calc-symbol", "calc-balance", "calc-risk", "calc-atr-mult"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", calcPosition);
  });
  calcPosition();
}

function calcPosition() {
  const code = document.getElementById("calc-symbol")?.value;
  const balance = parseFloat(document.getElementById("calc-balance")?.value) || 7000;
  const riskPct = (parseFloat(document.getElementById("calc-risk")?.value) || 2) / 100;
  const atrMult = parseFloat(document.getElementById("calc-atr-mult")?.value) || 2;

  const r = (DATA?.results || []).find(x => x.code === code);
  if (!r) return;

  const maxLoss = balance * riskPct;
  const stopDist = (r.atr14 || 0) * atrMult;
  const stopTicks = r.tick_size ? stopDist / r.tick_size : 0;
  const riskPerContract = stopTicks * (r.tick_value || 0);
  const contracts = riskPerContract > 0 ? Math.max(1, Math.floor(maxLoss / riskPerContract)) : 0;
  const marginNeeded = (r.margin || 0) * contracts;
  const canAfford = marginNeeded <= balance * 0.5;

  document.getElementById("calc-output").innerHTML = `
    <div><div class="stat-label">最大虧損金額</div><div class="stat-value">$${maxLoss.toFixed(0)}</div></div>
    <div><div class="stat-label">止損距離</div><div class="stat-value">${stopDist.toFixed(4)}</div></div>
    <div><div class="stat-label">每口風險</div><div class="stat-value">$${riskPerContract.toFixed(2)}</div></div>
    <div><div class="stat-label">建議口數</div><div class="stat-value">${contracts}</div></div>
    <div><div class="stat-label">所需保證金</div><div class="stat-value ${canAfford ? "positive" : "negative"}">$${marginNeeded.toLocaleString()}</div></div>
    <div><div class="stat-label">保證金使用率</div><div class="stat-value ${marginNeeded/balance > 0.5 ? "negative" : "positive"}">${(marginNeeded/balance*100).toFixed(1)}%</div></div>
  `;
}

// ============================================================
// Trade Journal
// ============================================================

function setupTradeForm() {
  const dateInput = document.getElementById("trade-date");
  if (dateInput) dateInput.value = new Date().toISOString().split("T")[0];

  document.getElementById("btn-add-trade")?.addEventListener("click", addTrade);
}

function addTrade() {
  const symbol = document.getElementById("trade-symbol")?.value;
  const direction = document.getElementById("trade-direction")?.value;
  const contracts = parseInt(document.getElementById("trade-contracts")?.value) || 1;
  const entry = parseFloat(document.getElementById("trade-entry")?.value);
  const stop = parseFloat(document.getElementById("trade-stop")?.value);
  const date = document.getElementById("trade-date")?.value;
  const exit = parseFloat(document.getElementById("trade-exit")?.value) || null;
  const exitDate = document.getElementById("trade-exit-date")?.value || null;

  if (!symbol || !entry || !date) {
    alert("請填寫品種、開倉價和日期");
    return;
  }

  const r = (DATA?.results || []).find(x => x.code === symbol);
  const multiplier = r?.multiplier || 1;
  const tickValue = r?.tick_value || 1;
  const tickSize = r?.tick_size || 0.01;

  let pnl = null;
  if (exit) {
    const priceDiff = direction === "long" ? exit - entry : entry - exit;
    const ticks = priceDiff / tickSize;
    pnl = ticks * tickValue * contracts;
  }

  const trade = {
    id: Date.now(),
    symbol,
    name: r?.name || symbol,
    direction,
    contracts,
    entry,
    stop: stop || null,
    exit,
    date,
    exitDate,
    pnl: pnl != null ? Math.round(pnl * 100) / 100 : null,
    status: exit ? "closed" : "open",
  };

  TRADES.push(trade);
  localStorage.setItem("futures-trades", JSON.stringify(TRADES));

  // Clear form
  document.getElementById("trade-entry").value = "";
  document.getElementById("trade-stop").value = "";
  document.getElementById("trade-exit").value = "";
  document.getElementById("trade-exit-date").value = "";

  renderJournalPanel();
}

function deleteTrade(id) {
  TRADES = TRADES.filter(t => t.id !== id);
  localStorage.setItem("futures-trades", JSON.stringify(TRADES));
  renderJournalPanel();
}

function renderJournalPanel() {
  // Stats
  const closedTrades = TRADES.filter(t => t.status === "closed" && t.pnl != null);
  const totalPnl = closedTrades.reduce((s, t) => s + t.pnl, 0);
  const wins = closedTrades.filter(t => t.pnl > 0);
  const winRate = closedTrades.length > 0 ? (wins.length / closedTrades.length * 100) : 0;
  const avgWin = wins.length > 0 ? wins.reduce((s, t) => s + t.pnl, 0) / wins.length : 0;
  const losses = closedTrades.filter(t => t.pnl <= 0);
  const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((s, t) => s + t.pnl, 0) / losses.length) : 0;
  const profitFactor = avgLoss > 0 ? (avgWin / avgLoss) : 0;

  // Max drawdown
  let peak = 0, maxDD = 0, running = 0;
  closedTrades.forEach(t => {
    running += t.pnl;
    if (running > peak) peak = running;
    const dd = peak - running;
    if (dd > maxDD) maxDD = dd;
  });

  document.getElementById("journal-stats").innerHTML = [
    statCard(`$${totalPnl.toFixed(0)}`, "總損益", totalPnl >= 0 ? "positive" : "negative"),
    statCard(closedTrades.length, "已平倉交易", ""),
    statCard(`${winRate.toFixed(1)}%`, "勝率", winRate >= 50 ? "positive" : "negative"),
    statCard(profitFactor.toFixed(2), "盈虧比", profitFactor >= 1.5 ? "positive" : profitFactor >= 1 ? "" : "negative"),
    statCard(`$${maxDD.toFixed(0)}`, "最大回撤", "negative"),
  ].join("");

  // Trade list
  const tbody = document.getElementById("trades-body");
  const sorted = [...TRADES].sort((a, b) => new Date(b.date) - new Date(a.date));
  tbody.innerHTML = sorted.map(t => {
    const dirClass = t.direction === "long" ? "positive" : "negative";
    const dirLabel = t.direction === "long" ? "做多" : "做空";
    const pnlHtml = t.pnl != null
      ? `<span class="${t.pnl >= 0 ? "positive" : "negative"}">$${t.pnl.toFixed(2)}</span>`
      : `<span style="color:var(--text-muted)">持倉中</span>`;

    return `<tr>
      <td>${t.date}</td>
      <td><strong>${t.symbol}</strong> ${t.name || ""}</td>
      <td class="${dirClass}">${dirLabel}</td>
      <td>${t.contracts}</td>
      <td>${formatPrice(t.entry)}</td>
      <td>${t.exit != null ? formatPrice(t.exit) : "-"}</td>
      <td>${pnlHtml}</td>
      <td><button class="btn btn-danger" onclick="deleteTrade(${t.id})" style="padding:2px 8px;font-size:11px">刪除</button></td>
    </tr>`;
  }).join("");
}

// ============================================================
// Economic Calendar Panel
// ============================================================

function renderCalendarPanel() {
  const events = CALENDAR_DATA?.events || [];
  const tbody = document.getElementById("calendar-body");
  if (!tbody) return;

  tbody.innerHTML = events.map(e => {
    const impactClass = e.impact === "high" ? "negative" : e.impact === "medium" ? "warning" : "";
    const impactLabel = e.impact === "high" ? "高" : e.impact === "medium" ? "中" : "低";
    const affected = (e.affected || []).join(", ");
    const daysLabel = e.days_until === 0 ? "今天" : e.days_until === 1 ? "明天" : `${e.days_until}天`;
    const daysClass = e.days_until <= 1 ? "urgent" : e.days_until <= 3 ? "warning" : "ok";

    return `<tr>
      <td>${e.date}</td>
      <td><strong>${e.name}</strong><div style="font-size:11px;color:var(--text-muted)">${e.description || ""}</div></td>
      <td>${e.time || ""}</td>
      <td class="${impactClass}" style="font-weight:600">${impactLabel}</td>
      <td style="font-size:12px">${affected}</td>
      <td><span class="days-badge ${daysClass}">${daysLabel}</span></td>
    </tr>`;
  }).join("");
}

// ============================================================
// Seasonality Panel
// ============================================================

function renderSeasonalityPanel() {
  const data = SEASONALITY_DATA?.data || {};
  const tbody = document.getElementById("seasonality-body");
  if (!tbody) return;

  const currentMonth = String(new Date().getMonth() + 1);
  const rows = [];

  for (const [code, info] of Object.entries(data)) {
    const monthData = info.months?.[currentMonth];
    if (!monthData) continue;
    rows.push({ code, name: info.name, ...monthData });
  }

  rows.sort((a, b) => b.avg_return - a.avg_return);

  tbody.innerHTML = rows.map(r => {
    const bias = r.avg_return > 1 ? "positive" : r.avg_return < -1 ? "negative" : "";
    const direction = r.avg_return > 1 ? "偏多" : r.avg_return < -1 ? "偏空" : "中性";
    const dirClass = r.avg_return > 1 ? "signal long" : r.avg_return < -1 ? "signal short" : "signal neutral";

    return `<tr>
      <td><strong>${r.code}</strong> ${r.name}</td>
      <td class="${bias}">${r.avg_return > 0 ? "+" : ""}${r.avg_return}%</td>
      <td class="${r.win_rate >= 60 ? "positive" : r.win_rate <= 40 ? "negative" : ""}">${r.win_rate}%</td>
      <td class="positive">+${r.best}%</td>
      <td class="negative">${r.worst}%</td>
      <td><span class="${dirClass}">${direction}</span></td>
    </tr>`;
  }).join("");

  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-secondary);padding:20px">
      請先執行 python backend/seasonality.py 產生季節性資料
    </td></tr>`;
  }
}

// ============================================================
// Utilities
// ============================================================

function formatPrice(price) {
  if (price == null) return "-";
  if (price < 1) return price.toFixed(6);
  if (price < 10) return price.toFixed(4);
  return price.toFixed(2);
}

function formatChange(val) {
  if (val == null) return "-";
  const sign = val >= 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}
