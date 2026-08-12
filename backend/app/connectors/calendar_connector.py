import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.db import SessionLocal
from app.services.focus import get_current_focus_state, get_last_manual_focus_text, set_focus
from app.services.sync_state import delete_cursor, get_cursor, set_cursor

# Independent from Gmail's scope/token — see CONTRIBUTING.md: sharing a token file would
# couple the two connectors' credential lifecycles for no benefit. Same credentials.json
# (OAuth client) is reused; only the token cache is separate.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CREDENTIALS_PATH = BACKEND_DIR / "credentials.json"
TOKEN_PATH = BACKEND_DIR / "calendar_token.json"

POLL_INTERVAL_SECONDS = 180
LOOKAHEAD_MINUTES = 15
BUSY_UNTIL_KEY = "calendar_busy_until"
CURRENT_EVENT_ID_KEY = "calendar_current_event_id"


def get_calendar_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Missing {CREDENTIALS_PATH}. Same OAuth Desktop app credentials Gmail uses — "
                    "see README setup steps."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def _is_qualifying(event: dict) -> bool:
    start = event.get("start", {})
    if "dateTime" not in start:
        return False  # all-day / date-only event

    attendees = event.get("attendees") or []
    if len(attendees) <= 1:
        return False  # no one else invited — a personal reminder, not a meeting

    self_attendee = next((a for a in attendees if a.get("self")), None)
    if self_attendee is None or self_attendee.get("responseStatus") != "accepted":
        return False  # declined/tentative/no-response invites don't count

    if event.get("transparency") == "transparent":
        return False  # explicitly marked as not blocking time

    return True


def _fetch_current_event(service) -> dict | None:
    now = datetime.now(timezone.utc)
    # timeMin bounds an event's END time (exclusive lower bound) and timeMax bounds its START
    # time (exclusive upper bound) per the Calendar API's actual semantics — so an event that
    # started before "now" but hasn't ended yet is still included; this is not the same as
    # the more intuitive-but-wrong "window between timeMin and timeMax" reading.
    response = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(minutes=LOOKAHEAD_MINUTES)).isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    current = []
    for event in response.get("items", []):
        if not _is_qualifying(event):
            continue
        start_dt = datetime.fromisoformat(event["start"]["dateTime"])
        end_dt = datetime.fromisoformat(event["end"]["dateTime"])
        if start_dt <= now <= end_dt:
            current.append(event)

    if not current:
        return None

    # startTime ordering already comes from the API; tiebreak on event id for full
    # determinism on a real double-booking — arbitrary but deterministic, not yet informed
    # by any real overlap case (see CONTRIBUTING.md's audit note on this).
    current.sort(key=lambda e: (e["start"]["dateTime"], e["id"]))
    return current[0]


def _poll_once(service, session) -> None:
    set_cursor(session, "calendar_last_poll_at", datetime.now(timezone.utc).isoformat())

    current_event = _fetch_current_event(service)
    previous_event_id = get_cursor(session, CURRENT_EVENT_ID_KEY)
    current_event_id = current_event["id"] if current_event else None

    if current_event_id == previous_event_id:
        return  # no transition — same event still current, or still no event

    if current_event is not None:
        # Start transition (including a direct back-to-back switch between two meetings —
        # treated as just a new start, no explicit revert for the meeting that just ended).
        title = current_event.get("summary") or "(no title)"
        end_dt = current_event["end"]["dateTime"]
        set_focus(session, title, source="calendar")
        set_cursor(session, BUSY_UNTIL_KEY, end_dt)
        set_cursor(session, CURRENT_EVENT_ID_KEY, current_event_id)
        print(f"[calendar] meeting started: {title!r}, busy until {end_dt}")
    else:
        # End transition — a qualifying event was current, now none is.
        delete_cursor(session, BUSY_UNTIL_KEY)
        delete_cursor(session, CURRENT_EVENT_ID_KEY)

        latest = get_current_focus_state(session)
        if latest is not None and latest.source == "calendar":
            # Nothing manual happened since the meeting started — safe to revert.
            manual_text = get_last_manual_focus_text(session)
            if manual_text is not None:
                set_focus(session, manual_text, source="manual")
                print(f"[calendar] meeting ended, reverted focus to: {manual_text!r}")
            else:
                print("[calendar] meeting ended, no prior manual focus to revert to")
        else:
            print("[calendar] meeting ended, manual override already in effect, no revert")


def _record_error(exc: Exception) -> None:
    session = SessionLocal()
    try:
        set_cursor(session, "calendar_last_error_at", datetime.now(timezone.utc).isoformat())
        set_cursor(session, "calendar_last_error_message", str(exc)[:200])
    finally:
        session.close()


def _clear_error() -> None:
    session = SessionLocal()
    try:
        delete_cursor(session, "calendar_last_error_at")
        delete_cursor(session, "calendar_last_error_message")
    finally:
        session.close()


def start_calendar_listener() -> None:
    try:
        service = get_calendar_service()
    except Exception as exc:
        # No retry — missing/invalid credentials need a human to fix them, not a retry loop.
        print(f"[calendar] failed to start: {exc}")
        _record_error(exc)
        return

    # A successful connect clears any previously recorded crash — /health reflects
    # current state, not a stale failure that a human already fixed.
    _clear_error()

    print(f"[calendar] connected, polling every {POLL_INTERVAL_SECONDS}s")

    while True:
        session = SessionLocal()
        try:
            _poll_once(service, session)
        except Exception as exc:
            print(f"[calendar] poll error: {exc}")
        finally:
            session.close()
        time.sleep(POLL_INTERVAL_SECONDS)
