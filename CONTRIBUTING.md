# Signal Filter — Project Plan

## Status (as of 2026-08-01)

| Task | Status | Detail |
|---|---|---|
| Define problem, architecture, tech stack | 🟢 Done | Postgres (practice goal), local MiniLM embeddings, local `qwen2.5:3b-instruct` via Ollama (hybrid two-stage pipeline), monorepo, CLI-first, everything free — no paid APIs |
| Install Postgres, create `signalfilter` DB | 🟢 Done | Password-reset via `pg_hba.conf` trust workaround, then `CREATE DATABASE` |
| Install Ollama, pull `qwen2.5:3b-instruct` | 🟢 Done | ~1.9GB model, runs CPU-only (16GB RAM, Intel Iris Xe iGPU, no discrete GPU) |
| Scaffold FastAPI backend + Python deps | 🟢 Done | `backend/`, venv, `requirements.txt`, all installed cleanly on Python 3.14 |
| SQLAlchemy models: `Item`, `FocusState`, `Feedback` | 🟢 Done | `backend/app/models/`, tables created via `init_db()` |
| Embedding filter (stage 1) | 🟢 Done | `backend/app/services/embedding.py` — tested: relevant message scored 0.43, irrelevant scored 0.07 |
| LLM judgment (stage 2) | 🟢 Done | `backend/app/services/llm.py` — tested: real message scored 8/10 with a sensible reason |
| Native Windows notifications | 🟢 Done | `backend/app/services/notify.py` (`win11toast`) — tested, toast fired |
| Pipeline orchestrator | 🟢 Done | `backend/app/pipeline.py` ties stage 1 → stage 2 → notify → log together |
| Slack connector (Socket Mode) | 🟢 Done | `backend/app/connectors/slack_connector.py` — live, connected to a real Slack app/workspace |
| CLI (`focus` / `run`) | 🟢 Done | `backend/app/cli.py` — focus text updatable live without restarting the listener |
| Setup docs (root README + backend README) | 🟢 Done | Full Postgres/Ollama/Slack-app walkthrough for a fresh machine |
| Running live against real Slack traffic | 🟡 In progress | Listener is running; validating real messages get filtered/scored/notified correctly |
| Gmail connector | ⚪ Not started | Week 2 |
| React dashboard + 👍/👎 feedback UI | ⚪ Not started | Week 2 |
| Feedback-driven threshold tuning | ⚪ Not started | Week 3+ |
| Calendar integration / auto-focus detection | ⚪ Not started | Week 3+, long-term |

## The idea

You're not overwhelmed because you get too many notifications — you're overwhelmed because most of them don't matter right now. Signal Filter learns what you're currently focused on (a short text you set, updated throughout the day) and only interrupts you for things actually relevant to that, muting the rest instead of silently dropping it.

**Why it's hard:** priorities shift hour to hour, and "urgent" is relative to your current focus, not urgent in general. The system needs to understand meaning (not keyword/sender rules) and do it fast enough to triage in real time across Slack and Gmail.

## Tech stack & key decisions

| Area | Choice | Why |
|---|---|---|
| Storage | PostgreSQL (local) | Chosen partly to get Postgres practice; SQLAlchemy models make it easy to swap later if ever needed |
| Stage-1 embeddings | `sentence-transformers` — `all-MiniLM-L6-v2` | Local, free, fast enough on CPU for cheap similarity scoring |
| Stage-2 LLM | Local via **Ollama** — `qwen2.5:3b-instruct` | Free (no API cost); smaller + better instruction-following/structured output than `phi3:mini`, important given CPU-only inference (16GB RAM, Intel Iris Xe iGPU, no discrete GPU) |
| Repo structure | Monorepo (`/backend`, `/frontend` later) | Simplest for a solo MVP, no separate deploy targets yet |
| Notification delivery | Native Windows toast notifications | `win11toast` or `winsdk` — not `win10toast`, which is unmaintained/flaky on modern Windows |
| Frontend | Deferred — CLI first | Backend/pipeline needs to work before a dashboard is useful |
| Cost constraint | Everything must be free | No paid APIs or cloud resources anywhere in the stack |

## Architecture

### Data layer

- **Slack**: Socket Mode — receives events without needing a public URL (no ngrok, no public hosting for MVP)
- **Gmail**: polling via `history.list` every 30–60s — no Pub/Sub push setup needed for MVP
- Normalize everything into a unified `Item` schema: `{source, sender, content, timestamp, thread_id}`
- Postgres via SQLAlchemy

### Intelligence layer — two-stage ranking pipeline

Every incoming message runs through two stages before a notification decision is made:

