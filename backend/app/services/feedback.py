from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.feedback import Feedback


def upsert_feedback(session: Session, item_id: str, thumbs_up: bool) -> Feedback:
    # Upsert, not insert — feedback_item_id_unique makes one vote per item the only valid
    # state; voting again (including via a Yes/No auto-reply click) replaces the previous
    # vote rather than adding a second row.
    feedback = session.query(Feedback).filter(Feedback.item_id == item_id).first()
    if feedback:
        feedback.thumbs_up = thumbs_up
        feedback.created_at = datetime.now(timezone.utc)
    else:
        feedback = Feedback(item_id=item_id, thumbs_up=thumbs_up)
        session.add(feedback)
    session.commit()
    session.refresh(feedback)
    return feedback
