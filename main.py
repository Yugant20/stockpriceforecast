import yfinance as yf
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import timedelta
from sklearn.linear_model import LinearRegression

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/price")
def get_price(symbol: str):
    data = yf.download(symbol, period="7d", interval="1d", progress=False)
    if data.empty:
        return {"error": "Invalid symbol or no data"}
    latest_price = data["Close"].iloc[-1]
    return {"symbol": symbol.upper(), "price": float(latest_price)}

@app.get("/forecast")
def forecast(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="6mo", interval="1d")
        if df.empty:
            return {"error": "No data found for symbol"}
        df = df.reset_index()
        all_possible = ["Open", "High", "Low", "Close", "Adj Close"]
        available_cols = [col for col in all_possible if col in df.columns]
        if not available_cols:
            return {"error": "No usable price columns found"}
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
            next_day = last_date + timedelta(days=day_offset)
            if next_day.weekday() < 5:
                future_index = len(X) + day_offset
                pred = {"date": str(next_day.date())}
                for col in models:
                    pred[col.lower().replace(" ", "_")] = round(float(models[col].predict([[future_index]])[0][0]), 2)
                forecast.append(pred)
            day_offset += 1
        return {"symbol": symbol.upper(), "forecast": forecast}
    except Exception as e:
        return {"error": str(e)}