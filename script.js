const isLocalhost = window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost";
const BASE_URL = isLocalhost
  ? "http://127.0.0.1:8000"
  : "https://stockpriceforecast.fly.dev";  

let currentSymbol = "";
let priceInterval;
let currentPeriod = "1M";
let historicalData = [];
let forecastData = [];

async function fetchCurrentPrice(symbol) {
  try {
    const [priceRes, detailsRes] = await Promise.all([
      fetch(`${BASE_URL}/price?symbol=${symbol}`),
      fetch(`${BASE_URL}/details?symbol=${symbol}`)
    ]);

    const priceData = await priceRes.json();
    const detailsData = await detailsRes.json();

    const priceEl = document.getElementById("currentPrice");
    const symbolEl = document.getElementById("currentSymbol");

    if (priceData.error || detailsData.error) {
      priceEl.textContent = "N/A";
      symbolEl.textContent = "--";
      return;
    }

    priceEl.textContent = `$${priceData.price.toFixed(2)}`;
    symbolEl.textContent = `${detailsData.name} (${detailsData.symbol})`;

    if (detailsData.logo) {
      let logo = document.getElementById("stockLogo");
      if (!logo) {
        logo = document.createElement("img");
        logo.id = "stockLogo";
        logo.style.height = "30px";
        logo.style.marginLeft = "10px";
        document.querySelector("#currentDisplay h2").appendChild(logo);
      }
      logo.src = detailsData.logo;
    }

    updateRecent(symbol, priceData.price);
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
      document.querySelector(".chart-section").style.display = "none";
      document.querySelector(".table-section").style.display = "none";
      document.getElementById("forecastBtn").style.display = "block";
    });
    container.appendChild(card);
  });
}

async function fetchHistoricalData(symbol, period) {
  try {
    const res = await fetch(`${BASE_URL}/historical?symbol=${symbol}&period=${period}`);
    const data = await res.json();
    
    if (data.error) {
      console.error("Error fetching historical data:", data.error);
      return [];
    }
    
    return data.historical || [];
  } catch (e) {
    console.error("Error fetching historical data:", e);
    return [];
  }
}

async function fetchForecast() {
  const symbol = currentSymbol;
  if (!symbol) return;
  
  try {
    // Fetch both historical and forecast data
    const [historicalRes, forecastRes] = await Promise.all([
      fetchHistoricalData(symbol, currentPeriod),
      fetch(`${BASE_URL}/forecast?symbol=${symbol}`)
    ]);
    
    historicalData = historicalRes;
    const forecastResult = await forecastRes.json();
    
    if (forecastResult.error) {
      alert(forecastResult.error);
      return;
    }
    
    forecastData = forecastResult.forecast || [];
    
    // Show time period buttons and chart
    showTimePeriodButtons();
    plotCombinedChart(historicalData, forecastData);
    buildForecastTable(forecastData);
    document.querySelector(".chart-section").style.display = "block";
    document.querySelector(".table-section").style.display = "block";
  } catch (e) {
    console.error("Error loading forecast:", e);
    alert("Error loading forecast");
  }
}

function showTimePeriodButtons() {
  // Check if buttons already exist
  if (document.querySelector('.time-period-buttons')) {
    return;
  }
  
  const chartSection = document.querySelector(".chart-section");
  const buttonContainer = document.createElement("div");
  buttonContainer.className = "time-period-buttons";
  buttonContainer.style.cssText = `
    display: flex;
    justify-content: center;
    gap: 10px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  `;
  
  const periods = ["1W", "1M", "3M", "6M", "1Y"];
  
  periods.forEach(period => {
    const button = document.createElement("button");
    button.textContent = period;
    button.className = period === currentPeriod ? "period-btn active" : "period-btn";
    button.style.cssText = `
      padding: 8px 16px;
      border: none;
      border-radius: 6px;
      background-color: ${period === currentPeriod ? '#00cfff' : '#444'};
      color: ${period === currentPeriod ? '#000' : '#fff'};
      cursor: pointer;
      font-weight: bold;
      transition: all 0.3s ease;
    `;
    
    button.addEventListener("click", async () => {
      // Update active button
      document.querySelectorAll('.period-btn').forEach(btn => {
        btn.style.backgroundColor = '#444';
        btn.style.color = '#fff';
        btn.classList.remove('active');
      });
      button.style.backgroundColor = '#00cfff';
      button.style.color = '#000';
      button.classList.add('active');
      
      currentPeriod = period;
      
      // Fetch new historical data
      const newHistoricalData = await fetchHistoricalData(currentSymbol, period);
      historicalData = newHistoricalData;
      
      // Update chart
      plotCombinedChart(historicalData, forecastData);
    });
    
    buttonContainer.appendChild(button);
  });
  
  chartSection.insertBefore(buttonContainer, chartSection.firstChild);
}

