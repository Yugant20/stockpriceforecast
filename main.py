import requests
import pandas as pd
from datetime import timedelta
import yfinance as yf
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from xgboost import XGBRegressor
from supabase import create_client, Client

SUPABASE_URL = "https://jpnuwenmtlkkrnbiaops.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpwbnV3ZW5tdGxra3JuYmlhb3BzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTM4MTc2OTAsImV4cCI6MjA2OTM5MzY5MH0.S5AltZns5YmsxwDC-KYdfw35w222GphF5qxTmd1M4AI"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

FINNHUB_API_KEY = "d279ig9r01qloari4pn0d279ig9r01qloari4png"
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

@app.get("/historical")
def get_historical_data(symbol: str, period: str = "1M"):
    try:
        periods_map = {
            "1W": "7d", "1M": "1mo", "3M": "3mo",
            "6M": "6mo", "1Y": "1y"
        }
        yf_period = periods_map.get(period, "1mo")
        df = yf.download(symbol, period=yf_period, interval="1d", progress=False, auto_adjust=True)
        
        if df.empty:
            return {
                "symbol": symbol.upper(),
                "period": period,
                "historical": [],
                "error": "No data found for this symbol"
            }
        
        if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
            df.columns = df.columns.droplevel(1)
            
        df = df.dropna().reset_index()
        
        if df.empty:
            return {
                "symbol": symbol.upper(),
                "period": period,
                "historical": [],
                "error": "No valid data after cleaning"
            }
        
        historical_data = []
        for _, row in df.iterrows():
            try:
                date_val = row["Date"]
                if hasattr(date_val, 'strftime'):
                    date_str = date_val.strftime("%m-%d-%y")
                else:
                    date_str = str(date_val)[:10]
                
                historical_data.append({
                    "date": date_str,
                    "open": round(row["Open"] if pd.api.types.is_scalar(row["Open"]) else row["Open"].iloc[0], 2),
                    "high": round(row["High"] if pd.api.types.is_scalar(row["High"]) else row["High"].iloc[0], 2),
                    "low": round(row["Low"] if pd.api.types.is_scalar(row["Low"]) else row["Low"].iloc[0], 2),
                    "close": round(row["Close"] if pd.api.types.is_scalar(row["Close"]) else row["Close"].iloc[0], 2)
                })
            except Exception as row_error:
                continue

        return {
            "symbol": symbol.upper(),
            "period": period,
            "historical": historical_data
        }

    except Exception as e:
        return {"error": str(e)}

def save_forecast_to_db(symbol: str, forecast: list):
    try:
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
    except Exception:
        pass

@app.get("/forecast")
def forecast(symbol: str):
    try:
        df = yf.download(symbol, period="1y", interval="1d", progress=False, auto_adjust=True)
        
        if df.empty:
            return {
                "symbol": symbol.upper(),
                "forecast": [],
                "error": f"No data found for symbol {symbol}. Please check if the symbol is valid."
            }
        
        df = df.dropna().reset_index()
        
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.droplevel(1)
        
        if len(df) < 10:
            return {
                "symbol": symbol.upper(),
                "forecast": [],
                "error": "Not enough historical data (at least 10 days required) to generate a forecast."
            }

        required_columns = ["Date", "Open", "High", "Low", "Close"]
        available_columns = df.columns.tolist()
        
        missing_columns = [col for col in required_columns if col not in available_columns]
        if missing_columns:
            return {
                "symbol": symbol.upper(),
                "forecast": [],
                "error": f"Missing required columns: {missing_columns}"
            }
        
        df = df[required_columns].copy()
        df.rename(columns={"Date": "date"}, inplace=True)
        df.set_index("date", inplace=True)
        df = df.sort_index()

        original_length = len(df)
        for lag in range(1, 4):
            for col in ["Open", "High", "Low", "Close"]:
                df[f"{col}_lag{lag}"] = df[col].shift(lag)

        df.dropna(inplace=True)

        if len(df) < 5:
            return {
                "symbol": symbol.upper(),
                "forecast": [],
                "error": f"Not enough historical data after feature engineering. Need at least 5 rows, got {len(df)}."
            }
        
        feature_cols = [col for col in df.columns if "lag" in col]
        target_cols = ["Open", "High", "Low", "Close"]
        
        if len(feature_cols) != 12:
            return {
                "symbol": symbol.upper(),
                "forecast": [],
                "error": f"Expected 12 feature columns, got {len(feature_cols)}"
            }

        models = {}
        for col in target_cols:
            model = XGBRegressor(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=3,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                verbosity=0
            )
            model.fit(df[feature_cols], df[col])
            models[col] = model

        forecast_data = []
        
        if len(df) < 3:
            return {
                "symbol": symbol.upper(),
                "forecast": [],
                "error": f"Not enough data for forecasting. Need at least 3 rows, got {len(df)}."
            }
            
        last_known = df.tail(3).copy()
        last_date = df.index[-1]

        for day in range(7):
            try:
                if len(last_known) < 3:
                    break
                
                input_features = {}
                for col in target_cols:
                    try:
                        val1 = last_known.iloc[-1][col]
                        val2 = last_known.iloc[-2][col]
                        val3 = last_known.iloc[-3][col]
                        
                        input_features[f"{col}_lag1"] = float(val1) if pd.api.types.is_scalar(val1) else float(val1.iloc[0])
                        input_features[f"{col}_lag2"] = float(val2) if pd.api.types.is_scalar(val2) else float(val2.iloc[0])
                        input_features[f"{col}_lag3"] = float(val3) if pd.api.types.is_scalar(val3) else float(val3.iloc[0])
                    except IndexError:
                        raise

                next_date = last_date + timedelta(days=1)
                while next_date.weekday() >= 5:
                    next_date += timedelta(days=1)

                prediction = {"date": next_date.strftime("%m/%d/%Y")}
                new_row = {}

                for col in target_cols:
                    try:
                        input_df = pd.DataFrame([input_features], columns=feature_cols)
                        pred = models[col].predict(input_df)[0]
                        prediction[col.lower()] = round(float(pred), 2)
                        new_row[col] = float(pred)
                    except Exception:
                        raise

                forecast_data.append(prediction)

                new_row_data = {}
                for col in target_cols:
                    new_row_data[col] = new_row[col]
                    val1 = last_known.iloc[-1][col]
                    val2 = last_known.iloc[-2][col]
                    val3 = last_known.iloc[-3][col]
                    
                    new_row_data[f"{col}_lag1"] = float(val1) if pd.api.types.is_scalar(val1) else float(val1.iloc[0])
                    new_row_data[f"{col}_lag2"] = float(val2) if pd.api.types.is_scalar(val2) else float(val2.iloc[0])
                    new_row_data[f"{col}_lag3"] = float(val3) if pd.api.types.is_scalar(val3) else float(val3.iloc[0])

                new_row_df = pd.DataFrame([new_row_data], index=[next_date])
                
                last_known = pd.concat([last_known, new_row_df])
                last_known = last_known.tail(3)
                last_date = next_date

            except Exception:
                break

        if forecast_data:
            save_forecast_to_db(symbol, forecast_data)
        
        return {"symbol": symbol.upper(), "forecast": forecast_data}

    except Exception as e:
        return {
            "symbol": symbol.upper(),
            "forecast": [],
            "error": f"Exception: {str(e)}"
        }