import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from sentence_transformers import SentenceTransformer, util
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.item import Item
from app.services.sync_state import get_cursor

# Weak-signal escalation constants. Deliberately distinct from embedding_threshold (which
# compares a message against the focus text) — this compares messages against each other.
#
# Validated offline against the real 2026-08-02 250-item Gmail burst before being wired into
# the live pipeline, per the audit's explicit requirement — see CONTRIBUTING.md. First result
# at threshold 0.85: 249/250 burst items falsely flagged (avg cluster_count ~137). Raising the
# threshold did not help — the burst's pairwise similarities are perfectly bimodal (~0.12 for
# unrelated pairs, ~1.0 for the repeated marketing content, nothing in between), so no
# threshold value in a normal range discriminates. The actual cause: 3 automated senders each
# resending near-identical content dozens of times, which content-similarity alone can't tell
# apart from many different people converging on one real topic. Fixed by excluding same-sender
# pairs from the candidate pool, at the same 0.85 threshold — re-validated: max cluster_count
# across all 250 burst items drops to 0.
CLUSTER_SIMILARITY_THRESHOLD = 0.85
CLUSTER_WINDOW_HOURS = 24


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


def get_embedding(content: str) -> list[float]:
    model = _get_model()
    return model.encode(content, convert_to_tensor=False).tolist()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def count_recent_similar(
    session: Session,
    vector: list[float],
    exclude_item_id: str,
    sender: str,
    window_hours: int = CLUSTER_WINDOW_HOURS,
    similarity_threshold: float = CLUSTER_SIMILARITY_THRESHOLD,
) -> int:
    # items.created_at is stored as naive UTC (no tzinfo column, but written from
    # datetime.now(timezone.utc)) — the cutoff must match that exact naive-UTC shape,
    # not a tz-aware value, or the comparison silently misbehaves.
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).replace(tzinfo=None)

    # Same-sender candidates excluded — see the module-level comment above for why: one
    # automated sender resending near-identical content otherwise looks identical, in
    # embedding space, to many different people converging on one real topic.
    stmt = select(Item.embedding_vector).where(
        Item.embedding_vector.is_not(None),
        Item.created_at >= cutoff,
        Item.id != exclude_item_id,
        Item.sender != sender,
    )
    count = 0
    for (raw_vector,) in session.execute(stmt).all():
        candidate = json.loads(raw_vector)
        if _cosine_similarity(vector, candidate) >= similarity_threshold:
            count += 1
    return count
