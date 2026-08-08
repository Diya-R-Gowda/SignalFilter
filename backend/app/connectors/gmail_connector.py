import time
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.db import SessionLocal
from app.pipeline import process_item
from app.services.sync_state import delete_cursor, get_cursor, set_cursor

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CREDENTIALS_PATH = BACKEND_DIR / "credentials.json"
TOKEN_PATH = BACKEND_DIR / "token.json"

POLL_INTERVAL_SECONDS = 40
HISTORY_CURSOR_KEY = "gmail_history_id"


def get_gmail_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Missing {CREDENTIALS_PATH}. Download OAuth Desktop app credentials from "
                    "Google Cloud Console and save them there as credentials.json — see README setup steps."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _extract_header(headers: list[dict], name: str) -> str:
    for header in headers:
        if header["name"].lower() == name.lower():
            return header["value"]
    return ""


def _fetch_message(service, message_id: str) -> dict:
    message = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="metadata", metadataHeaders=["From", "Subject"])
        .execute()
    )

    headers = message.get("payload", {}).get("headers", [])
    sender = _extract_header(headers, "From")
    subject = _extract_header(headers, "Subject")
    snippet = message.get("snippet", "")

    return {
        "sender": sender or "unknown",
        "content": f"{subject}\n\n{snippet}".strip(),
        "thread_id": message.get("threadId"),
        "source_timestamp": message.get("internalDate", ""),
    }


def _poll_once(service, session) -> None:
    set_cursor(session, "gmail_last_poll_at", datetime.now(timezone.utc).isoformat())

    cursor = get_cursor(session, HISTORY_CURSOR_KEY)

    if cursor is None:
        # First run: don't replay the whole inbox, just record where "new" starts from.
        profile = service.users().getProfile(userId="me").execute()
        set_cursor(session, HISTORY_CURSOR_KEY, str(profile["historyId"]))
        print("[gmail] first run — recording history cursor, will process new mail from here on")
        return

    try:
        response = (
            service.users()
            .history()
            .list(userId="me", startHistoryId=cursor, historyTypes=["messageAdded"])
            .execute()
        )
    except Exception as exc:
        # Cursor too old (Gmail only keeps ~7 days of history) or otherwise invalid — reset and skip this cycle.
        print(f"[gmail] history cursor invalid ({exc}), resetting")
        profile = service.users().getProfile(userId="me").execute()
        set_cursor(session, HISTORY_CURSOR_KEY, str(profile["historyId"]))
        return

    message_ids = [
        added["message"]["id"]
        for record in response.get("history", [])
        for added in record.get("messagesAdded", [])
    ]

    for message_id in message_ids:
        try:
            details = _fetch_message(service, message_id)
            if not details["content"].strip():
                # Gmail's history event can fire slightly before subject/snippet are indexed —
                # nothing to score yet; the message gets picked up correctly on a later poll.
                print(f"[gmail] {details['sender']}: empty content, skipping (will retry on next poll)")
                continue

            item = process_item(
                session,
                source="gmail",
                sender=details["sender"],
                content=details["content"],
                source_timestamp=details["source_timestamp"],
                thread_id=details["thread_id"],
            )
            status = "NOTIFIED" if item.notified else ("scored" if item.passed_stage1 else "filtered")
            print(f"[gmail] {details['sender']}: {details['content'][:60]!r} -> {status}")
        except Exception as exc:
            # One bad message (encoding issue, API hiccup, etc.) must never block the rest of the
            # batch or prevent the cursor from advancing — that would reprocess everything forever.
            print(f"[gmail] failed to process message {message_id}: {exc}")

    new_history_id = response.get("historyId")
    if new_history_id:
        set_cursor(session, HISTORY_CURSOR_KEY, str(new_history_id))


def _record_error(exc: Exception) -> None:
    session = SessionLocal()
    try:
        set_cursor(session, "gmail_last_error_at", datetime.now(timezone.utc).isoformat())
        set_cursor(session, "gmail_last_error_message", str(exc)[:200])
    finally:
        session.close()


def _clear_error() -> None:
    session = SessionLocal()
    try:
        delete_cursor(session, "gmail_last_error_at")
        delete_cursor(session, "gmail_last_error_message")
    finally:
        session.close()


def start_gmail_listener() -> None:
    try:
        service = get_gmail_service()
    except Exception as exc:
        # No retry — missing/invalid credentials need a human to fix them, not a retry loop.
        # Record why and return; the process and Slack's thread are unaffected.
        print(f"[gmail] failed to start: {exc}")
        _record_error(exc)
        return

    # A successful connect clears any previously recorded crash — /health reflects
    # current state, not a stale failure that a human already fixed.
    _clear_error()

    print(f"[gmail] connected, polling every {POLL_INTERVAL_SECONDS}s")

    while True:
        session = SessionLocal()
        try:
            _poll_once(service, session)
        except Exception as exc:
            print(f"[gmail] poll error: {exc}")
        finally:
            session.close()
        time.sleep(POLL_INTERVAL_SECONDS)
