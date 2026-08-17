from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session, init_db
from app.models.feedback import Feedback
from app.models.item import Item
from app.schemas import (
    ConnectorHealthOut,
    FeedbackIn,
    FeedbackInsightOut,
    FeedbackOut,
    FocusIn,
    FocusOut,
    ItemOut,
    SettingsIn,
    SettingsOut,
)
from app.services.feedback import upsert_feedback
from app.services.focus import get_current_focus_state, set_focus
from app.services.sync_state import get_cursor, set_cursor

# (connector name, SyncState key, stale-after seconds) — thresholds are 3x each
# connector's own heartbeat interval (Gmail POLL_INTERVAL_SECONDS=40, Slack
# SLACK_HEARTBEAT_INTERVAL_SECONDS=30).
CONNECTOR_HEALTH_CONFIG = [
    ("gmail", "gmail_last_poll_at", 120),
    ("slack", "slack_last_heartbeat_at", 90),
    ("calendar", "calendar_last_poll_at", 540),  # 3x calendar_connector's 180s poll interval
]

# (SyncState key, caster) — matches the three tunable fields on Settings exactly;
# .env/Settings is only the bootstrap default, consulted when no SyncState row exists.
TUNING_SETTINGS_CONFIG = [
    ("embedding_threshold", float),
    ("interrupt_score_threshold", int),
    ("gmail_interrupt_score_threshold", int),
]

app = FastAPI(title="Signal Filter API")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/items", response_model=list[ItemOut])
def list_items(
    source: str | None = None,
    notified: bool | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
) -> list[Item]:
    stmt = select(Item).order_by(Item.created_at.desc()).limit(limit)
    if source is not None:
        stmt = stmt.where(Item.source == source)
    if notified is not None:
        stmt = stmt.where(Item.notified == notified)
    items = list(session.execute(stmt).scalars().all())

    # Item has no feedback relationship — attach each item's existing vote (if any) as a
    # plain instance attribute so ItemOut.feedback picks it up via from_attributes.
    feedback_stmt = select(Feedback.item_id, Feedback.thumbs_up).where(
        Feedback.item_id.in_([item.id for item in items])
    )
    feedback_by_item = dict(session.execute(feedback_stmt).all())
    for item in items:
        item.feedback = feedback_by_item.get(item.id)

    return items


def _is_calendar_busy(session: Session) -> bool:
    raw = get_cursor(session, "calendar_busy_until")
    if raw is None:
        return False
    return datetime.now(timezone.utc) < datetime.fromisoformat(raw)


@app.get("/focus", response_model=FocusOut | None)
def read_focus(session: Session = Depends(get_session)):
    state = get_current_focus_state(session)
    if state is None:
        return None
    # calendar_busy isn't a FocusState column — attached as a plain instance attribute so
    # FocusOut picks it up via from_attributes, same pattern list_items() uses for feedback.
    state.calendar_busy = _is_calendar_busy(session)
    return state


@app.post("/focus", response_model=FocusOut)
def update_focus(body: FocusIn, session: Session = Depends(get_session)):
    state = set_focus(session, body.focus_text)
    # Same attachment read_focus does — a manual POST can happen mid-meeting, so this must
    # reflect current calendar state too, not just whatever was true before the write.
    state.calendar_busy = _is_calendar_busy(session)
    return state


@app.post("/items/{item_id}/feedback", response_model=FeedbackOut)
def create_feedback(item_id: str, body: FeedbackIn, session: Session = Depends(get_session)):
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    return upsert_feedback(session, item_id, body.thumbs_up)


def _read_tuning_settings(session: Session) -> SettingsOut:
    values: dict = {}
    for key, caster in TUNING_SETTINGS_CONFIG:
        raw = get_cursor(session, key)
        if raw is None:
            values[key] = getattr(settings, key)
            values[f"{key}_source"] = "default"
        else:
            values[key] = caster(raw)
            values[f"{key}_source"] = "override"
    return SettingsOut(**values)


@app.get("/settings", response_model=SettingsOut)
def read_settings(session: Session = Depends(get_session)) -> SettingsOut:
    return _read_tuning_settings(session)


