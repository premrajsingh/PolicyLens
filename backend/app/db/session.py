from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import Settings, get_settings

_engine = None


def _sqlite_url(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        path = database_url.replace("sqlite:///", "", 1)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return database_url


def get_engine(settings: Settings | None = None):
    global _engine
    if _engine is None:
        settings = settings or get_settings()
        url = _sqlite_url(settings.database_url)
        connect_args = (
            {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
        )
        _engine = create_engine(url, echo=False, connect_args=connect_args)

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return _engine


def init_db(settings: Settings | None = None) -> None:
    engine = get_engine(settings)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
                    chunk_id UNINDEXED,
                    document_id UNINDEXED,
                    section UNINDEXED,
                    page_number UNINDEXED,
                    text,
                    tokenize = 'porter'
                )
                """
            )
        )
        session.commit()


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


def reset_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
