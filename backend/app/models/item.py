import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, Float, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    source: Mapped[str] = mapped_column(String, nullable=False)  # "slack" | "gmail"
    sender: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    thread_id: Mapped[str] = mapped_column(String, nullable=True)
    source_timestamp: Mapped[str] = mapped_column(String, nullable=False)

    focus_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_score: Mapped[float] = mapped_column(Float, nullable=True)
    passed_stage1: Mapped[bool] = mapped_column(Boolean, default=False)

    llm_score: Mapped[int] = mapped_column(Integer, nullable=True)
    llm_reason: Mapped[str] = mapped_column(Text, nullable=True)

    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
