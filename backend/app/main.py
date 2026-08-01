from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session, init_db
from app.models.feedback import Feedback
from app.models.item import Item
from app.schemas import FeedbackIn, FeedbackOut, FocusIn, FocusOut, ItemOut
from app.services.focus import get_current_focus_state, set_focus

app = FastAPI(title="Signal Filter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
    return list(session.execute(stmt).scalars().all())


@app.get("/focus", response_model=FocusOut | None)
def read_focus(session: Session = Depends(get_session)):
    return get_current_focus_state(session)


@app.post("/focus", response_model=FocusOut)
def update_focus(body: FocusIn, session: Session = Depends(get_session)):
    return set_focus(session, body.focus_text)


@app.post("/items/{item_id}/feedback", response_model=FeedbackOut)
def create_feedback(item_id: str, body: FeedbackIn, session: Session = Depends(get_session)):
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    feedback = Feedback(item_id=item_id, thumbs_up=body.thumbs_up)
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    return feedback