function plotCombinedChart(historical, forecast) {
  const ctx = document.getElementById("forecastChart").getContext("2d");
  
  // Prepare historical data
  const historicalLabels = historical.map(d => d.date);
  const historicalOpen = historical.map(d => d.open);
  const historicalHigh = historical.map(d => d.high);
  const historicalLow = historical.map(d => d.low);
  const historicalClose = historical.map(d => d.close);
  
  // Prepare forecast data
  const forecastLabels = forecast.map(d => d.date);
  const forecastOpen = forecast.map(d => d.open);
  const forecastHigh = forecast.map(d => d.high);
  const forecastLow = forecast.map(d => d.low);
  const forecastClose = forecast.map(d => d.close);
  
  // Combine labels
  const allLabels = [...historicalLabels, ...forecastLabels];
  
  // Create datasets with null values to separate historical and forecast
  const createDataset = (historicalData, forecastData, label, color, forecastColor) => {
    const combinedData = [
      ...historicalData,
      ...new Array(forecastData.length).fill(null)
    ];
    
    const forecastDataset = [
      ...new Array(historicalData.length).fill(null),
      ...forecastData
    ];
    
    return [
      {
        label: `${label} (Historical)`,
        data: combinedData,
        borderColor: color,
        backgroundColor: color,
        fill: false,
        tension: 0.2,
        pointRadius: 1,
        pointHoverRadius: 4
      },
      {
        label: `${label} (Forecast)`,
        data: forecastDataset,
        borderColor: forecastColor,
        backgroundColor: forecastColor,
        fill: false,
        tension: 0.2,
        pointRadius: 2,
        pointHoverRadius: 5,
        borderDash: [5, 5], // Dashed line for forecast
        pointStyle: 'triangle'
      }
    ];
  };
  
  if (window.myChart) window.myChart.destroy();
  
  const datasets = [
    ...createDataset(historicalOpen, forecastOpen, "Open", "#ffa600", "#ffcc66"),
    ...createDataset(historicalHigh, forecastHigh, "High", "#00c853", "#66ff99"),
    ...createDataset(historicalLow, forecastLow, "Low", "#d50000", "#ff6666"),
    ...createDataset(historicalClose, forecastClose, "Close", "#4cffd4", "#80ffea")
  ];
  
  window.myChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: allLabels,
      datasets: datasets
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { 
          labels: { color: "#fff" }, 
          position: 'top',
          onClick: function(e, legendItem) {
            const index = legendItem.datasetIndex;
            const chart = this.chart;
            const isVisible = chart.isDatasetVisible(index);
            chart.setDatasetVisibility(index, !isVisible);
            chart.update();
          }
        },
        tooltip: { 
          enabled: true, 
          mode: 'nearest',
          callbacks: {
            title: function(context) {
              return context[0].label;
            },
            label: function(context) {
              const datasetLabel = context.dataset.label;
              const value = context.parsed.y;
              return value !== null ? `${datasetLabel}: $${value.toFixed(2)}` : null;
            }
          }
        }
      },
      scales: {
        x: { 
          ticks: { color: "#ccc" },
          grid: { color: "#333" }
        },
        y: { 
          ticks: { 
            color: "#ccc",
            callback: function(value) {
              return '$' + value.toFixed(2);
            }
          },
          grid: { color: "#333" }
        }
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

  document.querySelector(".chart-section").style.display = "none";
  document.querySelector(".table-section").style.display = "none";
  
  // Remove existing time period buttons
  const existingButtons = document.querySelector('.time-period-buttons');
  if (existingButtons) {
    existingButtons.remove();
  }

  const forecastBtn = document.getElementById("forecastBtn");
  forecastBtn.style.display = "block";

  fetchCurrentPrice(symbol);

  if (priceInterval) clearInterval(priceInterval);
  priceInterval = setInterval(() => fetchCurrentPrice(symbol), 30000);
});

document.getElementById("forecastBtn").addEventListener("click", fetchForecast);

// Dropdown Suggestions
const input = document.getElementById("symbolInput");
const dropdown = document.getElementById("suggestionsList");

input.addEventListener("input", async () => {
  const query = input.value.trim();
  if (query.length < 2) {
    dropdown.innerHTML = "";
    return;
  }

  try {
    const res = await fetch(`${BASE_URL}/search-symbol?query=${query}`);
    const data = await res.json();

    dropdown.innerHTML = "";
    data.results.forEach(({ symbol, name }) => {
      const li = document.createElement("li");
      li.textContent = `${symbol} - ${name}`;
      li.className = "dropdown-item";
      li.onclick = () => {
        input.value = symbol;
        dropdown.innerHTML = "";
      };
      dropdown.appendChild(li);
    });
  } catch (err) {
    dropdown.innerHTML = "";
  }
});