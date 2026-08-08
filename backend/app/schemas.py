from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    sender: str
    content: str
    thread_id: str | None
    source_timestamp: str
    focus_text: str
    embedding_score: float | None
    passed_stage1: bool
    llm_score: int | None
    llm_reason: str | None
    notified: bool
    created_at: datetime


class FocusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    focus_text: str
    created_at: datetime


class FocusIn(BaseModel):
    focus_text: str


class FeedbackIn(BaseModel):
    thumbs_up: bool


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    item_id: str
    thumbs_up: bool
    created_at: datetime


class ConnectorHealthOut(BaseModel):
    name: str
    last_heartbeat: datetime | None
    seconds_since: int | None
    stale: bool
    last_error_at: datetime | None
    last_error_message: str | None


class SettingsOut(BaseModel):
    embedding_threshold: float
    embedding_threshold_source: Literal["default", "override"]
    interrupt_score_threshold: int
    interrupt_score_threshold_source: Literal["default", "override"]
    gmail_interrupt_score_threshold: int
    gmail_interrupt_score_threshold_source: Literal["default", "override"]


class SettingsIn(BaseModel):
    embedding_threshold: float | None = Field(default=None, ge=-1, le=1)
    interrupt_score_threshold: int | None = Field(default=None, ge=0, le=10)
    gmail_interrupt_score_threshold: int | None = Field(default=None, ge=0, le=10)
