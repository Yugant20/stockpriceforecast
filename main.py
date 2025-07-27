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
    filename_abs = os.path.abspath(filename)
    print(f"Saving CSV to: {filename_abs}")

    existing_rows = set()

    if os.path.exists(filename):
        with open(filename, mode="r", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                existing_rows.add((row["symbol"], row["date"]))
        print(f"Found existing CSV file with {len(existing_rows)} entries")
    else:
        print(f"No existing CSV file found, creating new one.")

    with open(filename, mode="a", newline="") as file:
        fieldnames = ["symbol", "date", "open", "high", "low", "close"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if os.path.getsize(filename) == 0:
            print("CSV file empty, writing header.")
            writer.writeheader()

        for day in forecast:
            key = (symbol.upper(), day["date"])
            if key not in existing_rows:
                print(f"Writing new row for {key}")
                writer.writerow({
                    "symbol": symbol.upper(),
                    "date": day["date"],
                    "open": day.get("open", ""),
                    "high": day.get("high", ""),
                    "low": day.get("low", ""),
                    "close": day.get("close", "")
                })
            else:
                print(f"Skipping duplicate row for {key}")

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
        
        # Flatten columns if multiindex present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty:
            return {"error": "No data found for symbol"}

        required_cols = ["Open", "High", "Low", "Close"]
        available_cols = [col for col in required_cols if col in df.columns]
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
        last_date = df.index[-1]
        future_index = len(X)

        while len(forecast) < 7:
            last_date += timedelta(days=1)
            if last_date.weekday() < 5:
                prediction = {"date": str(last_date.date())}
                for col in models:
                    prediction[col.lower()] = round(float(models[col].predict([[future_index]])[0][0]), 2)
                forecast.append(prediction)
                future_index += 1

        save_forecast_to_csv(symbol, forecast)

        return {"symbol": symbol.upper(), "forecast": forecast}
    except Exception as e:
        print(f"Error in /forecast: {e}")
        return {"error": str(e)}
