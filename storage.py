import os
from datetime import datetime, timezone, date as date_cls
from typing import Dict

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    BigInteger,
    Date,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------
# By default we keep everything local with SQLite so new contributors can run
# the project without installing any external services.  To switch to Postgres
# just export DATABASE_URL, e.g.:
#   export DATABASE_URL="postgresql+psycopg2://boolstreet:boolstreet@localhost:5432/boolstreet"
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.getenv("DATABASE_URL")

_engine = create_engine(DATABASE_URL, echo=False, future=True)
_Session = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


class DailyBar(Base):
    """OHLCV bar at daily resolution (Polygon `/prev` endpoint)."""

    __tablename__ = "daily_bars"

    ticker: str = Column(String(10), primary_key=True)
    date: date_cls = Column(Date, primary_key=True)  # trading day (UTC)

    open: float = Column(Float)
    high: float = Column(Float)
    low: float = Column(Float)
    close: float = Column(Float)
    volume: int = Column(BigInteger)


class UserScript(Base):
    """Stores uploaded user strategy scripts as raw source."""

    __tablename__ = "user_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    code = Column(String, nullable=False)
    created_at = Column(Date, default=date_cls.today)


# ---------------------------------------------------------------------------
# Public helper functions
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables if they do not yet exist."""
    Base.metadata.create_all(bind=_engine)


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

    with _Session() as session:
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


def save_script(name: str, code: str) -> int:
    """Persist a user script and return its assigned id."""
    with _Session() as session:
        script = UserScript(name=name, code=code)
        session.add(script)
        session.commit()
        session.refresh(script)
        return script.id


def get_script_code(script_id: int) -> str | None:
    """Return the raw source code for the given script id (or None)."""
    with _Session() as session:
        script = session.get(UserScript, script_id)
        return script.code if script else None 


def drop_all() -> None:
    """Drop all tables. Use with caution."""
    Base.metadata.drop_all(bind=_engine)