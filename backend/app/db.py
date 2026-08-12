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
        conn.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS queued_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS embedding_vector TEXT"))
        conn.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS cluster_count INTEGER"))
        conn.execute(text("ALTER TABLE focus_states ADD COLUMN IF NOT EXISTS source TEXT"))
        conn.commit()

        # Dedup before adding the unique constraint below, or the ALTER fails outright
        # against any pre-existing double-voted item. Keeps the most recent row per
        # item_id. Safe to re-run: once deduped, there's nothing left to delete.
        conn.execute(
            text(
                """
                DELETE FROM feedback
                WHERE id NOT IN (
                    SELECT DISTINCT ON (item_id) id
                    FROM feedback
                    ORDER BY item_id, created_at DESC, id DESC
                )
                """
            )
        )
        conn.commit()

        # Postgres has no ADD CONSTRAINT IF NOT EXISTS (verified: raises a syntax error),
        # and a DO block catching duplicate_object doesn't work either — a duplicate unique
        # constraint actually raises DuplicateTable, not duplicate_object. Checking
        # pg_constraint directly is the reliable idempotent path, tested on every startup.
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'feedback_item_id_unique'
                    ) THEN
                        ALTER TABLE feedback ADD CONSTRAINT feedback_item_id_unique UNIQUE (item_id);
                    END IF;
                END $$;
                """
            )
        )
        conn.commit()
