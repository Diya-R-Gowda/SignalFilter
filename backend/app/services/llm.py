import json

import requests

from app.config import settings

SYSTEM_PROMPT = """You are a triage assistant. You decide whether a message deserves to interrupt \
the user right now, given what they say they are currently focused on.

Score the message from 0 to 10:
- 0-2: unrelated to the focus, not urgent
- 3-5: loosely related or FYI, doesn't need an immediate interrupt
- 6-8: clearly relevant to the focus and time-sensitive
- 9-10: directly blocks or is critical to the focus right now

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
