const API_BASE = window.LFS_API_BASE || "";

const markets = ["USD/MXN OTC", "USD/PKR OTC", "EUR/CHF OTC"];
let selected = markets[0];

function $(id) { return document.getElementById(id); }

function selectMarket(symbol) {
  selected = symbol;
  document.querySelectorAll(".market-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.symbol === symbol);
  });
  refreshSignal();
}

function renderSignal(data) {
  const status = data.status || "WAITING";
  $("status").textContent = status.replaceAll("_", " ");
  $("pattern").textContent = data.pattern_id || "—";
  $("matches").textContent = data.matches ?? "—";
  $("up").textContent = data.up_probability != null ? data.up_probability + "%" : "—";
  $("down").textContent = data.down_probability != null ? data.down_probability + "%" : "—";
  $("direction").textContent = data.direction || "WAITING";
  $("note").textContent = data.reason || (
    data.direction && data.direction !== "WAITING"
      ? "Historical pattern probability only — not a guaranteed outcome."
      : "Waiting for enough completed 5-minute candles."
  );
}

async function refreshSignal() {
  try {
    const res = await fetch(API_BASE + "/api/signal/" + encodeURIComponent(selected));
    if (!res.ok) throw new Error("API error");
    renderSignal(await res.json());
  } catch (e) {
    $("status").textContent = "OFFLINE";
    $("note").textContent = "Backend is unreachable.";
  }
}

async function checkHealth() {
  try {
    const res = await fetch(API_BASE + "/health");
    const data = await res.json();
    $("connection").textContent = data.live_provider_configured ? "LIVE READY" : "ENGINE READY";
  } catch {
    $("connection").textContent = "OFFLINE";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const container = $("markets");
  markets.forEach(symbol => {
    const btn = document.createElement("button");
    btn.className = "market-btn";
    btn.dataset.symbol = symbol;
    btn.textContent = symbol;
    btn.onclick = () => selectMarket(symbol);
    container.appendChild(btn);
  });
  selectMarket(selected);
  checkHealth();
  setInterval(refreshSignal, 5000);
  setInterval(checkHealth, 15000);
});
