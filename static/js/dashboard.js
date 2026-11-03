const state = {
  equipment: [],
  sites: [],
  types: [],
  usageChart: null,
  forecastChart: null,
  txLog: [],
};

// ---------------- tab switching ----------------
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`panel-${btn.dataset.tab}`).classList.add("active");
    loadPanel(btn.dataset.tab);
  });
});

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${res.status})`);
  }
  return res.json();
}

// ---------------- summary stats ----------------
async function loadSummary() {
  const s = await api("/api/summary");
  document.getElementById("stat-total").textContent = s.total_equipment;
  document.getElementById("stat-available").textContent = s.available;
  document.getElementById("stat-rented").textContent = s.rented;
  document.getElementById("stat-overdue").textContent = s.overdue;
  document.getElementById("stat-anomalies").textContent = s.anomalies;
}

// ---------------- asset board ----------------
async function loadBoard() {
  const site = document.getElementById("filter-site").value;
  const status = document.getElementById("filter-status").value;
  const params = new URLSearchParams();
  if (site) params.set("site", site);
  if (status) params.set("status", status);

  const data = await api(`/api/equipment?${params.toString()}`);
  state.equipment = data.equipment;
  state.sites = data.sites;
  state.types = data.types;

  populateSiteFilters();

  const grid = document.getElementById("board-grid");
  grid.innerHTML = "";
  if (!data.equipment.length) {
    grid.innerHTML = `<div class="empty-state">No equipment matches this filter.</div>`;
    return;
  }
  for (const eq of data.equipment) {
    const due = eq.due_date ? new Date(eq.due_date).toLocaleDateString() : null;
    grid.insertAdjacentHTML("beforeend", `
      <div class="asset-card status-${eq.status}">
        <div class="asset-card-top">
          <span class="asset-tag">${eq.asset_tag}</span>
          <span class="status-chip status-${eq.status}">${eq.status}</span>
        </div>
        <div class="asset-name">${eq.name}</div>
        <div class="asset-meta">
          ${eq.site}<br>
          Condition: ${eq.condition}
          ${due ? `<br>Due: ${due}` : ""}
          ${eq.last_operator_id ? `<br>Operator: ${eq.last_operator_id}` : ""}
        </div>
      </div>
    `);
  }
}

function populateSiteFilters() {
  const selectors = ["filter-site", "usage-site-filter"];
  for (const id of selectors) {
    const sel = document.getElementById(id);
    if (sel.dataset.populated) continue;
    for (const site of state.sites) {
      const opt = document.createElement("option");
      opt.value = site;
      opt.textContent = site;
      sel.appendChild(opt);
    }
    sel.dataset.populated = "1";
  }
}

document.getElementById("filter-site").addEventListener("change", loadBoard);
document.getElementById("filter-status").addEventListener("change", loadBoard);

// ---------------- check-in / check-out ----------------
function populateScanSelect() {
  const sel = document.getElementById("scan-select");
  sel.innerHTML = "";
  for (const eq of state.equipment) {
    const opt = document.createElement("option");
    opt.value = eq.id;
    opt.textContent = `${eq.asset_tag} — ${eq.name} (${eq.status})`;
    sel.appendChild(opt);
  }
  updateScanUI();
}

function updateScanUI() {
  const sel = document.getElementById("scan-select");
  const eq = state.equipment.find(e => e.id === Number(sel.value));
  const btn = document.getElementById("scan-action-btn");
  const fields = document.getElementById("checkout-fields");
  const current = document.getElementById("scan-current");
  if (!eq) return;

  current.textContent = `Currently: ${eq.status.toUpperCase()} at ${eq.site}`;

  if (eq.status === "available") {
    btn.textContent = "Check out";
    btn.classList.remove("checkin");
    fields.style.display = "block";
  } else {
    btn.textContent = "Check in";
    btn.classList.add("checkin");
    fields.style.display = "none";
  }
}

document.getElementById("scan-select").addEventListener("change", updateScanUI);

document.getElementById("scan-action-btn").addEventListener("click", async () => {
  const sel = document.getElementById("scan-select");
  const eq = state.equipment.find(e => e.id === Number(sel.value));
  const msg = document.getElementById("scan-message");
  if (!eq) return;

  try {
    let result;
    if (eq.status === "available") {
      const operatorId = document.getElementById("operator-id").value || "OP-UNKNOWN";
      const rentalDays = document.getElementById("rental-days").value || 7;
      result = await api(`/api/equipment/${eq.id}/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operator_id: operatorId, rental_days: Number(rentalDays) }),
      });
    } else {
      result = await api(`/api/equipment/${eq.id}/checkin`, { method: "POST" });
    }
    msg.textContent = result.message;
    msg.className = "scan-message ok";
    logTransaction(result.message);
    await loadBoard();
    populateScanSelect();
    await loadSummary();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "scan-message err";
  }
});

function logTransaction(text) {
  state.txLog.unshift({ text, time: new Date().toLocaleTimeString() });
  state.txLog = state.txLog.slice(0, 25);
  const list = document.getElementById("scan-log-list");
  list.innerHTML = state.txLog.map(t => `<li><b>${t.time}</b> — ${t.text}</li>`).join("");
}

