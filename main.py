import yfinance as yf
import pandas as pd
import numpy as np
import csv
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import timedelta
from sklearn.ensemble import RandomForestRegressor

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Stock Forecast API running"}


def save_forecast_to_csv(symbol: str, forecast: list):
    filename = "forecast_data.csv"
    symbol = symbol.upper()
    existing_rows = set()

    # Read existing symbol-date pairs to avoid duplicates
    if os.path.exists(filename):
        with open(filename, mode="r", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                existing_rows.add((row["symbol"].strip().upper(), row["date"].strip()))

    with open(filename, mode="a", newline="") as file:
        fieldnames = ["symbol", "date", "open", "high", "low", "close"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if os.path.getsize(filename) == 0:
            print("Writing CSV header")
            writer.writeheader()

        saved_count = 0
        for day in forecast:
            key = (symbol, day["date"].strip())
            if key not in existing_rows:
                writer.writerow({
                    "symbol": symbol,
                    "date": day["date"],
                    "open": float(day.get("open", 0)),
                    "high": float(day.get("high", 0)),
                    "low": float(day.get("low", 0)),
                    "close": float(day.get("close", 0))
                })
                print(f"Saved forecast for {symbol} on {day['date']}")
                saved_count += 1
                existing_rows.add(key)
            else:
                print(f"Skipped duplicate: {symbol} on {day['date']}")

        if saved_count == 0:
            print(f"No new forecasts saved for {symbol}")


@app.get("/price")
def get_price(symbol: str):
    try:
        data = yf.download(symbol, period="7d", interval="1d", progress=False)
        if data.empty or "Close" not in data.columns:
            return {"error": "Invalid symbol or no data"}
        latest_price = data["Close"].iloc[-1]
        return {"symbol": symbol.upper(), "price": float(latest_price)}
    except Exception as e:
        return {"error": str(e)}

@app.get("/forecast")
def forecast(symbol: str):
    try:
        df = yf.download(symbol, period="6mo", interval="1d", progress=False)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty:
            return {"symbol": symbol.upper(), "forecast": []}

        required_cols = ["Open", "High", "Low", "Close"]
        available_cols = [col for col in required_cols if col in df.columns]
        df = df.dropna(subset=available_cols)

        if len(df) < 7:
            return {"symbol": symbol.upper(), "forecast": []}
        elif len(df) >= 30:
            df = df[-30:]
        else:
            df = df[-len(df):]

        X = np.arange(len(df)).reshape(-1, 1)
        models = {}

        for col in available_cols:
            y = df[col].values.reshape(-1, 1)
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X, y.ravel())
            models[col] = model

        forecast = []
        last_date = df.index[-1]
        future_index = len(X)

        while len(forecast) < 7:
            last_date += timedelta(days=1)
            if last_date.weekday() < 5:
                prediction = {"date": str(last_date.date())}
                for col in models:
                    pred = models[col].predict([[future_index]])[0]
                    prediction[col.lower()] = round(float(pred), 2)
                forecast.append(prediction)
                future_index += 1

        # DEBUG LINE TO SEE WHAT DATES ARE GENERATED
        print("Generated forecast dates:", [f['date'] for f in forecast])

        save_forecast_to_csv(symbol, forecast)
        return {"symbol": symbol.upper(), "forecast": forecast}

    except Exception as e:
        print(f"Error in /forecast: {e}")
        return {"error": str(e)}
