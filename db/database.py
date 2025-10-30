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

# Get the project root directory (parent of backend)
# __file__ is backend/db/database.py, so we need to go up 3 levels
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
instance_dir = os.path.join(project_root, "instance")

# Default to SQLite if DATABASE_URL is not set, or convert relative SQLite paths to absolute
if not DATABASE_URL:
    # Create instance directory if it doesn't exist
    os.makedirs(instance_dir, exist_ok=True)
    
    # Set default SQLite database path (use absolute path for SQLite)
    db_path = os.path.join(instance_dir, "boolstreet.db")
    DATABASE_URL = f"sqlite:///{db_path}"
elif DATABASE_URL.startswith("sqlite:///"):
    # Convert relative SQLite paths to absolute paths
    # sqlite:///instance/boolstreet.db -> sqlite:////absolute/path/instance/boolstreet.db
    db_path = DATABASE_URL.replace("sqlite:///", "")
    
    # If it's a relative path (doesn't start with /), make it absolute
    if not os.path.isabs(db_path):
        db_path = os.path.join(project_root, db_path)
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    DATABASE_URL = f"sqlite:///{db_path}"

# Create engine
engine = create_engine(DATABASE_URL, echo=False, future=True)

# Create session factory
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_session():
    """Get a new database session."""
    return Session() 