from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SyncState(Base):
    """Generic key/value cursor storage for connectors (e.g. Gmail's historyId)."""

    __tablename__ = "sync_states"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
