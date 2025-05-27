from db.database import engine, get_session
from db.db_models import Base, UserModel

# ---------------------------------------------------------------------------
# Public helper functions
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables if they do not yet exist."""
    Base.metadata.create_all(bind=engine)


def save_model(name: str, code: str, user_id: str, weights: str = None, tickers: str = str) -> int:
    """Persist a user trading model and return its assigned id.
    
    Parameters
    ----------
    name : str
        User-friendly name for the model
    code : str
        Raw source code of the model
    user_id : str
        Google OAuth user ID of the model owner
    weights : str, optional
        Content or path of the weights file (if provided)
    tickers : str
        JSON string of tickers (if provided)
    Returns
    -------
    int
        The assigned model ID
    """
    with get_session() as session:
        model = UserModel(
            name=name,
            code=code,
            user_id=user_id,
            active=True,
            balance=1000.0,
            weights=weights,  # Store weights if provided
            tickers=tickers  
        )
        session.add(model)
        session.commit()
        session.refresh(model)
        return model.id


def get_model_code(model_id: int) -> str | None:
    """Return the raw source code for the given trading model id (or None)."""
    with get_session() as session:
        model = session.get(UserModel, model_id)
        return model.code if model else None


def drop_all() -> None:
    """Drop all tables. Use with caution."""
    Base.metadata.drop_all(bind=engine)