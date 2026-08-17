from datetime import datetime, timezone

from win11toast import toast

from app.db import SessionLocal
from app.models.item import Item
from app.services.app_identity import APP_USER_MODEL_ID
from app.services.feedback import upsert_feedback


def send_notification(
    title: str,
    body: str,
    item_id: str | None = None,
    drafted_reply: str | None = None,
    channel: str | None = None,
    thread_ts: str | None = None,
) -> None:
    if drafted_reply and item_id and channel:
        _send_actionable_reply_toast(title, body, item_id, drafted_reply, channel, thread_ts)
    else:
        toast(title, body, duration="short", app_id=APP_USER_MODEL_ID)


def _send_actionable_reply_toast(
    title: str, body: str, item_id: str, drafted_reply: str, channel: str, thread_ts: str | None
) -> None:
    toast_body = f"{body}\n\nSuggested reply: {drafted_reply}"

    def on_click(args: dict) -> None:
        action = args.get("arguments")
        if action == "reply_yes":
            _handle_reply_click(item_id, channel, thread_ts, drafted_reply, accepted=True)
        elif action == "reply_no":
            _handle_reply_click(item_id, channel, thread_ts, drafted_reply, accepted=False)

    # Tier A scope: this only catches a click made while the toast is still on-screen
    # (win11toast tears down its click listener the instant the toast times out or is
    # dismissed — see CONTRIBUTING.md). A click from Action Center after that window is
    # structurally impossible to catch with this library; that gap is Tier B, deferred.
    toast(
        title,
        toast_body,
        buttons=[
            {"activationType": "foreground", "arguments": "reply_yes", "content": "Yes, post it"},
            {"activationType": "foreground", "arguments": "reply_no", "content": "No"},
        ],
        app_id=APP_USER_MODEL_ID,
        duration="long",
        on_click=on_click,
    )


def _handle_reply_click(
    item_id: str, channel: str, thread_ts: str | None, drafted_reply: str, accepted: bool
) -> None:
    session = SessionLocal()
    try:
        item = session.get(Item, item_id)
        if item is None or item.reply_posted_at is not None:
            return  # already posted (or item gone) — a second click is a no-op, not a re-post

        # Yes/No is functionally a thumbs up/down at the moment of interruption — feeds the
        # same Feedback table the dashboard's vote buttons do, not a parallel mechanism.
        upsert_feedback(session, item_id, thumbs_up=accepted)

        if accepted:
            try:
                from app.connectors.slack_connector import post_reply

                post_reply(channel, thread_ts, drafted_reply)
                item.reply_posted_at = datetime.now(timezone.utc)
                session.commit()
            except Exception as exc:
                # Posting failure (e.g. missing chat:write scope) must not look like success —
                # reply_posted_at stays NULL so this is visibly still unresolved, not silently
                # dropped.
                print(f"[notify] failed to post reply for item {item_id}: {exc}")
    finally:
        session.close()
