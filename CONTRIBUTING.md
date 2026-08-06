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
| Running live against real Slack traffic | 🟢 Done | Validated: relevant message ("can you check if the pipeline is working?") scored 8/10 and notified; irrelevant ("anyone up for lunch?") scored 3/10 and was correctly held back. Also caught and fixed a real bug — stage-1 threshold was too high, filtering out even relevant short messages before they reached the LLM |
| FastAPI HTTP API (`/items`, `/focus`, `/items/{id}/feedback`) | 🟢 Done | `backend/app/main.py` + `backend/app/schemas.py` — smoke-tested against the real DB via `TestClient` |
| Gmail connector | 🟢 Done | `backend/app/connectors/gmail_connector.py` — OAuth completed, live-tested: a real test email was picked up, scored (0/10, correctly filtered as unrelated to focus), and logged. Along the way found and fixed two real bugs: a Slack thread crash (`SocketModeHandler.start()` touching signals off the main thread) and a false-notification bug (LLM hallucinating a score for a message polled before Gmail had indexed its content) |
| React dashboard + 👍/👎 feedback UI | 🟡 Built, not yet run in a browser | `frontend/` — Vite + React + TS, surfaced/filtered columns, focus switcher, feedback buttons; type-checks and builds cleanly, not yet manually verified in a browser |
| Feedback-driven threshold tuning | ⚪ Not started | Week 3+ |
| Calendar integration / auto-focus detection | ⚪ Not started | Week 3+, long-term |
| Connector health visibility | ⚪ Not started | Week 3+ — see detailed idea below |
| In-dashboard tuning controls | ⚪ Not started | Week 3+ — see detailed idea below |
| Digest mode | ⚪ Not started | Week 3+ — see detailed idea below |

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
| **Week 3+** | Iterate on ranking quality, expand context, and harden reliability | 1. Use accumulated feedback to tune the stage-1 similarity threshold (or train a lightweight classifier — e.g. logistic regression on embeddings — on top of it).<br>2. Add Google Calendar as a context signal (e.g. "in a meeting" suppresses non-urgent interrupts, meeting titles inform focus).<br>3. Explore auto-detecting focus from calendar events/activity instead of always requiring manual input.<br>4. **GitHub-aware auto-reply with actionable notifications** — see detailed idea below.<br>5. **Connector health visibility** — see detailed idea below.<br>6. **In-dashboard tuning controls** — see detailed idea below.<br>7. **Digest mode** — see detailed idea below.<br>8. Longer-term/optional: browser extension injecting relevance scores directly into Gmail/Slack UI, multi-user support. | Ranking that visibly improves from real feedback, plus calendar-aware context and operational reliability — the "long-term" version of the MVP from the original pitch. |

## Week 3+ idea: GitHub-aware auto-reply with actionable notifications

**The idea:** connect a GitHub repo to Signal Filter. When a Slack question comes in that's already answered by something already committed (e.g. "did you fix the pipeline bug?" and there's a commit that did exactly that), the system drafts a reply from that commit instead of just notifying you to go answer it yourself. If nothing in the repo answers the question, it falls back to today's normal notify-only behavior.

**How the decision would extend the existing two-stage pipeline (a third branch, not a replacement):**

1. Stage 1 (embedding filter) and stage 2 (LLM relevance/urgency score) run exactly as they do today.
2. For items that clear the notify threshold, an additional check runs: *does this question already have a confident answer in recent commit history?* This needs its own retrieval step (embed commit messages/diffs/README — a small RAG index over the repo) and a separate LLM call whose job is specifically "does commit X answer question Y, and if so draft a short reply" — a QA task, distinct from the relevance-scoring task stage 2 already does. This step needs a **high confidence bar**: a wrong or hallucinated answer posted into Slack under your name is a much worse failure than no reply at all.
3. Outcome branches:
   - No confident answer found in the repo → normal notify, exactly like today.
   - Confident answer found → still notify, but the notification itself carries the drafted reply, not just the original message.

**Delivery mechanic — actionable Windows notification:**

