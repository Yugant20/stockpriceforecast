import yfinance as yf
import pandas as pd
import numpy as np
from datetime import timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sklearn.ensemble import RandomForestRegressor
from supabase import create_client, Client

# Supabase credentials
SUPABASE_URL = "https://jpnuwenmtlkkrnbiaops.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpwbnV3ZW5tdGxra3JuYmlhb3BzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTM4MTc2OTAsImV4cCI6MjA2OTM5MzY5MH0.S5AltZns5YmsxwDC-KYdfw35w222GphF5qxTmd1M4AI"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    return {"message": "Stock Forecast API running with Supabase SQL"}

def save_forecast_to_db(symbol: str, forecast: list):
    for row in forecast:
        supabase.table("forecast_data").insert({
            "symbol": symbol.upper(),
            "date": row["date"],
            "open": row.get("open", 0.0),
            "high": row.get("high", 0.0),
            "low": row.get("low", 0.0),
            "close": row.get("close", 0.0)
        }).execute()

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

        save_forecast_to_db(symbol, forecast)
        return {"symbol": symbol.upper(), "forecast": forecast}

    except Exception as e:
        print(f"Error in /forecast: {e}")
        return {"error": str(e)}
