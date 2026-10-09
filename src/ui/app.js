// Global State
let rebalancerChartInstance = null;
let rebalancerHistoryChartInstance = null;
let stressClassesChartInstance = null;
let currentSignals = [];

// Initialize on load
document.addEventListener("DOMContentLoaded", () => {
  fetchSignals();
  fetchRebalancerState();
  fetchStressState();
});

// Tab Switcher
function switchTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(content => content.classList.remove("active"));

  const targetBtn = document.getElementById(`tab-btn-${tabId}`);
  const targetContent = document.getElementById(`tab-${tabId}`);

  if (targetBtn) targetBtn.classList.add("active");
  if (targetContent) targetContent.classList.add("active");

  if (tabId === "module-a") {
    setTimeout(fetchRebalancerState, 50);
  } else if (tabId === "module-b") {
    setTimeout(fetchStressState, 50);
  }
}

// ----------------- TAB 1: RISK ENGINE -----------------

async function fetchSignals() {
  try {
    const res = await fetch("/api/risk-engine/signals");
    const signals = await res.json();
    currentSignals = signals;
    renderSignalFeed(signals);
    updateGlobalMetrics();
  } catch (err) {
    console.error("Failed to fetch signals:", err);
  }
}

function renderSignalFeed(signals) {
  const container = document.getElementById("signal-feed-container");
  container.innerHTML = "";

  const reversed = [...signals].reverse();

  reversed.forEach(s => {
    const card = document.createElement("div");
    card.className = `signal-card tier-${s.severity_tier.toLowerCase()}`;

    // Sentiment pill class
    let sentClass = "sent-neutral";
    if (s.sentiment_score >= 0.15) sentClass = "sent-positive";
    else if (s.sentiment_score <= -0.15) sentClass = "sent-negative";

    // Event badge class
    let eventClass = "badge-event";
    if (s.event_classification === "Geopolitical") eventClass = "badge-geopolitical";
    else if (s.event_classification === "Macroeconomic") eventClass = "badge-macro";
    else if (s.event_classification === "Credit Event") eventClass = "badge-credit";
    else if (s.event_classification === "Product Launch") eventClass = "badge-product";

    // Ticker pills
    const tickerHtml = (s.detected_tickers && s.detected_tickers.length > 0)
      ? s.detected_tickers.map(t => `<span style="background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 4px; font-weight:700; color:#38bdf8; font-size: 0.7rem;">$${t}</span>`).join(" ")
      : `<span style="color: var(--text-dim); font-size: 0.7rem;">${s.primary_entity}</span>`;

    card.innerHTML = `
      <div class="signal-top-row">
        <div class="signal-meta">
          <span style="font-weight: 600; color: var(--text-main);">${s.source_name}</span>
          <span>•</span>
          <span>${s.timestamp.substring(11, 19)}</span>
        </div>
        <div style="display: flex; gap: 0.35rem; align-items: center;">
          <span class="badge ${eventClass}">${s.event_classification}</span>
          <span class="sentiment-pill ${sentClass}">${s.sentiment_score > 0 ? '+' : ''}${s.sentiment_score.toFixed(2)}</span>
        </div>
      </div>
      <div class="signal-headline">${s.headline || s.raw_text.substring(0, 90) + '...'}</div>
      <div class="signal-body">${s.raw_text}</div>
      <div class="signal-footer">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
          <span style="color: var(--text-dim);">Entity:</span>
          ${tickerHtml}
        </div>
        <div class="impact-meter">
          <span style="color: var(--text-dim); font-size: 0.7rem;">Impact:</span>
          <span style="color: ${s.impact_score >= 8.0 ? 'var(--accent-red)' : (s.impact_score >= 6.5 ? 'var(--accent-gold)' : 'var(--accent-green)')}; font-size: 0.85rem;">
            ${s.impact_score}/10
          </span>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

async function simulateNextEvent() {
  const btn = document.getElementById("btn-stream-event");
  btn.disabled = true;
  btn.innerHTML = `<span>⏳</span> Ingesting Feed...`;

  try {
    const res = await fetch("/api/risk-engine/simulate-next", { method: "POST" });
    const data = await res.json();
    await fetchSignals();
    await fetchRebalancerState();
    await fetchStressState();
  } catch (err) {
    console.error("Simulation error:", err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>▶</span> Stream Next Live Event`;
  }
}

async function handleAnalyzeSubmit(e) {
  e.preventDefault();
  const source = document.getElementById("input-source").value;
  const headline = document.getElementById("input-headline").value;
  const text = document.getElementById("input-text").value;
  const btn = document.getElementById("btn-analyze-submit");

  btn.disabled = true;
  btn.innerText = "Analyzing...";

  try {
    const res = await fetch("/api/risk-engine/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source, headline, text })
    });
    const signal = await res.json();

    // Show result panel
    const resPanel = document.getElementById("sandbox-result-panel");
    resPanel.style.display = "block";

    document.getElementById("result-sentiment-score").innerText = (signal.sentiment_score > 0 ? "+" : "") + signal.sentiment_score.toFixed(2);
    document.getElementById("result-sentiment-score").style.color = signal.sentiment_score >= 0.15 ? "var(--accent-green)" : (signal.sentiment_score <= -0.15 ? "var(--accent-red)" : "var(--text-muted)");
    document.getElementById("result-sentiment-label").innerText = signal.sentiment_label;

    document.getElementById("result-event-class").innerText = signal.event_classification;
    document.getElementById("result-impact-score").innerText = `${signal.impact_score} / 10`;
    document.getElementById("result-rationale").innerText = signal.rationale;

    const channelsDiv = document.getElementById("result-channels");
    channelsDiv.innerHTML = signal.transmission_channels.map(c => `<span class="badge" style="background: rgba(255,255,255,0.06); color: var(--accent-blue);">${c}</span>`).join(" ");

    // Refresh overall system
    await fetchSignals();
    await fetchRebalancerState();
    await fetchStressState();
  } catch (err) {
    console.error("Analyze error:", err);
  } finally {
    btn.disabled = false;
    btn.innerText = "Analyze Signal";
  }
}

