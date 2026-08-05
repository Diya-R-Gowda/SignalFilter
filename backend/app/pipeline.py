import threading

from sqlalchemy.orm import Session

from app.config import settings
from app.models.item import Item
from app.services import embedding, llm, notify
from app.services.focus import get_current_focus


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
        embedding.passes_stage1(focus_text, content) if focus_text else (False, 0.0)
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

        if score >= settings.interrupt_score_threshold:
            item.notified = True

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
