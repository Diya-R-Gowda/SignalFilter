import json

import requests

from app.config import settings

SYSTEM_PROMPT = """You are a triage assistant. You decide whether a message deserves to interrupt \
the user right now, given what they say they are currently focused on.

Judge relevance by whether the message's SUBJECT/TOPIC matches the focus, not by how urgent \
or formal it sounds. A casual "how's X going?" about the exact thing the user is focused on \
IS related — it just isn't urgent. Only score low if the topic itself has nothing to do with \
the focus (e.g. social plans, meals, hobbies, other unrelated projects).

Automated or bulk mail — marketing, newsletters, promotions, "no-reply" senders, anything with \
an unsubscribe footer or a sales/CTA tone — always scores 0-1, even if it happens to mention \
words that overlap with the focus. These are never a personal, on-topic message and should never \
be treated as one.

Score the message from 0 to 10 using these bands:
- 0-1: different topic entirely, no connection to the focus
- 2-3: tangentially related at best
- 4-5: same topic as the focus, but a casual check-in/status question, no urgency
- 6-8: same topic as the focus and time-sensitive, needs a response or action soon
- 9-10: directly blocks or is critical to the focus right now

Examples (focus: "testing Signal Filter's Slack triage pipeline"):
- "anyone up for lunch?" -> 0 (different topic entirely)
- "how's the pipeline coming along?" -> 4 (same topic, casual, not urgent)
- "can you check if the pipeline is working?" -> 8 (same topic, actionable, urgent)

Respond with ONLY a JSON object: {"score": <int 0-10>, "reason": "<one short sentence>"}"""


def score_item(focus_text: str, item_content: str, sender: str, source: str) -> tuple[int, str]:
    user_prompt = (
        f"Current focus: {focus_text}\n\n"
        f"Incoming message (source: {source}, from: {sender}):\n{item_content}"
    )

    response = requests.post(
        f"{settings.ollama_host}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["message"]["content"]

    try:
        parsed = json.loads(content)
        score = int(parsed["score"])
        reason = str(parsed["reason"])
    except (json.JSONDecodeError, KeyError, ValueError):
        score, reason = 0, "LLM returned an unparseable response"

    return max(0, min(10, score)), reason


DRAFT_REPLY_SYSTEM_PROMPT = """You are drafting a short Slack reply on the user's behalf, based on ONE \
specific git commit that might answer their question.

Say confident=true whenever the commit's subject/body states something that directly answers the \
question — e.g. the question asks whether/when something was done, added, or fixed, and the commit \
describes doing exactly that thing. You don't need every detail spelled out — if the commit is clearly \
about the same specific thing being asked about and describes it as done, that counts as an answer.

Say confident=false only when the commit is about a different thing than the question asks about, or is \
merely on a related/adjacent topic without actually answering it (e.g. same general area of the project \
but a different specific feature or bug).

Examples:
- Question: "is dark mode implemented yet?" / Commit: "Add dark mode toggle to settings page" -> confident=true, reply along the lines of "Yep, dark mode toggle was added in the settings page."
- Question: "did we fix the login bug?" / Commit: "Refactor login form styling" -> confident=false (styling refactor isn't the same as a bug fix)
- Question: "anyone free for lunch?" / Commit: "Add dark mode toggle" -> confident=false (unrelated topic)

If confident, draft a short, casual Slack reply (1-2 sentences) grounded only in what the commit says.

Respond with ONLY a JSON object: {"confident": <bool>, "reply": "<short reply, or empty string if not confident>"}"""


def draft_reply_from_commit(
    question: str, commit_sha: str, commit_subject: str, commit_body: str
) -> tuple[str | None, str]:
    """Returns (drafted_reply, raw_llm_reason_or_error). drafted_reply is None whenever the
    model isn't confident the commit actually answers the question — this is the conservative
    default the feature's design requires, not an edge case to special-case around."""
    user_prompt = (
        f"Slack question: {question}\n\n"
        f"Candidate commit ({commit_sha[:8]}): {commit_subject}\n{commit_body}"
    )

    response = requests.post(
        f"{settings.ollama_host}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": DRAFT_REPLY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["message"]["content"]

    try:
        parsed = json.loads(content)
        confident = bool(parsed["confident"])
        reply = str(parsed["reply"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return None, "LLM returned an unparseable response"

    if not confident or not reply.strip():
        return None, "not confident"
    return reply, "confident"