@app.post("/settings", response_model=SettingsOut)
def update_settings(body: SettingsIn, session: Session = Depends(get_session)) -> SettingsOut:
    # SettingsIn's Field(ge=..., le=...) constraints already reject the whole request with a
    # 422 before this runs if any provided key is out of range — nothing gets written unless
    # every key in the request is valid.
    for key, value in body.model_dump(exclude_none=True).items():
        set_cursor(session, key, str(value))
    return _read_tuning_settings(session)


@app.get("/feedback/insights", response_model=list[FeedbackInsightOut])
def read_feedback_insights(session: Session = Depends(get_session)) -> list[FeedbackInsightOut]:
    # Computed live from Feedback + Item on every call — no SyncState key, same philosophy
    # as /health computing current status fresh rather than caching it. Only six specific
    # state/vote combinations are informative; everything else contributes nothing, per the
    # audit: a thumbs-down on an already-filtered item just confirms current behavior.
    stmt = select(
        Feedback.thumbs_up, Item.source, Item.passed_stage1, Item.llm_score, Item.notified
    ).join(Item, Feedback.item_id == Item.id)

    counts = {
        "embedding_threshold": {"raise": 0, "lower": 0},
        "interrupt_score_threshold": {"raise": 0, "lower": 0},
        "gmail_interrupt_score_threshold": {"raise": 0, "lower": 0},
    }

    for thumbs_up, source, passed_stage1, llm_score, notified in session.execute(stmt).all():
        score_threshold_key = (
            "gmail_interrupt_score_threshold" if source == "gmail" else "interrupt_score_threshold"
        )
        if notified:
            if not thumbs_up:
                counts[score_threshold_key]["raise"] += 1
        elif passed_stage1 and llm_score is not None:
            if thumbs_up:
                counts[score_threshold_key]["lower"] += 1
        else:
            if thumbs_up:
                counts["embedding_threshold"]["lower"] += 1

    results = []
    for key in ("embedding_threshold", "interrupt_score_threshold", "gmail_interrupt_score_threshold"):
        raise_votes = counts[key]["raise"]
        lower_votes = counts[key]["lower"]
        if raise_votes == 0 and lower_votes == 0:
            direction = None
            informative_votes = 0
        elif raise_votes >= lower_votes:
            # Ties go to "raise" — an arbitrary but deterministic tiebreak, since both
            # directions being equally supported gives no real basis to prefer either.
            direction = "raise"
            informative_votes = raise_votes
        else:
            direction = "lower"
            informative_votes = lower_votes
        results.append(
            FeedbackInsightOut(
                threshold=key,
                direction=direction,
                informative_votes=informative_votes,
                gate_met=informative_votes >= settings.feedback_min_votes,
            )
        )
    return results


@app.get("/health", response_model=list[ConnectorHealthOut])
def read_health(session: Session = Depends(get_session)) -> list[ConnectorHealthOut]:
    now = datetime.now(timezone.utc)
    results = []
    for name, key, stale_after_seconds in CONNECTOR_HEALTH_CONFIG:
        raw = get_cursor(session, key)
        if raw is None:
            # Never written a heartbeat yet — unknown, not "healthy by default".
            last_heartbeat = None
            seconds_since = None
            stale = True
        else:
            last_heartbeat = datetime.fromisoformat(raw)
            seconds_since = int((now - last_heartbeat).total_seconds())
            stale = seconds_since > stale_after_seconds

        raw_error_at = get_cursor(session, f"{name}_last_error_at")
        last_error_at = datetime.fromisoformat(raw_error_at) if raw_error_at else None
        last_error_message = get_cursor(session, f"{name}_last_error_message")

        if last_error_at is not None:
            # A recorded crash is definitionally not healthy, independent of what the
            # heartbeat-based staleness window would otherwise say.
            stale = True

        results.append(
            ConnectorHealthOut(
                name=name,
                last_heartbeat=last_heartbeat,
                seconds_since=seconds_since,
                stale=stale,
                last_error_at=last_error_at,
                last_error_message=last_error_message,
            )
        )
    return results
