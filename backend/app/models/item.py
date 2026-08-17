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
    # Slack channel ID, distinct from thread_id (which falls back to the channel ID for
    # non-threaded messages, so it can't be trusted as "the channel" on its own). Only
    # populated for source="slack" — needed so a GitHub-aware auto-reply click knows where to
    # post. source_timestamp doubles as the thread_ts anchor for the reply (valid for both
    # already-threaded and top-level messages), so no separate reply-thread column is needed.
    channel: Mapped[str | None] = mapped_column(String, nullable=True)

    focus_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_score: Mapped[float] = mapped_column(Float, nullable=True)
    passed_stage1: Mapped[bool] = mapped_column(Boolean, default=False)

    llm_score: Mapped[int] = mapped_column(Integer, nullable=True)
    llm_reason: Mapped[str] = mapped_column(Text, nullable=True)

    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    digested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Attention budget: set instead of notified=True when the daily budget is exhausted;
    # cleared back to NULL (with notified flipped True) on the next batch release.
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Weak-signal escalation: embedding_vector is the item's own content embedding
    # (JSON-encoded list of floats), computed only for items that passed stage 1.
    # cluster_count is how many similar recent items existed at scoring time.
    embedding_vector: Mapped[str | None] = mapped_column(Text, nullable=True)
    cluster_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # GitHub-aware auto-reply (Tier A): set only when a confident matching commit was found
    # for a Slack question and an actionable toast was sent offering to post it. reply_posted_at
    # stays NULL until a real Yes click posts it — also doubles as the signal for whether the
    # immediate-click-only window is actually wide enough in practice (see CONTRIBUTING.md).
    drafted_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
