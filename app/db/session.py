from __future__ import annotations

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from ..config import Config
from ..settings import DATABASE_PATH, DATA_DIR


DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DATABASE_PATH.as_posix()}",
    connect_args={
        "timeout": Config.SQLITE_TIMEOUT_SECONDS,
        "check_same_thread": False,
    },
    future=True,
)
SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
SessionLocal = scoped_session(SessionFactory)


@event.listens_for(engine, "connect")
def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute(f"PRAGMA busy_timeout = {int(Config.SQLITE_TIMEOUT_SECONDS * 1000)}")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA temp_store = MEMORY")
    cursor.execute(f"PRAGMA cache_size = -{max(1024, Config.SQLITE_CACHE_KB)}")
    cursor.close()


def get_session() -> Session:
    return SessionLocal()


def create_session() -> Session:
    return SessionFactory()


def close_session(_exception: BaseException | None = None) -> None:
    SessionLocal.remove()


def commit() -> None:
    get_session().commit()


def rollback() -> None:
    get_session().rollback()


def health_check() -> None:
    get_session().execute(text("SELECT 1")).fetchone()
