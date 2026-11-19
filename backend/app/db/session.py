"""DB engine, session factory and declarative Base."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


# Options of the app's engine. `hide_parameters`: a database error or an SQL log line never carries the bound values, which are masked
# transcripts, plans, feedback and CV text (M4 S3c, D65). It does not hide what PostgreSQL itself writes into the DETAIL of an error
# (a check or not-null violation names the failing row), so values are validated before they are stored.
ENGINE_OPTIONS = {"pool_pre_ping": True, "hide_parameters": True}
engine = create_engine(settings.DATABASE_URL, **ENGINE_OPTIONS)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