| Stage | Name | What happens | Tech | Threshold / behavior | Output |
|---|---|---|---|---|---|
| 1 | Embedding filter | Embed the incoming item's text and the user's current focus string, then compute cosine similarity between the two vectors. This is the cheap, fast pass that runs on *every* message. | `sentence-transformers` — `all-MiniLM-L6-v2`, local, CPU | Start **permissive/low** — a missed urgent message is worse than a few extra LLM calls downstream. Raise it later once feedback data justifies tightening it. | A similarity score (0–1). Items below threshold are filtered straight to the low-priority digest, skipping stage 2 entirely — this is what keeps the pipeline fast and free. |
| 2 | LLM judgment | Only items that clear the stage-1 threshold get sent here. The LLM reads the message plus the user's focus string and reasons about semantic relevance, urgency, and context (e.g. "is this actually blocking something," not just "does it mention similar words"). | Local `qwen2.5:3b-instruct` via Ollama, CPU inference | No threshold to tune yet — every item that reaches this stage gets scored. Prompt should ask for a structured output (e.g. JSON with a 0–10 interrupt score + one-line reason). | A final interrupt score + short justification. Above a cutoff → native Windows notification fires. Below it → item stays in the CLI/dashboard stream but doesn't interrupt. |

**Feedback loop** (runs alongside both stages, not a stage itself): log 👍/👎 on every triage decision to Postgres **from day one** — embedding score, LLM score, and user feedback together — even before anything consumes it. Much easier to capture this now than to retrofit it once real usage data exists.

### Delivery

- Native Windows notification only for the top-ranked/high-interrupt items
- Everything else stays visible in CLI output (later: dashboard digest) — never silently discarded

## Project phases

| Phase | Focus | Detailed steps | Deliverable |
|---|---|---|---|
| **Week 1** | Backend pipeline, one connector, CLI only — no frontend yet | 1. Scaffold FastAPI project + Postgres connection via SQLAlchemy.<br>2. Define `Item`, `FocusState`, `Feedback` tables.<br>3. Build Slack connector using **Socket Mode** (no public URL/ngrok needed) — pull real messages into the `Item` schema.<br>4. Add manual focus-text input (CLI arg or simple POST endpoint) so you can set/change "what I'm focused on" without a UI.<br>5. Wire up the two-stage pipeline (embedding filter → local LLM via Ollama) end-to-end on real Slack messages.<br>6. Fire native Windows toast notifications (`win11toast`/`winsdk`) for items that clear the interrupt-score cutoff.<br>7. Log every triage decision (both scores + eventual feedback) to Postgres. | Real Slack messages flowing through the full pipeline in real time, triggering actual Windows notifications for the relevant ones — provable end-to-end, even with zero UI. |
| **Week 2** | Second connector + first UI | 1. Add Gmail connector (polling `history.list` every 30–60s, no Pub/Sub needed).<br>2. Normalize Gmail messages into the same `Item` schema so the pipeline doesn't care which source an item came from.<br>3. Build a simple React/TS dashboard: unified stream view, split into "surfaced" vs "filtered" items.<br>4. Add 👍/👎 buttons on each item, wired to the `Feedback` table already logging since Week 1. | A working local app showing both Slack + Gmail items ranked by relevance, with feedback capture live — usable on your own real inbox for a few days. |
| **Week 3+** | Iterate on ranking quality, expand context | 1. Use accumulated feedback to tune the stage-1 similarity threshold (or train a lightweight classifier — e.g. logistic regression on embeddings — on top of it).<br>2. Add Google Calendar as a context signal (e.g. "in a meeting" suppresses non-urgent interrupts, meeting titles inform focus).<br>3. Explore auto-detecting focus from calendar events/activity instead of always requiring manual input.<br>4. Longer-term/optional: browser extension injecting relevance scores directly into Gmail/Slack UI, multi-user support. | Ranking that visibly improves from real feedback, plus calendar-aware context — the "long-term" version of the MVP from the original pitch. |

## Cost notes

Everything above runs at $0: Postgres/FastAPI/React/CLI are local and open-source, MiniLM + Qwen2.5:3b run locally via Ollama (no API billing), Slack/Gmail APIs are free-tier for personal-volume use, and Socket Mode avoids needing any public hosting or ngrok.

## Open questions / future decisions

- How the similarity threshold gets tuned over time (manual vs. learned from feedback)
- Whether `qwen2.5:3b-instruct` CPU inference speed holds up in practice once tested against real message volume — fallback would be a smaller/faster model or a tighter prompt
- Browser extension (inject relevance score directly into Gmail/Slack UI) — long-term idea, not in current scope
- Long-term: calendar-aware auto-focus detection, multi-user/team version
