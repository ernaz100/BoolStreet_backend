"""Database storage utilities for initializing and managing the database."""

from db.database import engine
from db.db_models import Base


def init_db():
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(engine)
    print("Database initialized successfully.")


def drop_all():
    """Drop all tables from the database."""
    Base.metadata.drop_all(engine)
    print("All tables dropped successfully.")

