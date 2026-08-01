from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.focus_state import FocusState


def get_current_focus_state(session: Session) -> FocusState | None:
    stmt = select(FocusState).order_by(FocusState.created_at.desc()).limit(1)
    return session.execute(stmt).scalar_one_or_none()


def get_current_focus(session: Session) -> str | None:
    row = get_current_focus_state(session)
    return row.focus_text if row else None


def set_focus(session: Session, focus_text: str) -> FocusState:
    state = FocusState(focus_text=focus_text)
    session.add(state)
    session.commit()
    session.refresh(state)
    return state
