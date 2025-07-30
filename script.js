const isLocalhost = window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost";
const BASE_URL = isLocalhost
  ? "http://127.0.0.1:8000"  // Local FastAPI server
  : "https://stockpriceforecast.fly.dev";  // Render deployment

let currentSymbol = "";
let priceInterval;

async function fetchCurrentPrice(symbol) {
  try {
    const res = await fetch(`${BASE_URL}/price?symbol=${symbol}`);
    const data = await res.json();

    const priceEl = document.getElementById("currentPrice");
    const symbolEl = document.getElementById("currentSymbol");

    if (data.error) {
      priceEl.textContent = "N/A";
      symbolEl.textContent = "--";
      return;
    }

    priceEl.textContent = `$${data.price.toFixed(2)}`;
    symbolEl.textContent = data.symbol;
    updateRecent(symbol, data.price);
  } catch (e) {
    document.getElementById("currentPrice").textContent = "N/A";
  }
}

function updateRecent(symbol, price) {
  let recent = JSON.parse(localStorage.getItem("recentStocks")) || [];
  recent = recent.filter(s => s.symbol !== symbol);
  recent.unshift({ symbol, price });
  if (recent.length > 5) recent.pop();
  localStorage.setItem("recentStocks", JSON.stringify(recent));
  renderRecent();
}

function renderRecent() {
  const container = document.getElementById("recentList");
  container.innerHTML = "";
  const recent = JSON.parse(localStorage.getItem("recentStocks")) || [];
  recent.forEach(stock => {
    const card = document.createElement("div");
    card.className = "recent-card";
    card.textContent = `${stock.symbol}: $${stock.price.toFixed(2)}`;
    card.addEventListener("click", () => {
      document.getElementById("symbolInput").value = stock.symbol;
      currentSymbol = stock.symbol;
      fetchCurrentPrice(stock.symbol);
      // Do NOT auto fetch forecast here
      document.querySelector(".chart-section").style.display = "none";
      document.querySelector(".table-section").style.display = "none";
      document.getElementById("forecastBtn").style.display = "block";
    });
    container.appendChild(card);
  });
}

async function fetchForecast() {
  const symbol = currentSymbol;
  if (!symbol) return;
  try {
    const res = await fetch(`${BASE_URL}/forecast?symbol=${symbol}`);
    const data = await res.json();

    if (data.error) {
      alert(data.error);
      return;
    }

    plotChart(data.forecast);
    buildForecastTable(data.forecast);
    document.querySelector(".chart-section").style.display = "block";
    document.querySelector(".table-section").style.display = "block";
  } catch (e) {
    alert("Error loading forecast");
  }
}

function plotChart(data) {
  const ctx = document.getElementById("forecastChart").getContext("2d");
  const labels = data.map(d => d.date);
  const open = data.map(d => d.open);
  const high = data.map(d => d.high);
  const low = data.map(d => d.low);
  const close = data.map(d => d.close);

  if (window.myChart) window.myChart.destroy();
  window.myChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Open", data: open, borderColor: "#ffa600", backgroundColor: "#ffa600", fill: false, tension: 0.3, pointHoverRadius: 6 },
        { label: "High", data: high, borderColor: "#00c853", backgroundColor: "#00c853", fill: false, tension: 0.3, pointHoverRadius: 6 },
        { label: "Low", data: low, borderColor: "#d50000", backgroundColor: "#d50000", fill: false, tension: 0.3, pointHoverRadius: 6 },
        { label: "Close", data: close, borderColor: "#4cffd4", backgroundColor: "#4cffd4", fill: false, tension: 0.3, pointHoverRadius: 6 }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: "#fff" }, position: 'top' },
        tooltip: { enabled: true, mode: 'nearest' }
      },
      scales: {
        x: { ticks: { color: "#ccc" } },
        y: { ticks: { color: "#ccc" } }
      },
      animation: { duration: 1000, easing: 'easeOutQuart' }
    }
  });
}

function buildForecastTable(data) {
  const tbody = document.querySelector("#forecastTable tbody");
  const thead = document.querySelector("#forecastTable thead");
  thead.innerHTML = `
    <tr style="background-color:#222;color:white;">
      <th>Date</th>
      <th>Open</th>
      <th>High</th>
      <th>Low</th>
      <th>Close</th>
    </tr>`;
  tbody.innerHTML = "";
  data.forEach(row => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.date}</td>
      <td>$${row.open}</td>
      <td>$${row.high}</td>
      <td>$${row.low}</td>
      <td>$${row.close}</td>`;
    tr.style.transition = "background-color 0.3s";
    tr.onmouseover = () => tr.style.backgroundColor = "#333";
    tr.onmouseout = () => tr.style.backgroundColor = "";
    tbody.appendChild(tr);
  });
}

window.addEventListener("load", () => {
  renderRecent();
});

document.getElementById("searchBtn").addEventListener("click", () => {
  const symbolInput = document.getElementById("symbolInput");
  const symbol = symbolInput.value.trim().toUpperCase();
  if (!symbol) return;

  currentSymbol = symbol;

  // Hide chart & table on new search
  document.querySelector(".chart-section").style.display = "none";
  document.querySelector(".table-section").style.display = "none";

  // Show forecast button (no inline styles except display)
  const forecastBtn = document.getElementById("forecastBtn");
  forecastBtn.style.display = "block";

  fetchCurrentPrice(symbol);

  // Clear any existing interval and set new one for price updates every 30 seconds
  if (priceInterval) clearInterval(priceInterval);
  priceInterval = setInterval(() => fetchCurrentPrice(symbol), 30000);
});

// Only fetch forecast on button click
document.getElementById("forecastBtn").addEventListener("click", fetchForecast);
