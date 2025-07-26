import yfinance as yf
import pandas as pd
import numpy as np
import csv
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import timedelta
from sklearn.linear_model import LinearRegression

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 🔽 Utility: Save forecast to CSV (avoid duplicates)
def save_forecast_to_csv(symbol: str, forecast: list):
    filename = "forecast_data.csv"
    existing_rows = set()

    # Read existing rows
    if os.path.exists(filename):
        with open(filename, mode="r", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                existing_rows.add((row["symbol"], row["date"]))

    # Append only new rows
    with open(filename, mode="a", newline="") as file:
        fieldnames = ["symbol", "date", "open", "high", "low", "close"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if os.path.getsize(filename) == 0:
            writer.writeheader()

        for day in forecast:
            key = (symbol.upper(), day["date"])
            if key not in existing_rows:
                writer.writerow({
                    "symbol": symbol.upper(),
                    "date": day["date"],
                    "open": day.get("open", ""),
                    "high": day.get("high", ""),
                    "low": day.get("low", ""),
                    "close": day.get("close", "")
                })


# ✅ Get current stock price
@app.get("/price")
def get_price(symbol: str):
    data = yf.download(symbol, period="7d", interval="1d", progress=False)
    if data.empty:
        return {"error": "Invalid symbol or no data"}
    latest_price = data["Close"].iloc[-1]
    return {"symbol": symbol.upper(), "price": float(latest_price)}


# ✅ Get 7-day forecast
@app.get("/forecast")
def forecast(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="60d", interval="1d")

        if df.empty:
            return {"error": "No data found for symbol"}

        df = df.reset_index()
        columns_needed = ["Open", "High", "Low", "Close"]
        available_cols = [col for col in columns_needed if col in df.columns]
        df = df.dropna(subset=available_cols)

        if len(df) < 30:
            return {"error": "Not enough data to forecast"}

        df = df[-30:]
        X = np.arange(len(df)).reshape(-1, 1)

        models = {}
        for col in available_cols:
            y = df[col].values.reshape(-1, 1)
            model = LinearRegression()
            model.fit(X, y)
            models[col] = model

        forecast = []
        last_date = df["Date"].iloc[-1]
        day_offset = 1

        while len(forecast) < 7:
            next_day = last_date + timedelta(days=1)
            last_date = next_day
            if next_day.weekday() < 5:
                future_index = len(X) + day_offset
                prediction = {
                    "date": str(next_day.date())
                }
                for col in models:
                    prediction[col.lower()] = round(float(models[col].predict([[future_index]])[0][0]), 2)
                forecast.append(prediction)
            day_offset += 1

        save_forecast_to_csv(symbol, forecast)  # ⬅️ Save to CSV here

        return {"symbol": symbol.upper(), "forecast": forecast}

    except Exception as e:
        print(f"Error in /forecast: {e}")
        return {"error": str(e)}