function loadSampleText(sampleId) {
  if (sampleId === 1) {
    document.getElementById("input-source").value = "Financial News (Reuters/Bloomberg)";
    document.getElementById("input-headline").value = "Fed Unveils Emergency +75bps Rate Spike as US Inflation Exceeds 5.1%";
    document.getElementById("input-text").value = "Federal Reserve officials voted unanimously in an emergency session to hike policy rates by 75 basis points. Long-term Treasury bond yields surged while banking and commercial real estate credit spreads widened violently. $JPM $BAC";
  } else {
    document.getElementById("input-source").value = "Social Media (Twitter/X FinTwit)";
    document.getElementById("input-headline").value = "NVIDIA & Hyperscaler AI Deal";
    document.getElementById("input-text").value = "CONFIRMED: $NVDA signs record $22B enterprise sovereign cloud architecture deployment. CEO Jensen Huang cites accelerating gross margin accretion and zero supply bottlenecks. $MSFT $GOOGL #Bullish";
  }
}

function updateGlobalMetrics() {
  document.getElementById("metric-total-signals").innerText = currentSignals.length;
  const criticalCount = currentSignals.filter(s => s.impact_score >= 7.0).length;
  document.getElementById("metric-critical-alerts").innerText = criticalCount;
}

// ----------------- TAB 2: MODULE A REBALANCER -----------------

async function fetchRebalancerState() {
  try {
    const res = await fetch("/api/rebalancer/state");
    const data = await res.json();
    renderRebalancerUI(data);
  } catch (err) {
    console.error("Failed to fetch rebalancer state:", err);
  }
}

