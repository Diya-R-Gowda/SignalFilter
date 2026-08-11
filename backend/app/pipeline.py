import json
import threading
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.item import Item
from app.services import embedding, llm, notify
from app.services.focus import get_current_focus
from app.services.sync_state import get_cursor


def _start_of_today_utc_naive() -> datetime:
    # items.created_at is naive UTC (no tz on the column, but written from
    # datetime.now(timezone.utc)). The attention budget resets on the user's local calendar
    # day, not UTC midnight, so local midnight has to be computed then converted into that
    # same naive-UTC shape to compare correctly against the column.
    local_midnight = datetime.combine(date.today(), time.min).astimezone()
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)


def _todays_notified_count(session: Session) -> int:
    stmt = select(func.count(Item.id)).where(
        Item.notified == True,  # noqa: E712
        Item.created_at >= _start_of_today_utc_naive(),
    )
    return session.execute(stmt).scalar() or 0


def process_item(
    session: Session,
    source: str,
    sender: str,
    content: str,
    source_timestamp: str,
    thread_id: str | None = None,
) -> Item:
    focus_text = get_current_focus(session) or ""

    passed_stage1, embedding_score = (
        embedding.passes_stage1(session, focus_text, content) if focus_text else (False, 0.0)
    )

    item = Item(
        source=source,
        sender=sender,
        content=content,
        thread_id=thread_id,
        source_timestamp=source_timestamp,
        focus_text=focus_text,
        embedding_score=embedding_score,
        passed_stage1=passed_stage1,
    )

    if passed_stage1:
        score, reason = llm.score_item(focus_text, content, sender, source)
        item.llm_score = score
        item.llm_reason = reason

        # Weak-signal escalation: compute this item's own content embedding and how many
        # similar recent items exist, independent of this item's own score. Dashboard-flag
        # only (see ItemCard.tsx) — never affects the notify/queue decision below.
        vector = embedding.get_embedding(content)
        item.embedding_vector = json.dumps(vector)
        # exclude_item_id is defensive only: item isn't committed yet (autoflush=False), so
        # it can't appear in its own candidate pool regardless of this filter.
        item.cluster_count = embedding.count_recent_similar(
            session, vector, exclude_item_id=item.id, sender=sender
        )

        threshold_key = (
            "gmail_interrupt_score_threshold" if source == "gmail" else "interrupt_score_threshold"
        )
        threshold_default = (
            settings.gmail_interrupt_score_threshold
            if source == "gmail"
            else settings.interrupt_score_threshold
        )
        raw_threshold = get_cursor(session, threshold_key)
        threshold = int(raw_threshold) if raw_threshold is not None else threshold_default
        if score >= threshold:
            # Scores of 9-10 always bypass the attention budget. This is a starting
            # assumption based on only one real 9-10 ever occurring in this project's
            # history — worth revisiting once more real cases exist, not a settled rule.
            if score >= 9 or _todays_notified_count(session) < settings.attention_budget_daily:
                item.notified = True
            else:
                item.queued_at = datetime.now(timezone.utc)

    # Persist the triage decision before touching the notification — win11toast's
    # toast() blocks until the toast is dismissed, so if this process gets killed
    # mid-toast, the record must already be safe rather than lost with it.
    session.add(item)
    session.commit()
    session.refresh(item)

    if item.notified:
        threading.Thread(
            target=notify.send_notification,
            kwargs={"title": f"{source} — {sender}", "body": content[:200]},
            daemon=True,
        ).start()

    return item