// ---------------- usage logs ----------------
async function loadUsage() {
  const site = document.getElementById("usage-site-filter").value;
  const params = new URLSearchParams();
  if (site) params.set("site", site);
  const data = await api(`/api/usage?${params.toString()}`);

  const tbody = document.querySelector("#usage-table tbody");
  tbody.innerHTML = data.logs.map(l => `
    <tr>
      <td>${l.date}</td>
      <td>${l.equipment_name}</td>
      <td>${l.type}</td>
      <td>${l.site}</td>
      <td>${l.engine_hours.toFixed(1)}</td>
      <td>${l.idle_hours.toFixed(1)}</td>
      <td>${l.fuel_used_l.toFixed(1)}</td>
    </tr>
  `).join("");

  const ctx = document.getElementById("usage-chart");
  const labels = data.trend.map(t => t.date.slice(5));
  const engine = data.trend.map(t => Number(t.engine_hours.toFixed(1)));
  const idle = data.trend.map(t => Number(t.idle_hours.toFixed(1)));

  if (state.usageChart) state.usageChart.destroy();
  state.usageChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Engine hrs", data: engine, borderColor: "#f5b700", backgroundColor: "rgba(245,183,0,0.15)", tension: 0.3, fill: true },
        { label: "Idle hrs", data: idle, borderColor: "#4d9eff", backgroundColor: "rgba(77,158,255,0.1)", tension: 0.3, fill: true },
      ],
    },
    options: chartOptions(),
  });
}
document.getElementById("usage-site-filter").addEventListener("change", loadUsage);

// ---------------- overdue alerts ----------------
async function loadAlerts() {
  const alerts = await api("/api/alerts/overdue");
  const container = document.getElementById("alert-list");
  if (!alerts.length) {
    container.innerHTML = `<div class="empty-state">No overdue equipment right now — fleet is on schedule.</div>`;
    return;
  }
  container.innerHTML = alerts.map(a => `
    <div class="alert-item">
      <div>
        <div class="who">${a.equipment_name} <span style="color:var(--text-dim); font-family:var(--font-mono); font-size:12px;">${a.asset_tag}</span></div>
        <div class="meta">${a.site} · Operator ${a.operator_id || "—"} · Due ${new Date(a.due_date).toLocaleDateString()}</div>
      </div>
      <span class="days-badge">${a.days_overdue}d overdue</span>
    </div>
  `).join("");
}

// ---------------- demand forecast ----------------
async function loadForecast() {
  const data = await api("/api/forecast/demand?top_n=8");
  const cards = document.getElementById("forecast-cards");
  cards.innerHTML = data.map(f => `
    <div class="forecast-card">
      <div class="type">${f.type}</div>
      <div class="site">${f.site}</div>
      <div class="hrs">${f.predicted_hours}</div>
      <div class="hrs-label">predicted hrs, next period</div>
    </div>
  `).join("");

  const ctx = document.getElementById("forecast-chart");
  if (state.forecastChart) state.forecastChart.destroy();
  state.forecastChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map(f => `${f.type} · ${f.site.split(" - ")[0]}`),
      datasets: [{ label: "Predicted hrs", data: data.map(f => f.predicted_hours), backgroundColor: "#f5b700" }],
    },
    options: { ...chartOptions(), indexAxis: "y" },
  });
}

// ---------------- anomalies ----------------
async function loadAnomalies() {
  const data = await api("/api/anomalies");
  const container = document.getElementById("anomaly-list");
  if (!data.length) {
    container.innerHTML = `<div class="empty-state">No anomalies detected in the current window.</div>`;
    return;
  }
  container.innerHTML = data.map(a => `
    <div class="anomaly-item">
      <div class="top-row">
        <div>
          <div class="who">${a.name} <span style="color:var(--text-dim); font-family:var(--font-mono); font-size:12px;">${a.asset_tag}</span></div>
          <div class="meta">${a.site} · ${a.date} · Engine ${a.engine_hours}h / Idle ${a.idle_hours}h</div>
        </div>
      </div>
      <div class="reason-tags">${a.reasons.map(r => `<span class="reason-tag">${r}</span>`).join("")}</div>
    </div>
  `).join("");
}

function chartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: "#8a93a3", font: { family: "Inter" } } } },
    scales: {
      x: { ticks: { color: "#8a93a3" }, grid: { color: "#2b313b" } },
      y: { ticks: { color: "#8a93a3" }, grid: { color: "#2b313b" } },
    },
  };
}

// ---------------- panel loader / init ----------------
async function loadPanel(tab) {
  try {
    if (tab === "board") await loadBoard();
    if (tab === "checkinout") { await loadBoard(); populateScanSelect(); }
    if (tab === "usage") await loadUsage();
    if (tab === "alerts") await loadAlerts();
    if (tab === "forecast") await loadForecast();
    if (tab === "anomalies") await loadAnomalies();
  } catch (err) {
    console.error(err);
  }
}

document.getElementById("reseed-btn").addEventListener("click", async () => {
  const btn = document.getElementById("reseed-btn");
  btn.disabled = true;
  btn.textContent = "…";
  await api("/api/reseed", { method: "POST" });
  document.getElementById("filter-site").dataset.populated = "";
  document.getElementById("usage-site-filter").dataset.populated = "";
  document.getElementById("filter-site").innerHTML = `<option value="">All sites</option>`;
  document.getElementById("usage-site-filter").innerHTML = `<option value="">All sites</option>`;
  await loadSummary();
  await loadPanel("board");
  btn.disabled = false;
  btn.textContent = "↻ Resim";
});

(async function init() {
  await loadSummary();
  await loadPanel("board");
  setInterval(loadSummary, 15000);
})();