function renderRebalancerUI(data) {
  // Update alpha metrics
  const alphaVal = data.active_alpha_pct;
  const alphaElem = document.getElementById("rebal-active-alpha");
  alphaElem.innerText = (alphaVal >= 0 ? "+" : "") + alphaVal.toFixed(2) + "%";
  alphaElem.style.color = alphaVal >= 0 ? "var(--accent-green)" : "var(--accent-red)";
  
  document.getElementById("metric-tactical-alpha").innerText = (alphaVal >= 0 ? "+" : "") + alphaVal.toFixed(2) + "%";
  document.getElementById("metric-tactical-alpha").style.color = alphaVal >= 0 ? "var(--accent-green)" : "var(--accent-red)";

  document.getElementById("rebal-strat-return").innerText = (data.strategy_return_pct >= 0 ? "+" : "") + data.strategy_return_pct.toFixed(2) + "%";
  document.getElementById("rebal-bench-return").innerText = (data.benchmark_return_pct >= 0 ? "+" : "") + data.benchmark_return_pct.toFixed(2) + "%";

  // Table
  const tbody = document.querySelector("#table-rebalancer-constituents tbody");
  tbody.innerHTML = "";

  data.stocks.forEach(s => {
    const tr = document.createElement("tr");
    let actionBadge = `<span class="tag-neut">NEUTRAL</span>`;
    if (s.allocation_action === "OVERWEIGHT") actionBadge = `<span class="tag-over">▲ OVERWEIGHT</span>`;
    else if (s.allocation_action === "UNDERWEIGHT") actionBadge = `<span class="tag-under">▼ UNDERWEIGHT</span>`;

    tr.innerHTML = `
      <td style="font-weight: 700; color: var(--accent-blue);">$${s.ticker}</td>
      <td>${s.name}</td>
      <td style="color: var(--text-muted);">${s.sector}</td>
      <td>${s.benchmark_weight_pct.toFixed(2)}%</td>
      <td style="font-weight: 700;">${s.tactical_weight_pct.toFixed(2)}%</td>
      <td style="font-weight: 700; color: ${s.delta_weight_pct > 0 ? 'var(--accent-green)' : (s.delta_weight_pct < 0 ? 'var(--accent-red)' : 'var(--text-muted)')};">
        ${s.delta_weight_pct > 0 ? '+' : ''}${s.delta_weight_pct.toFixed(2)}%
      </td>
      <td>
        <span class="sentiment-pill ${s.sentiment >= 0.15 ? 'sent-positive' : (s.sentiment <= -0.15 ? 'sent-negative' : 'sent-neutral')}">
          ${s.sentiment > 0 ? '+' : ''}${s.sentiment.toFixed(2)}
        </span>
      </td>
      <td>${actionBadge}</td>
    `;
    tbody.appendChild(tr);
  });

  // Chart
  renderRebalancerChart(data.stocks);
  renderRebalancerHistoryChart(data.history || [], data.stocks);
}

function renderRebalancerHistoryChart(history, stocks) {
  const canvas = document.getElementById("chart-rebalancer-history");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (rebalancerHistoryChartInstance) rebalancerHistoryChartInstance.destroy();

  const trackedTickers = [...stocks]
    .sort((a, b) => Math.abs(b.delta_weight_pct) - Math.abs(a.delta_weight_pct))
    .slice(0, 5)
    .map(s => s.ticker);
  const colors = ["#38bdf8", "#4ade80", "#fbbf24", "#fb7185", "#c084fc"];
  const labels = history.map((h, index) => h.timestamp || `Rebalance ${index + 1}`);

  rebalancerHistoryChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: trackedTickers.map((ticker, index) => ({
        label: `$${ticker}`,
        data: history.map(h => Number(((h.weights || {})[ticker] || 0) * 100).toFixed(2)),
        borderColor: colors[index],
        backgroundColor: colors[index],
        borderWidth: 2,
        pointRadius: 2,
        tension: 0.25,
        fill: false
      }))
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#94a3b8", font: { family: "Inter", size: 11 } } }
      },
      scales: {
        x: { ticks: { color: "#94a3b8", maxRotation: 45 }, grid: { color: "rgba(255,255,255,0.05)" } },
        y: { ticks: { color: "#94a3b8", callback: value => value + "%" }, grid: { color: "rgba(255,255,255,0.05)" } }
      }
    }
  });
}

