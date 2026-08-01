from sqlalchemy.orm import Session

from app.models.sync_state import SyncState


def get_cursor(session: Session, key: str) -> str | None:
    state = session.get(SyncState, key)
    return state.value if state else None


def set_cursor(session: Session, key: str, value: str) -> None:
    state = session.get(SyncState, key)
    if state:
        state.value = value
    else:
        session.add(SyncState(key=key, value=value))
    session.commit()
