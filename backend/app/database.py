"""SQLAlchemy engine and FastAPI database-session dependency."""

from collections.abc import Generator
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import get_database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create one process-level engine; sessions remain request-scoped."""

    return create_engine(get_database_url(), pool_pre_ping=True)


def get_db() -> Generator[Session, None, None]:
    """Yield one SQLAlchemy session for the lifetime of an API request."""

    try:
        session = Session(get_engine(), autoflush=False)
    except (RuntimeError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc

    try:
        yield session
    finally:
        session.close()
