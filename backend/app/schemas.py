from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
