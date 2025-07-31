import requests
import pandas as pd
import numpy as np
from datetime import timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sklearn.ensemble import RandomForestRegressor
from supabase import create_client, Client

# Supabase credentials
SUPABASE_URL = "https://jpnuwenmtlkkrnbiaops.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpwbnV3ZW5tdGxra3JuYmlhb3BzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTM4MTc2OTAsImV4cCI6MjA2OTM5MzY5MH0.S5AltZns5YmsxwDC-KYdfw35w222GphF5qxTmd1M4AI"  # keep secret
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# API Keys
FINNHUB_API_KEY = "d258bt1r01qns40dnuc0d258bt1r01qns40dnucg"
ALPHA_VANTAGE_API_KEY = "NVHS1RSTQTRKIJR7"

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

@app.get("/search-symbol")
def search_symbol(query: str):
    try:
        url = f"https://finnhub.io/api/v1/search?q={query}&token={FINNHUB_API_KEY}"
        res = requests.get(url).json()
        results = res.get("result", [])
        suggestions = [
            {"symbol": item["symbol"], "name": item["description"]}
            for item in results if item.get("symbol") and item.get("description")
        ]
        return {"results": suggestions}
    except Exception as e:
        return {"error": str(e)}


@app.get("/price")
def get_price(symbol: str):
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
    try:
        res = requests.get(url).json()
        if not res or "c" not in res:
            return {"error": "Could not retrieve price"}
        return {"symbol": symbol.upper(), "price": float(res["c"])}
    except Exception as e:
        return {"error": str(e)}

@app.get("/details")
def get_company_details(symbol: str):
    try:
        url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={FINNHUB_API_KEY}"
        res = requests.get(url)
        if res.status_code != 200:
            return {"error": "API request failed"}
        data = res.json()
        return {
            "name": data.get("name", "N/A"),
            "logo": data.get("logo", ""),
            "symbol": data.get("ticker", symbol.upper())
        }
    except Exception as e:
        return {"error": str(e)}

def save_forecast_to_db(symbol: str, forecast: list):
    for row in forecast:
        date = row["date"]
        exists = supabase.table("forecast_data")\
            .select("id")\
            .eq("symbol", symbol.upper())\
            .eq("date", date)\
            .execute()

        if not exists.data:
            supabase.table("forecast_data").insert({
                "symbol": symbol.upper(),
                "date": date,
                "open": row.get("open", 0.0),
                "high": row.get("high", 0.0),
                "low": row.get("low", 0.0),
                "close": row.get("close", 0.0)
            }).execute()

@app.get("/forecast")
def forecast(symbol: str):
    try:
        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}"
        res = requests.get(url).json()
        time_series = res.get("Time Series (Daily)", {})

        if not time_series:
            return {"symbol": symbol.upper(), "forecast": []}

        df = pd.DataFrame.from_dict(time_series, orient="index")
        df.rename(columns={
            "1. open": "Open",
            "2. high": "High",
            "3. low": "Low",
            "4. close": "Close"
        }, inplace=True)

        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df.astype(float)

        # Create lag features
        for lag in range(1, 4):
            for col in ["Open", "High", "Low", "Close"]:
                df[f"{col}_lag{lag}"] = df[col].shift(lag)

        df.dropna(inplace=True)
        feature_cols = [col for col in df.columns if "lag" in col]
        target_cols = ["Open", "High", "Low", "Close"]

        models = {}
        for col in target_cols:
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(df[feature_cols], df[col])
            models[col] = model

        forecast = []
        last_known = df.iloc[-3:].copy()  # Only keep 3 rows to manage lag logic
        last_date = df.index[-1]

        for _ in range(7):
            # Create input features from last 3 known rows
            input_features = {}
            for col in target_cols:
                input_features[f"{col}_lag1"] = last_known.iloc[-1][col]
                input_features[f"{col}_lag2"] = last_known.iloc[-2][col]
                input_features[f"{col}_lag3"] = last_known.iloc[-3][col]

            next_date = last_date + timedelta(days=1)
            while next_date.weekday() >= 5:
                next_date += timedelta(days=1)

            prediction = {"date": str(next_date.date())}
            new_row = {}

            for col in target_cols:
                input_df = pd.DataFrame([list(input_features.values())], columns=feature_cols)
                pred = models[col].predict(input_df)[0]
                prediction[col.lower()] = round(pred, 2)
                new_row[col] = pred

            forecast.append(prediction)

            # Prepare new_row for next prediction cycle with updated lags
            for col in target_cols:
                new_row[f"{col}_lag1"] = input_features[f"{col}_lag1"]
                new_row[f"{col}_lag2"] = input_features[f"{col}_lag2"]
                new_row[f"{col}_lag3"] = input_features[f"{col}_lag3"]

            new_row_df = pd.DataFrame([new_row], index=[next_date])
            last_known = pd.concat([last_known, new_row_df])
            last_known = last_known.iloc[-3:]  # Keep only last 3 rows
            last_date = next_date

        save_forecast_to_db(symbol, forecast)
        return {"symbol": symbol.upper(), "forecast": forecast}

    except Exception as e:
        print(f"Error in /forecast: {e}")
        return {"error": str(e)}