- The native toast includes the drafted reply text plus two buttons: **Yes** (post it) / **No** (stale or wrong, don't post).
- `win11toast` supports action buttons via an `on_click` callback, so this is feasible with the notification library already in use — no new dependency needed.
- Because the click might happen well after the toast fires, the drafted reply and its target channel/thread ID need to be **persisted** (in the `items` row, not just held in memory) so whichever button gets clicked later still has everything it needs to act.
- **Yes** → the bot posts the drafted reply into the original Slack thread (needs the `chat:write` scope added — the bot is currently read-only).
- **No** → nothing gets posted; you go reply manually in Slack yourself, same as today.

**Why this doubles as the feedback loop:** clicking Yes/No on a drafted reply is functionally the same signal as the 👍/👎 feedback already planned for the dashboard (was the system's judgment correct?), just captured at the moment of interruption instead of requiring a later visit to a UI. That data can feed the same threshold-tuning work already planned for Week 3+.

**Open questions to resolve before building this:**

- How to index the repo for retrieval — full RAG over commit messages + diffs, or something simpler like just the last N commits' messages?
- Where to set the confidence threshold for "this counts as an answer" — needs to be conservative, since the cost of a wrong auto-reply is high.
- Whether this only applies to your own repos, or also team repos you don't solely own (a permissions/trust question, not just a technical one).
- Needs the Slack bot's scopes expanded to include `chat:write`.

## Week 3+ idea: Connector health visibility

**The idea:** make it obvious, at a glance, whether each connector (Slack, Gmail) is actually making progress — not just "the process is running," but "it successfully checked for new messages recently." This is a direct response to a real bug found during Week 2 live testing: the Gmail poller got stuck reprocessing the same message on every cycle for over eight minutes, and nothing in the running output made that obvious — it took manually comparing database timestamps and process state to diagnose. A silent failure like that could easily go unnoticed for hours in normal use, quietly missing every real email in the meantime.

**How it would work:**

- Each connector records a heartbeat on every cycle — success *or* handled failure, not just "found new mail." For Gmail this means updating a `last_poll_at` timestamp every 30–60s regardless of whether anything new showed up; for Slack (event-driven, not polling) it'd be more like "last event received" or a periodic synthetic self-check.
- Store heartbeats the same way the Gmail history cursor already is — reusing the `SyncState` key/value table (e.g. `gmail_last_poll_at`, `slack_last_event_at`), or a small dedicated `connector_health` table if more fields end up needed (last error message, consecutive failure count).
- New API endpoint, `GET /health`, returning each connector's last heartbeat and whether it's stale relative to its expected cadence.
- Dashboard: a small status strip — a colored dot and "last checked Ns ago" per connector — so a stuck or dead connector is visible the moment you glance at the page, not discovered by noticing a message never arrived.
- Optional escalation: if a heartbeat goes stale past some threshold, fire a local notification via the same `win11toast` plumbing already built ("Gmail connector hasn't polled in 5 minutes") — Signal Filter watching itself.

**Open questions to resolve before building this:**

- What counts as "stale" per connector — Gmail has a natural cadence (poll interval) to compare against; Slack's Socket Mode connection doesn't poll, so staleness needs a different definition (e.g. a periodic reconnect/ping check instead).
- Should staleness trigger an actual interrupt notification, or stay purely a dashboard indicator? An alert that itself becomes noisy (e.g. firing just because there's been no new mail, not because anything's actually broken) would undermine the whole point of the project.

## Week 3+ idea: In-dashboard tuning controls

**The idea:** stop requiring a code edit + process restart every time a threshold needs adjusting. Every tuning conversation during Week 2 (embedding threshold, per-source notify threshold) ended the same way: edit `.env` or `config.py`, kill the running listener, restart it, wait for models to reload — a slow loop that also meant losing whatever the connector was mid-processing. Exposing the tunable values through the API and dashboard turns that into something adjustable live, no restart required.

**How it would work:**

- Move the tunable values (`EMBEDDING_THRESHOLD`, `INTERRUPT_SCORE_THRESHOLD`, `GMAIL_INTERRUPT_SCORE_THRESHOLD`) out of being read once at process startup via `pydantic-settings`, and into a DB-backed store read live per item — the same pattern `FocusState` already uses (append-only or single-row table, read fresh on every `process_item()` call instead of cached at import time).
- New API endpoints: `GET /settings` and `POST /settings` (or per-key `PATCH`), reusing the existing `SyncState`-style key/value table or a small dedicated `Settings` table.
- Dashboard: a small settings panel — number inputs or sliders for each threshold — that applies immediately to the next message processed.
- `.env` stays as the bootstrapping default on first run; once a value is set via the dashboard, the DB value wins, mirroring how focus text already works (the `.env` file has no bearing on focus after the first `focus` command).

**Open questions to resolve before building this:**

- Should the API validate/clamp values (e.g. score thresholds must be 0–10, embedding threshold 0–1) rather than trusting arbitrary input?
- Does the DB value fully replace `.env` for these settings going forward, or should `.env` remain a documented fallback if the DB has no override yet?

## Week 3+ idea: Digest mode

**The idea:** right now every item is either interrupt-worthy (notifies immediately) or filtered (sits quietly, only visible if you happen to open the dashboard). That binary throws away a real middle ground — a message that's genuinely relevant but not urgent *right now* might still be worth knowing about by the end of the day, without deserving a real-time interrupt. A digest surfaces that middle band on its own schedule instead of losing it in the Filtered list forever.

**How it would work:**

- Define a "digest-worthy" score band distinct from the notify threshold — e.g. items that passed stage 1 with a genuinely on-topic reason but scored just below the per-source interrupt cutoff, rather than the clearly-irrelevant bulk mail already being hidden by the dashboard's low-relevance filter.
- A scheduled check (a background timer thread in the existing listener process, or a separate CLI command run via Windows Task Scheduler) periodically queries items in that band created since the last digest.
- Delivery: either a single low-priority summary notification ("3 things worth a look from today") or — probably better, since a digest that itself interrupts partly defeats the point — a dedicated "Digest" section on the dashboard that surfaces them without ever firing a toast.
- Needs a `digested` flag or `digested_at` timestamp on `Item` so the same item isn't pulled into every subsequent digest.

**Open questions to resolve before building this:**

- What cadence makes sense — hourly, a few fixed times a day, once at end of day?
- Exactly where the score band boundary sits, and whether it should be per-source like the notify threshold already is.
- Delivery mechanic — dashboard-only vs. a genuinely low-priority notification — needs to stay consistent with the project's core premise of not interrupting unless something truly earns it.

## Cost notes

Everything above runs at $0: Postgres/FastAPI/React/CLI are local and open-source, MiniLM + Qwen2.5:3b run locally via Ollama (no API billing), Slack/Gmail APIs are free-tier for personal-volume use, and Socket Mode avoids needing any public hosting or ngrok.

## Open questions / future decisions

- How the similarity threshold gets tuned over time (manual vs. learned from feedback)
- Whether `qwen2.5:3b-instruct` CPU inference speed holds up in practice once tested against real message volume — fallback would be a smaller/faster model or a tighter prompt
- Browser extension (inject relevance score directly into Gmail/Slack UI) — long-term idea, not in current scope
- Long-term: calendar-aware auto-focus detection, multi-user/team version
