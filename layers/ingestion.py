import os
import sys
import time
from datetime import datetime, UTC
from typing import List

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from db.database import get_session
from db.db_models import MarketData
import yfinance as yf  # Add this import for yfinance

# -------------------------------------------------------------
# Ingestion layer for periodic market-data pulls from Polygon.io
# -------------------------------------------------------------
# This script fetches live snapshot data for a small universe of
# stocks every 15 minutes (free-tier limit: 5 requests/minute).
# The data is stored in the MarketData table for frontend display.
# -------------------------------------------------------------

# Load .env so that POLYGON_API_KEY is available when running
# `python ingestion.py` directly OR when imported by Flask.
load_dotenv()

POLYGON_API_KEY: str | None = os.getenv("POLYGON_API_KEY")
if not POLYGON_API_KEY:
    sys.stderr.write(
        "[INGEST] ❌  Environment variable `POLYGON_API_KEY` is missing. "
        "Create one at https://polygon.io and add it to your .env file.\n"
    )
    sys.exit(1)

# ----- Configuration --------------------------------------------------------
# These are the 5 high-liquidity, high-market-cap US equities we pull on the
# free plan. Adjust as needed as long as total requests ≦ 5/min.
TICKERS: List[str] = [
    "AAPL",  # Apple Inc.
    "MSFT",  # Microsoft Corp.
    "GOOGL",  # Alphabet Inc. (Class A)
    "AMZN",  # Amazon.com Inc.
    "TSLA",  # Tesla Inc.
]

# Polygon endpoint template – we use the ticker details endpoint which is available
# on the free tier and provides essential stock information including price data.
TICKER_URL = (
    "https://api.polygon.io/v2/aggs/ticker/{ticker}/prev"
)

# Company names mapping
COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com Inc.",
    "TSLA": "Tesla Inc."
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
 
def fetch_prev_agg(ticker: str) -> dict:
    """Return previous-day OHLC aggregate from Polygon's free `/prev` endpoint."""
    url = TICKER_URL.format(ticker=ticker.upper())
    params = {"apiKey": POLYGON_API_KEY, "adjusted": "true"}
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()

def calculate_percentage_change(open_price: float, close_price: float) -> float:
    """Calculate percentage change between open and close prices."""
    return ((close_price - open_price) / open_price) * 100

def store_market_data(ticker: str, data: dict) -> None:
    """Store market data in the database."""
    if not data.get("results"):
        return

    r = data["results"][0]
    db_session = get_session()
    
    # Calculate percentage change
    pct_change = calculate_percentage_change(r["o"], r["current"])
    
    # Create new market data entry
    market_data = MarketData(
        symbol=ticker,
        company_name=COMPANY_NAMES.get(ticker),
        type='stock',
        open_value=r["o"],
        high_value=r["h"],
        low_value=r["l"],
        current_value=r["current"],
        percentage_change=pct_change,
        volume=r["v"],
        timestamp=datetime.now(UTC)
    )
    
    try:
        db_session.add(market_data)
        db_session.commit()
        print(f"  • {ticker:5}  O:{r['o']:.2f}  H:{r['h']:.2f}  L:{r['l']:.2f}  C:{r['c']:.2f}  Vol:{r['v']}  ✅ saved")
    except Exception as e:
        db_session.rollback()
        print(f"  • {ticker:5}  ⚠️  Database error: {e}")

def fetch_all() -> None:
    """Fetch all configured tickers and store the results."""
    timestamp = datetime.now(UTC).isoformat(timespec="seconds") + "Z"
    print(f"\n[INGEST] 📈  {timestamp} – Fetching {len(TICKERS)} tickers…")

    for ticker in TICKERS:
        try:
            data = fetch_yfinance_current(ticker)
            store_market_data(ticker, data)
        except Exception as exc:
            print(f"  • {ticker:5}  ⚠️  Error: {exc}")

def fetch_yfinance_current(ticker: str) -> dict:
    """
    Fetch current market data for a given ticker using yfinance's .info endpoint.
    Returns a dictionary with structure similar to Polygon's /prev endpoint for easy integration.
    Adds a 'current' field for the most accurate current price.
    """
    info = yf.Ticker(ticker).info
    # Check for required fields and handle missing data gracefully
    try:
        open_price = float(info.get("open", 0))
        high_price = float(info.get("dayHigh", 0))
        low_price = float(info.get("dayLow", 0))
        close_price = float(info.get("regularMarketPrice", 0))
        volume = int(info.get("volume", 0))
        # Use 'currentPrice' if available, else fallback to 'regularMarketPrice'
        current_price = float(info.get("currentPrice") or info.get("regularMarketPrice", 0))
    except Exception:
        return {}

    # If any of the main fields are zero, treat as missing data
    if not all([open_price, high_price, low_price, close_price, volume, current_price]):
        return {}

    # Structure the result to match Polygon's /prev endpoint, with 'current' field
    return {
        "results": [
            {
                "o": open_price,   # Open
                "h": high_price,  # High
                "l": low_price,   # Low
                "c": close_price, # Close (previous close or last regular market)
                "v": volume,      # Volume
                "current": current_price, # Most accurate current price
            }
        ]
    }

# ---------------------------------------------------------------------------
# Scheduler setup – poll every 15 minutes (free plan ⇒ ≈20 requests/hour)
# ---------------------------------------------------------------------------

def start_scheduler() -> None:
    """Bootstraps APScheduler and starts the periodic job."""
    scheduler = BackgroundScheduler(daemon=True)
    # Job runs immediately once the scheduler starts, then every 15 minutes.
    scheduler.add_job(fetch_all, "interval", minutes=15, next_run_time=datetime.now(UTC))
    scheduler.start()
    print("[INGEST] 🚀  Scheduler started (interval: 15 min).")


           