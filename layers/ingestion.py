import os
import sys
import time
from datetime import datetime, UTC
from typing import List

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from db.storage import init_db, upsert_daily_bar
from layers.executor import execute_all_scripts

# -------------------------------------------------------------
# Ingestion layer for periodic market-data pulls from Polygon.io
# -------------------------------------------------------------
# This script fetches live snapshot data for a small universe of
# stocks every 15 minutes (free-tier limit: 5 requests/minute).
# The fresh data is printed to STDOUT for now; later we can swap
# the `print` statements for database persistence or message-bus
# publishing.
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


def fetch_all() -> None:
    """Fetch all configured tickers and print the results."""
    timestamp = datetime.now(UTC).isoformat(timespec="seconds") + "Z"
    print(f"\n[INGEST] 📈  {timestamp} – Fetching {len(TICKERS)} tickers…")

    for ticker in TICKERS:
        try:
            data = fetch_prev_agg(ticker)
            # Extract previous-day OHLC + volume metrics
            if data.get("results"):
                r = data["results"][0]
                # Persist to database
                upsert_daily_bar(ticker, r)

                print(
                    f"  • {ticker:5}  O:{r.get('o')}  H:{r.get('h')}  "
                    f"L:{r.get('l')}  C:{r.get('c')}  Vol:{r.get('v')}  ✅ saved"
                )
            else:
                print(f"  • {ticker:5}  ⚠️  No data returned – {data.get('status')}")
        except Exception as exc:
            print(f"  • {ticker:5}  ⚠️  Error: {exc}")

    # Execute all registered scripts
    results = execute_all_scripts()
    for result in results:
        status = "✅" if result["success"] else "❌"
        print(f"  • Script {result['script_id']} ({result['script_name']}) {status}: {result['output']}")


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


