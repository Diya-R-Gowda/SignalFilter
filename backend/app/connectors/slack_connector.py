import time
from datetime import datetime, timezone

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

from app.config import settings
from app.db import SessionLocal
from app.pipeline import process_item
from app.services.sync_state import delete_cursor, set_cursor

SLACK_HEARTBEAT_INTERVAL_SECONDS = 30


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
            channel=event.get("channel"),
        )
        status = "NOTIFIED" if item.notified else ("scored" if item.passed_stage1 else "filtered")
        print(f"[slack] {event.get('user')}: {event.get('text', '')[:60]!r} -> {status}")
    finally:
        session.close()


def post_reply(channel: str, thread_ts: str | None, text: str) -> None:
    """Posts a GitHub-aware auto-reply on the user's behalf. Requires the bot token to carry
    the chat:write scope — not part of this project's original Slack app setup, so this will
    raise SlackApiError(missing_scope) until that scope is added and the bot reinstalled
    (see TODO.md). Raises rather than swallowing the error so the caller (the toast on_click
    handler) can decide whether to still mark reply_posted_at — it deliberately does not, so a
    failed post can be retried rather than silently recorded as sent."""
    client = WebClient(token=settings.slack_bot_token)
    client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)


def _heartbeat_loop() -> None:
    while True:
        session = SessionLocal()
        try:
            set_cursor(session, "slack_last_heartbeat_at", datetime.now(timezone.utc).isoformat())
        finally:
            session.close()
        time.sleep(SLACK_HEARTBEAT_INTERVAL_SECONDS)


def _record_error(exc: Exception) -> None:
    session = SessionLocal()
    try:
        set_cursor(session, "slack_last_error_at", datetime.now(timezone.utc).isoformat())
        set_cursor(session, "slack_last_error_message", str(exc)[:200])
    finally:
        session.close()


def _clear_error() -> None:
    session = SessionLocal()
    try:
        delete_cursor(session, "slack_last_error_at")
        delete_cursor(session, "slack_last_error_message")
    finally:
        session.close()


def start_slack_listener():
    import threading

    try:
        # Constructed lazily here (not at module scope) so a bad token surfaces only when
        # this connector's thread actually runs, not at import time in the main thread —
        # App.__init__ calls auth_test() eagerly, which crashed the whole process (and
        # Gmail's thread with it, since it hadn't started yet) before this fix.
        slack_app = App(token=settings.slack_bot_token)
        slack_app.event("message")(handle_message)

        handler = SocketModeHandler(slack_app, settings.slack_app_token)
        # handler.start() registers a SIGINT handler on Windows, which only works in the
        # main thread — breaks when this runs alongside another connector on a background
        # thread. connect() + block avoids touching signals entirely.
        handler.connect()

        # A successful connect clears any previously recorded crash — /health reflects
        # current state, not a stale failure that a human already fixed.
        _clear_error()

        # Started only after connect() succeeds, so a heartbeat implies an actually-established
        # connection, not just that this function was entered. Plain threading/time.sleep only —
        # no signal handling here, so this can't reintroduce the bug in the comment above.
        threading.Thread(target=_heartbeat_loop, daemon=True).start()
    except Exception as exc:
        # No retry — an invalid/revoked token needs a human to fix it, not a retry loop.
        # Record why and let this thread end cleanly; the process and Gmail are unaffected.
        print(f"[slack] failed to start: {exc}")
        _record_error(exc)
        return

    threading.Event().wait()
