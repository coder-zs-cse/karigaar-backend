from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a sync Session (runs in threadpool automatically)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables on startup. Use Alembic migrations in production."""
    import app.models.worker    # noqa: F401
    import app.models.customer  # noqa: F401
    import app.models.job       # noqa: F401
    import app.models.call_log  # noqa: F401

    Base.metadata.create_all(bind=engine)
