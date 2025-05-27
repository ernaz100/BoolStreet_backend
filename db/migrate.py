from db.storage import init_db, drop_all
from backend.db.db_models import UserScript
from datetime import date
from db.database import get_session

def migrate():
    """Update database schema and migrate existing data."""
    print("Starting database migration...")
    
    # Drop existing tables
    drop_all()
    
    # Create new tables
    init_db()
    
    # Migrate existing data
    with get_session() as session:
        # Update existing trading models to set start_balance
        scripts = session.query(UserScript).all()
        for script in scripts:
            script.start_balance = script.balance
        session.commit()
    
    print("Migration completed successfully!")

if __name__ == '__main__':
    migrate() 