function renderRebalancerChart(stocks) {
  const ctx = document.getElementById("chart-rebalancer-weights").getContext("2d");
  const labels = stocks.map(s => s.ticker);
  const benchWeights = stocks.map(s => s.benchmark_weight_pct);
  const tacticalWeights = stocks.map(s => s.tactical_weight_pct);

  if (rebalancerChartInstance) {
    rebalancerChartInstance.destroy();
  }

  rebalancerChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Benchmark Weight (%)",
          data: benchWeights,
          backgroundColor: "rgba(148, 163, 184, 0.4)",
          borderColor: "rgba(148, 163, 184, 0.8)",
          borderWidth: 1,
          borderRadius: 4
        },
        {
          label: "Tactical Tilt Weight (%)",
          data: tacticalWeights,
          backgroundColor: "rgba(56, 189, 248, 0.85)",
          borderColor: "#38bdf8",
          borderWidth: 1,
          borderRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: "#94a3b8", font: { family: "Inter", size: 11 } }
        },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.raw.toFixed(2)}%`
          }
        }
      },
      scales: {
        x: {
          ticks: { color: "#94a3b8", font: { family: "Inter", size: 10 } },
          grid: { color: "rgba(255, 255, 255, 0.05)" }
        },
        y: {
          ticks: { color: "#94a3b8", font: { family: "Inter", size: 10 }, callback: v => v + "%" },
          grid: { color: "rgba(255, 255, 255, 0.05)" }
        }
      }
    }
  });
}

// ----------------- TAB 3: MODULE B STRESS TESTING -----------------

async function fetchStressState() {
  try {
    const res = await fetch("/api/stress-test/state");
    const data = await res.json();
    renderStressUI(data);
  } catch (err) {
    console.error("Failed to fetch stress state:", err);
  }
}

function renderStressUI(data) {
  const sim = data.last_simulation;
  if (!sim) return;

  // Header scenario badge
  document.getElementById("stress-scenario-badge").innerText = sim.scenario_name;

  // Metric cards
  const m = sim.metrics;
  document.getElementById("stress-pre-value").innerText = `$${(m.pre_stress_value / 1e6).toFixed(1)}M`;
  document.getElementById("stress-post-value").innerText = `$${(m.post_stress_value / 1e6).toFixed(1)}M`;
  
  const lossText = `-$${(m.total_loss_dollar / 1e6).toFixed(2)}M (-${m.total_loss_pct.toFixed(2)}%)`;
  document.getElementById("stress-total-loss").innerText = lossText;
  document.getElementById("metric-stress-loss").innerText = `-$${(m.total_loss_dollar / 1e6).toFixed(2)}M`;

  document.getElementById("stress-var-99").innerText = `$${(m.var_99_dollar / 1e6).toFixed(1)}M`;
  document.getElementById("stress-cvar-99").innerText = `$${(m.expected_shortfall_cvar_dollar / 1e6).toFixed(1)}M`;

  // Basel III CET1 meter
  const cet1Val = m.post_cet1_ratio_pct;
  const isBreach = m.capital_adequacy_breach;
  const fillElem = document.getElementById("stress-cet1-fill");
  const textElem = document.getElementById("stress-cet1-val");

  textElem.innerText = `${cet1Val.toFixed(2)}% ${isBreach ? '(REGULATORY BREACH ⚠️)' : '(Adequate)'}`;
  textElem.style.color = isBreach ? "var(--accent-red)" : "var(--accent-green)";
  fillElem.style.width = `${Math.min(100, (cet1Val / 15.0) * 100)}%`;
  fillElem.style.background = isBreach ? "var(--accent-red)" : "var(--accent-green)";

  // Top vulnerable assets table
  const tbody = document.querySelector("#table-stress-positions tbody");
  tbody.innerHTML = "";

  sim.top_vulnerable_positions.forEach(p => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="font-weight: 700; color: var(--accent-gold);">${p.asset_id}</td>
      <td>${p.name}</td>
      <td><span class="badge" style="background: rgba(255,255,255,0.06); color: #cbd5e1;">${p.asset_class}</span></td>
      <td style="color: var(--text-muted);">${p.sector}</td>
      <td style="font-weight: 700;">${p.rating}</td>
      <td>$${(p.notional / 1e6).toFixed(1)}M</td>
      <td>$${(p.pre_value / 1e6).toFixed(2)}M</td>
      <td style="font-weight: 700;">$${(p.post_value / 1e6).toFixed(2)}M</td>
      <td style="color: var(--accent-red); font-weight: 700;">-$${(p.loss / 1e6).toFixed(2)}M</td>
      <td style="color: var(--accent-red); font-weight: 700;">-${p.loss_pct.toFixed(2)}%</td>
    `;
    tbody.appendChild(tr);
  });

  // Asset class breakdown chart
  renderStressClassesChart(sim.class_summary);
}

