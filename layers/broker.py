import os
import requests
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# -------------------------------------------------------------
# Alpaca Paper-Trading integration
# -------------------------------------------------------------
# This helper module centralises **all** interaction with Alpaca's
# broker REST API so that the rest of the codebase never has to think
# about HTTP details.  For now we only implement the endpoint we need
# – placing cash-equity orders – but it is trivial to extend this file
# with helpers such as `list_orders`, `cancel_order`, etc.
# -------------------------------------------------------------

# Credentials – *paper* keys are totally separate from live trading
# keys.  You can generate them at https://app.alpaca.markets/paper

ALPACA_KEY_ID: str | None = os.getenv("ALPACA_KEY_ID")
ALPACA_SECRET_KEY: str | None = os.getenv("ALPACA_SECRET_KEY")

if not ALPACA_KEY_ID or not ALPACA_SECRET_KEY:
    raise RuntimeError(
        "Environment variables ALPACA_KEY_ID and ALPACA_SECRET_KEY are required."
    )

# Base URL – override via .env to point at a mock server in tests if
# desired.  For live trading you would change to
#   https://api.alpaca.markets
# but *NEVER* do that from this repo without adequate checks!
BASE_URL: str = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# ---- Public helpers ------------------------------------------------------

def place_order(order: Dict[str, Any]) -> Dict[str, Any]:
    """Submit **one** equity order to Alpaca's paper-trading endpoint.

    Parameters
    ----------
    order : dict
        Required keys:
            symbol          – Ticker, e.g. "AAPL".
            side            – "buy" or "sell".
            qty             – Positive integer share count.
        Optional keys:
            type            – "market" (default) or "limit".
            limit_price     – Needed if *type == "limit"*.
            time_in_force   – "day", "gtc", etc.  Defaults to "day".

    Returns
    -------
    dict
        JSON response from Alpaca – order id, status, etc.

    Raises
    ------
    requests.HTTPError
        Forwarded if the broker rejects the order so the caller can log
        or surface the error appropriately.
    """

    url = f"{BASE_URL}/v2/orders"
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY_ID,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        "Content-Type": "application/json",
    }

    # Build payload with sane defaults and some light validation.
    payload: Dict[str, Any] = {
        "symbol": order["symbol"],
        "qty": str(order["qty"]),  # Alpaca expects stringified ints
        "side": order["side"].lower(),
        "type": order.get("type", "market").lower(),
        "time_in_force": order.get("time_in_force", "day").lower(),
    }

    # Limit / stop parameters ------------------------------------------------
    if payload["type"] in {"limit", "stop", "stop_limit"}:
        # limit_price is called just "limit_price" by Alpaca when type
        # is limit *or* stop_limit.
        if payload["type"] in {"limit", "stop_limit"}:
            if "limit_price" not in order:
                raise ValueError("limit_price is required for limit/stop_limit orders")
            payload["limit_price"] = str(order["limit_price"])

        # stop & stop_limit need stop_price
        if payload["type"] in {"stop", "stop_limit"}:
            if "stop_price" not in order:
                raise ValueError("stop_price is required for stop/stop_limit orders")
            payload["stop_price"] = str(order["stop_price"])

    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

def execute_orders(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Best-effort placement of **multiple** orders.

    Each order is executed sequentially so that side-effects are
    well-defined.  The return value is a list of receipts – one per
    order – where each receipt contains either the broker response or
    an ``error`` key if something went wrong.
    """
    receipts: List[Dict[str, Any]] = []
    print(f"[DEBUG] Executing {len(orders)} orders")
    for o in orders:
        try:
            print(f"[DEBUG] Placing order: {o}")
            broker_resp = place_order(o)
            print(f"[DEBUG] Order placed successfully: {broker_resp}")
            receipts.append({"ok": True, "symbol": o["symbol"], "response": broker_resp})
        except Exception as exc:  # noqa: BLE001  (best-effort – collect errors)
            print(f"[DEBUG] Order failed for {o.get('symbol')}: {exc}")
            receipts.append({"ok": False, "symbol": o.get("symbol"), "error": str(exc)})
    print(f"[DEBUG] Order execution complete. {len(receipts)} receipts generated.")
    return receipts