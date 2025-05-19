import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List
import resource  # Unix only – safe for dev and most prod servers

import pandas as pd

from storage import _Session, DailyBar, get_script_code, UserScript
from dotenv import load_dotenv
from broker import execute_orders  # NEW – Polygon paper-trading

load_dotenv()

# ---------------------------------------------------------------------------
# Constants – tune as needed
# ---------------------------------------------------------------------------
CPU_LIMIT_SECS: int = int(os.getenv("SANDBOX_CPU_LIMIT", "5"))  # max CPU seconds
MEM_LIMIT_BYTES: int = int(os.getenv("SANDBOX_MEM_LIMIT", str(200 * 1024 * 1024)))  # 200 MB

# ---------------------------------------------------------------------------
# Helper: query current stock data and return as DataFrame
# ---------------------------------------------------------------------------

def load_current_data() -> pd.DataFrame:
    """Load the most recent daily bar for each ticker in the database."""
    with _Session() as session:
        subquery = (
            session.query(
                DailyBar.ticker, DailyBar.date.label("max_date")
            )
            .group_by(DailyBar.ticker)
            .subquery()
        )

        rows = (
            session.query(DailyBar)
            .join(
                subquery,
                (DailyBar.ticker == subquery.c.ticker)
                & (DailyBar.date == subquery.c.max_date),
            )
            .all()
        )

        records: list[Dict[str, Any]] = [
            {
                "ticker": r.ticker,
                "date": r.date.isoformat(),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]

    return pd.DataFrame.from_records(records)


# ---------------------------------------------------------------------------
# Sandbox logic
# ---------------------------------------------------------------------------

def _apply_limits() -> None:
    """Pre-exec hook that sets CPU & memory limits in the child process."""
    try:
        # CPU
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_SECS, CPU_LIMIT_SECS))
        # Memory (address space)
        resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT_BYTES, MEM_LIMIT_BYTES))
    except Exception as e:
        import sys
        sys.stderr.write(f"Warning: Could not apply resource limits: {e}\n")



def run_user_script(script_id: int) -> Dict[str, Any]:
    """Execute the given user script and return its JSON output.

    The script must expose a top-level `run(data: pd.DataFrame) -> dict`.
    We execute it in a subprocess with strict resource limits.

    Expected contract for the returned JSON:

    {
        "orders": [
            {
                "symbol": "AAPL",
                "side": "buy" | "sell",
                "qty": 10,
                "type": "market" | "limit" (default="market"),
                "limit_price": 185.50,      # required if type=="limit"
                "time_in_force": "day"      # default
            },
            ...
        ],
        "meta": {  # optional – any other user defined information
            "comment": "RSI cross-over signal",
            "signal_strength": 0.83
        }
    }

    The `orders` list is optional; if present the orders will be sent
    to Alpaca's *paper* trading endpoint right after the script
    completes (see `broker.execute_orders`).
    """

    code = get_script_code(script_id)
    if code is None:
        raise ValueError(f"No script found with id={script_id}")

    df = load_current_data()
    data_json = df.to_json(orient="records")
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "user_script.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        cmd = [sys.executable, script_path]
        start_time = datetime.now(timezone.utc)
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=_apply_limits,
        )

        try:
            stdout, stderr = proc.communicate(data_json, timeout=CPU_LIMIT_SECS + 2)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("Execution timed out")

        if proc.returncode != 0:
            raise RuntimeError(
                f"User script returned non-zero exit code {proc.returncode}:\n{stderr}"
            )

        try:
            result = json.loads(stdout.strip()) if stdout.strip() else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"User script did not return valid JSON: {exc}\n{stdout}")

        end_time = datetime.now(timezone.utc)

        # -------------------------------------------------------
        # Optional trade execution – if the user script returns
        # a JSON payload with an "orders" key we forward each
        # specified order to Alpaca's paper-trading endpoint.
        # A receipt (either success or error) is attached to the
        # final result so that the caller can inspect what
        # happened.
        # -------------------------------------------------------
        receipts = []
        if isinstance(result, dict):
            orders = result.get("orders", [])
            if orders:
                receipts = execute_orders(orders)

        # For now we just return the result; later we could persist logs.
        return {
            "script_id": script_id,
            "started_at": start_time.isoformat(),
            "ended_at": end_time.isoformat(),
            "duration_secs": (end_time - start_time).total_seconds(),
            "output": result,
        }, receipts

def execute_all_scripts() -> List[Dict[str, Any]]:
    """
    Execute all registered user scripts and return their results.
    
    Returns:
        List[Dict[str, Any]]: List of execution results, each containing:
            - script_id: ID of the executed script
            - script_name: Name of the script
            - started_at: ISO timestamp of execution start
            - ended_at: ISO timestamp of execution end
            - duration_secs: Execution duration in seconds
            - output: Script output or error message
            - success: Whether execution succeeded
    """
    results = []
    with _Session() as session:
        scripts = session.query(UserScript).all()
        for script in scripts:
            try:
                result, receipts = run_user_script(script.id)
                results.append({
                    "script_id": script.id,
                    "script_name": script.name,
                    "started_at": result["started_at"],
                    "ended_at": result["ended_at"],
                    "duration_secs": result["duration_secs"],
                    "output": result["output"],
                    "orders": receipts,
                    "success": True
                })
            except Exception as exc:
                results.append({
                    "script_id": script.id,
                    "script_name": script.name,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "duration_secs": 0,
                    "output": str(exc),
                    "success": False
                })
    return results