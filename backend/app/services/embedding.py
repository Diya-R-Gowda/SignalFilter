from functools import lru_cache

from sentence_transformers import SentenceTransformer, util
from sqlalchemy.orm import Session

from app.config import settings
from app.services.sync_state import get_cursor


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model)


def similarity(focus_text: str, item_content: str) -> float:
    model = _get_model()
    embeddings = model.encode([focus_text, item_content], convert_to_tensor=True)
    score = util.cos_sim(embeddings[0], embeddings[1]).item()
    return score


def passes_stage1(session: Session, focus_text: str, item_content: str) -> tuple[bool, float]:
    score = similarity(focus_text, item_content)
    raw_threshold = get_cursor(session, "embedding_threshold")
    threshold = float(raw_threshold) if raw_threshold is not None else settings.embedding_threshold
    return score >= threshold, score
