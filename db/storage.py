from datetime import datetime, timezone
from typing import Dict

from db.database import engine, get_session
from db.models import Base, DailyBar, UserScript

# ---------------------------------------------------------------------------
# Public helper functions
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables if they do not yet exist."""
    Base.metadata.create_all(bind=engine)


def upsert_daily_bar(ticker: str, bar: Dict[str, float | int]) -> None:
    """Insert or update a daily bar.

    Parameters
    ----------
    ticker : str
        Symbol, e.g. "AAPL".
    bar : dict
        Raw aggregate result from Polygon: keys must include
        't' (epoch-ms), 'o', 'h', 'l', 'c', 'v'.
    """
    trading_day = datetime.fromtimestamp(bar["t"] / 1000, tz=timezone.utc).date()

    with get_session() as session:
        obj = session.get(DailyBar, {"ticker": ticker, "date": trading_day})

        if obj is None:
            obj = DailyBar(ticker=ticker, date=trading_day)

        obj.open = bar.get("o")
        obj.high = bar.get("h")
        obj.low = bar.get("l")
        obj.close = bar.get("c")
        obj.volume = bar.get("v")

        session.merge(obj)  # ensures insert-or-update semantics
        session.commit()


def save_script(name: str, code: str, user_id: str) -> int:
    """Persist a user script and return its assigned id.
    
    Parameters
    ----------
    name : str
        User-friendly name for the script
    code : str
        Raw source code of the script
    user_id : str
        Google OAuth user ID of the script owner
        
    Returns
    -------
    int
        The assigned script ID
    """
    with get_session() as session:
        script = UserScript(
            name=name,
            code=code,
            user_id=user_id,
            active=True,
            balance=1000.0
        )
        session.add(script)
        session.commit()
        session.refresh(script)
        return script.id


def get_script_code(script_id: int) -> str | None:
    """Return the raw source code for the given script id (or None)."""
    with get_session() as session:
        script = session.get(UserScript, script_id)
        return script.code if script else None


def drop_all() -> None:
    """Drop all tables. Use with caution."""
    Base.metadata.drop_all(bind=engine)