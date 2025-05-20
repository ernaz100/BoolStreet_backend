import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
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

# Create engine
engine = create_engine(DATABASE_URL, echo=False, future=True)

# Create session factory
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_session():
    """Get a new database session."""
    return Session() 