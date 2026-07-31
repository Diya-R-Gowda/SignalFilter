from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import settings
from app.db import SessionLocal
from app.pipeline import process_item

slack_app = App(token=settings.slack_bot_token)


@slack_app.event("message")
def handle_message(event, say):
    if event.get("subtype") is not None or event.get("bot_id"):
        return  # skip edits, joins, bot messages, etc.

    session = SessionLocal()
    try:
        item = process_item(
            session,
            source="slack",
            sender=event.get("user", "unknown"),
            content=event.get("text", ""),
            source_timestamp=event.get("ts", ""),
            thread_id=event.get("thread_ts") or event.get("channel"),
        )
        status = "NOTIFIED" if item.notified else ("scored" if item.passed_stage1 else "filtered")
        print(f"[slack] {event.get('user')}: {event.get('text', '')[:60]!r} -> {status}")
    finally:
        session.close()


def start_slack_listener():
    handler = SocketModeHandler(slack_app, settings.slack_app_token)
    handler.start()
