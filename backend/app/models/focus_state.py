import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FocusState(Base):
    """History of focus-text changes. The most recently created row is the current focus."""

    __tablename__ = "focus_states"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    focus_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # "manual" | "calendar" | NULL. NULL means every row written before this column existed —
    # treated as equivalent to "manual" everywhere it's read, never backfilled.
    source: Mapped[str | None] = mapped_column(String, nullable=True)
