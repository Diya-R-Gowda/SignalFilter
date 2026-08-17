import subprocess
import time
from pathlib import Path

from app.services.embedding import _cosine_similarity, get_embedding

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent

COMMIT_LIMIT = 200
REFRESH_INTERVAL_SECONDS = 600

# Calibrated against 4 real question/commit pairs against this repo's actual history (see
# CONTRIBUTING.md): genuine matches scored 0.577-0.618, an unrelated question scored 0.202,
# and one paraphrase-heavy question missed its true match entirely, ranking a wrong commit
# at 0.360 instead. 0.55 sits just under the lowest real match and comfortably above that
# false-lead score. Still a small sample — not a settled constant, same caveat this
# project's other calibrated thresholds (weak-signal escalation) carry.
MATCH_SIMILARITY_THRESHOLD = 0.55

# Module-level cache: list of {"sha": str, "subject": str, "body": str, "embedding": list[float]}.
# Rebuilt periodically on a background thread rather than backed by a DB table — this repo's
# commit history is small, so an in-memory rebuild is cheap and avoids a schema for what's
# fundamentally a derived/recomputable index.
_index: list[dict] = []

# Unit separator (\x1f) between fields, record separator (\x1e) between commits — both
# control characters are vanishingly unlikely to appear in real commit messages, unlike
# common delimiters (|, :, newline) which commit bodies use freely.
_LOG_FORMAT = "%H%x1f%s%x1f%b%x1e"


def _fetch_recent_commits(limit: int = COMMIT_LIMIT) -> list[dict]:
    result = subprocess.run(
        ["git", "log", f"-n{limit}", f"--pretty=format:{_LOG_FORMAT}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git log failed: {result.stderr.strip()}")

    commits = []
    for record in result.stdout.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) != 3:
            continue
        sha, subject, body = parts
        commits.append({"sha": sha, "subject": subject, "body": body.strip()})
    return commits


def rebuild_index() -> None:
    global _index
    commits = _fetch_recent_commits()
    new_index = []
    for commit in commits:
        text = commit["subject"]
        if commit["body"]:
            text = f"{text}\n{commit['body']}"
        new_index.append(
            {
                "sha": commit["sha"],
                "subject": commit["subject"],
                "body": commit["body"],
                "embedding": get_embedding(text),
            }
        )
    _index = new_index


def find_matching_commit(question_text: str) -> dict | None:
    """Returns the best-matching commit dict (sha/subject/body) if its similarity to
    question_text clears MATCH_SIMILARITY_THRESHOLD, else None. Never raises on an empty
    index (repo_index hasn't finished its first build yet) — just returns no match."""
    if not _index:
        return None

    question_vector = get_embedding(question_text)
    best = None
    best_score = MATCH_SIMILARITY_THRESHOLD
    for commit in _index:
        score = _cosine_similarity(question_vector, commit["embedding"])
        if score >= best_score:
            best = commit
            best_score = score
    return best


def start_repo_index_refresher() -> None:
    while True:
        try:
            rebuild_index()
        except Exception as exc:
            # Best-effort — a transient git/subprocess failure must not take down the
            # process running the actual triage pipeline alongside it.
            print(f"[repo_index] rebuild failed: {exc}")
        time.sleep(REFRESH_INTERVAL_SECONDS)
