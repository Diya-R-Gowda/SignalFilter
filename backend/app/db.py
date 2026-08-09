from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db():
    from app.models import item, focus_state, feedback, sync_state  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # create_all() only creates missing tables, not missing columns on existing ones —
    # items already existed before digested_at was added to the model, so it needs its
    # own migration step. IF NOT EXISTS makes this safe to run on every startup.
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS digested_at TIMESTAMPTZ"))
        conn.commit()
