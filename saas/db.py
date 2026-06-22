"""SQLAlchemy engine/session setup."""
from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def get_db_session_factory(database_url: str) -> sessionmaker:
    engine = create_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


_SessionLocal: sessionmaker | None = None


def init_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        database_url = os.environ.get(
            "DATABASE_URL", "postgresql+psycopg2://whatif:whatif@localhost:5432/whatif"
        )
        _SessionLocal = get_db_session_factory(database_url)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    session_factory = init_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
