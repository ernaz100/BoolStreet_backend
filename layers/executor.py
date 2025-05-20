import json
import os
import subprocess
import sys
import tempfile
import atexit
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
import resource  # Unix only – safe for dev and most prod servers
import pandas as pd
from dotenv import load_dotenv
from contextlib import contextmanager

from layers.broker import execute_orders
from db.models import  DailyBar, UserScript, ScriptPrediction
from db.database import get_session
from db.storage import get_script_code
load_dotenv()

# ---------------------------------------------------------------------------
# Constants – tune as needed
# ---------------------------------------------------------------------------
CPU_LIMIT_SECS: int = int(os.getenv("SANDBOX_CPU_LIMIT", "15"))  # max CPU seconds
MEM_LIMIT_BYTES: int = int(os.getenv("SANDBOX_MEM_LIMIT", str(200 * 1024 * 1024)))  # 200 MB

# Track active subprocesses for cleanup
_active_processes = set()

def _cleanup_processes():
    """Cleanup function to ensure all subprocesses are terminated."""
    for process in _active_processes:
        try:
            process.terminate()
            process.wait(timeout=1)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

# Register cleanup function
atexit.register(_cleanup_processes)

@contextmanager
def managed_session():
    """Context manager for database sessions with proper error handling."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def load_current_data() -> pd.DataFrame:
    """Load the most recent daily bar for each ticker in the database."""
    with managed_session() as session:
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

def _apply_limits() -> None:
    """Pre-exec hook that sets CPU & memory limits in the child process."""
    try:
        # CPU
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_SECS, CPU_LIMIT_SECS))
        # Memory (address space)
        resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT_BYTES, MEM_LIMIT_BYTES))
        # File descriptors
        resource.setrlimit(resource.RLIMIT_NOFILE, (100, 100))
    except Exception as e:
        sys.stderr.write(f"Warning: Could not apply resource limits: {e}\n")

def run_user_script(script_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Execute the given user script and return its JSON output."""
    code = get_script_code(script_id)
    if code is None:
        raise ValueError(f"No script found with id={script_id}")

    df = load_current_data()
    data_json = df.to_json(orient="records")

    # Create a temporary file for the script
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        script_path = f.name

    try:
        # Set resource limits
        _apply_limits()

        # Run the script in a subprocess
        start_time = datetime.now(timezone.utc)
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=_apply_limits
        )
        _active_processes.add(process)

        try:
            stdout, stderr = process.communicate(input=data_json, timeout=CPU_LIMIT_SECS)
            end_time = datetime.now(timezone.utc)

            if process.returncode != 0:
                raise RuntimeError(f"Script failed: {stderr}")

            # Parse the JSON output
            try:
                output = json.loads(stdout)
            except json.JSONDecodeError:
                raise ValueError(f"Script output is not valid JSON: {stdout}")

            # Track prediction if available
            if "prediction" in output:
                with managed_session() as session:
                    script = session.get(UserScript, script_id)
                    if script:
                        prediction = ScriptPrediction(
                            script_id=script_id,
                            prediction=output["prediction"].get("action", "unknown"),
                            confidence=output["prediction"].get("confidence"),
                            profit_loss=0.0,
                            balance_after=script.balance
                        )
                        session.add(prediction)

            # Execute orders if present
            receipts = []
            if "orders" in output:
                receipts = execute_orders(output["orders"])

            return {
                "script_id": script_id,
                "started_at": start_time.isoformat(),
                "ended_at": end_time.isoformat(),
                "duration_secs": (end_time - start_time).total_seconds(),
                "output": output,
            }, receipts

        finally:
            _active_processes.remove(process)
            try:
                process.terminate()
                process.wait(timeout=1)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    finally:
        # Clean up the temporary file
        try:
            os.unlink(script_path)
        except Exception as e:
            sys.stderr.write(f"Warning: Could not delete temporary file {script_path}: {e}\n")

def execute_all_scripts() -> List[Dict[str, Any]]:
    """Execute all registered active user scripts and return their results."""
    results = []
    with managed_session() as session:
        scripts = session.query(UserScript).filter(UserScript.active == True).all()
        for script in scripts:
            try:
                result, receipts = run_user_script(script.id)
                
                # Calculate new balance based on orders
                new_balance = script.balance
                for receipt in receipts:
                    if receipt['type'] == 'buy':
                        new_balance -= receipt['amount']
                    else:  # sell
                        new_balance += receipt['amount']
                
                # Update script balance
                script.balance = new_balance
                
                results.append({
                    "script_id": script.id,
                    "script_name": script.name,
                    "user_id": script.user_id,
                    "started_at": result["started_at"],
                    "ended_at": result["ended_at"],
                    "duration_secs": result["duration_secs"],
                    "output": result["output"],
                    "orders": receipts,
                    "success": True,
                    "balance": new_balance
                })
            except Exception as exc:
                results.append({
                    "script_id": script.id,
                    "script_name": script.name,
                    "user_id": script.user_id,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "duration_secs": 0,
                    "output": str(exc),
                    "success": False,
                    "balance": script.balance
                })
    return results