function renderStressClassesChart(classSummary) {
  const ctx = document.getElementById("chart-stress-classes").getContext("2d");
  const labels = Object.keys(classSummary);
  const preVals = labels.map(k => (classSummary[k].pre_value / 1e6));
  const postVals = labels.map(k => (classSummary[k].post_value / 1e6));

  if (stressClassesChartInstance) {
    stressClassesChartInstance.destroy();
  }

  stressClassesChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Baseline Value ($M)",
          data: preVals,
          backgroundColor: "rgba(148, 163, 184, 0.4)",
          borderColor: "rgba(148, 163, 184, 0.8)",
          borderWidth: 1,
          borderRadius: 4
        },
        {
          label: "Post-Stress Value ($M)",
          data: postVals,
          backgroundColor: "rgba(244, 63, 94, 0.8)",
          borderColor: "#f43f5e",
          borderWidth: 1,
          borderRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#94a3b8", font: { family: "Inter", size: 10 } } },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: $${ctx.raw.toFixed(1)}M`
          }
        }
      },
      scales: {
        x: { ticks: { color: "#94a3b8", font: { family: "Inter", size: 10 } }, grid: { color: "rgba(255,255,255,0.05)" } },
        y: { ticks: { color: "#94a3b8", font: { family: "Inter", size: 10 }, callback: v => "$" + v + "M" }, grid: { color: "rgba(255,255,255,0.05)" } }
      }
    }
  });
}

async function runPresetScenario(scenarioId) {
  try {
    const res = await fetch(`/api/stress-test/simulate-preset/${scenarioId}`, { method: "POST" });
    const data = await res.json();
    await fetchStressState();
  } catch (err) {
    console.error("Preset scenario error:", err);
  }
}

async function handleCustomStressSubmit(e) {
  e.preventDefault();
  const scenario_name = document.getElementById("custom-scen-name").value;
  const equity_shock_pct = parseFloat(document.getElementById("custom-equity-shock").value);
  const interest_rate_shock_bps = parseFloat(document.getElementById("custom-ir-shock").value);
  const credit_spread_widening_bps = parseFloat(document.getElementById("custom-spread-shock").value);
  const pd_multiplier = parseFloat(document.getElementById("custom-pd-mult").value);

  try {
    const res = await fetch("/api/stress-test/simulate-custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_name,
        equity_shock_pct,
        interest_rate_shock_bps,
        credit_spread_widening_bps,
        pd_multiplier,
        lgd_multiplier: 1.25,
        energy_boost_pct: 0.0
      })
    });
    const data = await res.json();
    await fetchStressState();
  } catch (err) {
    console.error("Custom stress error:", err);
  }
}
