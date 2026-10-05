const API_BASE = window.LFS_API_BASE || "";

const markets = ["USD/MXN OTC", "USD/PKR OTC", "EUR/CHF OTC"];
let selected = markets[0];

function $(id) { return document.getElementById(id); }

function selectMarket(symbol) {
  selected = symbol;
  document.querySelectorAll(".market-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.symbol === symbol);
  });
  $("symbol").textContent = symbol;
  refreshSignal();
}

function renderSignal(data) {
  const status = data.status || "WAITING";
  $("status").textContent = status.replaceAll("_", " ");
  $("signal").textContent = data.direction || "WAITING";
  $("pattern").textContent = data.pattern_id || "—";
  $("matches").textContent = data.matches ?? "—";
  $("up").textContent = data.up_probability != null ? data.up_probability + "%" : "—";
  $("down").textContent = data.down_probability != null ? data.down_probability + "%" : "—";

  const mode = data.mode === "LIVE" ? "LIVE" : "HISTORICAL";
  $("mode").textContent = mode;
  $("note").textContent = data.note || data.reason ||
    (data.direction && data.direction !== "WAITING"
      ? "Historical pattern probability only — not a guaranteed outcome."
      : "Waiting for enough completed 5-minute candles.");
}

async function refreshSignal() {
  try {
    const res = await fetch(API_BASE + "/api/signal/" + encodeURIComponent(selected));
    if (!res.ok) throw new Error("API error");
    renderSignal(await res.json());
  } catch (e) {
    $("status").textContent = "OFFLINE";
    $("signal").textContent = "WAITING";
    $("note").textContent = "Backend is unreachable.";
  }
}

async function checkHealth() {
  try {
    const res = await fetch(API_BASE + "/health");
    const data = await res.json();
    $("connection").textContent =
      data.provider_status === "LIVE_RUNNING" ? "LIVE" :
      data.provider_status === "BOOK_ACCESS_MISMATCH" ? "OTC BOOK ACCESS ERROR" :
      data.provider_status === "VENUE_NOT_OPEN" ? "VENUE NOT OPEN" :
      data.provider_status === "LIVE_STREAMING_UNAVAILABLE" ? "HISTORICAL MODE" :
      data.live_provider_configured ? "HISTORICAL MODE" : "SETUP REQUIRED";
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
