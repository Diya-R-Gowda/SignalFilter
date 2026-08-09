import threading
import time
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models.item import Item
from app.services import notify
from app.services.sync_state import get_cursor, set_cursor

CHECK_INTERVAL_SECONDS = 300
BACKFILL_MARKER_KEY = "digest_backfill_done"
LAST_RUN_KEY = "digest_last_run_date"


def _run_backfill_once() -> None:
    session = SessionLocal()
    try:
        if get_cursor(session, BACKFILL_MARKER_KEY) is not None:
            return
        # Pre-existing filtered items predate this feature — stamp them as already-digested
        # so the first real check doesn't dump the entire backlog into one toast. Safe to
        # re-run before the marker is set: it just re-stamps rows that are still NULL.
        session.query(Item).filter(Item.digested_at.is_(None)).update(
            {Item.digested_at: datetime.now(timezone.utc)}, synchronize_session=False
        )
        set_cursor(session, BACKFILL_MARKER_KEY, "true")
        print("[digest] one-time backfill: stamped pre-existing items as already-digested")
    finally:
        session.close()


def _run_digest_check() -> None:
    session = SessionLocal()
    try:
        today = date.today().isoformat()
        if get_cursor(session, LAST_RUN_KEY) == today:
            return  # already ran today

        if datetime.now().strftime("%H:%M") < settings.digest_time:
            return  # not time yet

        stmt = select(Item).where(
            Item.passed_stage1 == True,  # noqa: E712
            Item.llm_score.is_not(None),
            Item.llm_score > 1,
            Item.notified == False,  # noqa: E712
            Item.digested_at.is_(None),
        )
        items = list(session.execute(stmt).scalars().all())

        # Persist before touching the notification, same reasoning as pipeline.py: toast()
        # blocks until dismissed, so a hung/slow toast call must never be able to stall this
        # scheduler loop or leave today's run unrecorded.
        if items:
            now = datetime.now(timezone.utc)
            for item in items:
                item.digested_at = now

        set_cursor(session, LAST_RUN_KEY, today)  # commits the session, including any digested_at updates above

        if items:
            threading.Thread(
                target=notify.send_notification,
                kwargs={
                    "title": "Signal Filter — Digest",
                    "body": f"{len(items)} things worth a look from today",
                },
                daemon=True,
            ).start()
    finally:
        session.close()


def start_digest_scheduler() -> None:
    print(f"[digest] scheduler starting, checking every {CHECK_INTERVAL_SECONDS}s, daily at {settings.digest_time}")
    _run_backfill_once()
    while True:
        try:
            _run_digest_check()
        except Exception as exc:
            print(f"[digest] check failed: {exc}")
        time.sleep(CHECK_INTERVAL_SECONDS)
