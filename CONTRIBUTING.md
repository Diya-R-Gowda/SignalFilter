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
| Connector health visibility | 🟢 Done | Heartbeats (`gmail_last_poll_at`, `slack_last_heartbeat_at`) via `SyncState`, `GET /health`, dashboard status strip — see detailed writeup below |
| Graceful connector failure handling | 🟢 Done | Found and fixed live: a dead Slack token was crashing the whole process (and Gmail with it) at import time. Connectors now fail their own thread only, record why, and auto-clear the record on next successful start — see detailed writeup below |
| In-dashboard tuning controls | ⚪ Not started | Week 3+ — see detailed idea below |
| Digest mode | ⚪ Not started | Week 3+ — see detailed idea below |
| Attention budget | ⚪ Not started | Week 3+ — see detailed idea below |
| Weak-signal escalation across messages | ⚪ Not started | Week 3+ — see detailed idea below |
| On-device personalization via local fine-tuning | ⚪ Not started | Week 3+, long-term — see detailed idea below |
| Flow-state-aware dynamic strictness | ⚪ Not started | Week 3+ — see detailed idea below |
| Self-auditing the AI judge (golden-set regression) | ⚪ Not started | Week 3+ — see detailed idea below |
| Per-sender adaptive trust | ⚪ Not started | Week 3+ — see detailed idea below |

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
| **Week 3+** | Iterate on ranking quality, expand context, and harden reliability | 1. Use accumulated feedback to tune the stage-1 similarity threshold (or train a lightweight classifier — e.g. logistic regression on embeddings — on top of it).<br>2. Add Google Calendar as a context signal (e.g. "in a meeting" suppresses non-urgent interrupts, meeting titles inform focus).<br>3. Explore auto-detecting focus from calendar events/activity instead of always requiring manual input.<br>4. **GitHub-aware auto-reply with actionable notifications** — see detailed idea below.<br>5. ~~Connector health visibility~~ — done, see detailed writeup below.<br>5b. ~~Graceful connector failure handling~~ — done, see detailed writeup below.<br>6. **In-dashboard tuning controls** — see detailed idea below.<br>7. **Digest mode** — see detailed idea below.<br>8. **Attention budget** — see detailed idea below.<br>9. **Weak-signal escalation across messages** — see detailed idea below.<br>10. **On-device personalization via local fine-tuning** — see detailed idea below.<br>11. **Flow-state-aware dynamic strictness** — see detailed idea below.<br>12. **Self-auditing the AI judge** — see detailed idea below.<br>13. **Per-sender adaptive trust** — see detailed idea below.<br>14. Longer-term/optional: browser extension injecting relevance scores directly into Gmail/Slack UI, multi-user support. | Ranking that visibly improves from real feedback, plus calendar-aware context and operational reliability — the "long-term" version of the MVP from the original pitch. |

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

## Week 3+ (done): Connector health visibility

**The idea:** make it obvious, at a glance, whether each connector (Slack, Gmail) is actually making progress — not just "the process is running," but "it successfully checked for new messages recently." This was a direct response to a real bug found during Week 2 live testing: the Gmail poller got stuck reprocessing the same message on every cycle for over eight minutes, and nothing in the running output made that obvious — it took manually comparing database timestamps and process state to diagnose. A silent failure like that could easily go unnoticed for hours in normal use, quietly missing every real email in the meantime.

**What was built (MVP scope):**

- Each connector writes a heartbeat timestamp on every cycle — Gmail updates `gmail_last_poll_at` at the start of every poll (every 40s), regardless of whether anything new showed up; Slack updates `slack_last_heartbeat_at` every 30s from a dedicated background thread started once its socket connection is established.
- Heartbeats reuse the existing `SyncState` key/value table (same pattern as the Gmail history cursor) — no new schema needed.
- `GET /health` (`backend/app/main.py`) returns each connector's last heartbeat, seconds since, and whether it's stale — staleness threshold is 3× each connector's own heartbeat interval (120s for Gmail, 90s for Slack).
- Dashboard status strip (`frontend/src/ConnectorStatus.tsx`) — a colored dot + "checked Ns ago" per connector, polled alongside items/focus.
- Verified live by killing the Gmail listener and watching `/health` flip from fresh to stale as the threshold passed, then confirming a restart brought it back to healthy.

**Explicitly not built (deliberately out of MVP scope):** no escalation/toast-on-stale. A heartbeat-staleness notification risks becoming noisy on its own (e.g. firing just because there's been no new mail, not because anything's actually broken), which would undermine the whole point of the project. Revisit only if silent staleness turns out to be a real recurring problem in practice.

## Week 3+ (done): Graceful connector failure handling

**The idea:** a connector should never be able to take the whole process — and the *other* connector — down with it. This was triggered by a real crash found while building health visibility above: the Slack bot token had gone dead (`account_inactive`), and `slack_bolt.App(...)` calls `auth_test()` eagerly inside its constructor. That constructor was running at *module import time*, in the main thread, before any connector thread was even started — so the exception killed the entire process, taking a perfectly healthy Gmail connector down with it. It wasn't a thread-safety bug (Python doesn't propagate exceptions between threads by default); it was a crash that happened *before* threading began.

**What was built:**

- Both `App(...)` construction (Slack) and `get_gmail_service()` (Gmail) already happen lazily inside each connector's `start_*_listener()` function rather than at module scope — Gmail already worked this way; Slack's `App(...)` and event-handler registration were moved out of module scope to match.
- Each `start_*_listener()` wraps its connection step in try/except. On failure: print the error, record it (`{name}_last_error_at` / `{name}_last_error_message` via `SyncState`), and return — the thread ends cleanly, the process and the other connector are unaffected. **No auto-retry** — an invalid token or missing credentials needs a human to fix the root cause, not a retry loop masking it.
- `GET /health` treats a recorded error as an automatic override: `stale` is forced `true` whenever `last_error_at` is present, regardless of what heartbeat timing alone would say. The dashboard status dot distinguishes "crashed" (known cause, shown immediately) from "stale" (gone quiet, unknown why) — `ConnectorStatus.tsx`'s `dotClass()`.
- **Follow-up fix, same feature:** the first version left a resolved error stuck forever — fixing credentials and restarting cleared nothing, since no code path removed the old error record, so a genuinely healthy connector kept reporting as crashed. Fixed by clearing `{name}_last_error_at`/`_message` at the exact point a connector's connection is confirmed established (right before Slack's heartbeat thread starts; right before Gmail's poll loop starts) — via a new `delete_cursor()` helper in `sync_state.py` rather than an empty-string sentinel, since `SyncState.value` is non-nullable and a deleted row is what `get_cursor()` already treats as "no error."
- Verified live, twice over: (a) with the actual dead Slack token in `.env`, confirmed Gmail ran normally under `--source all` while Slack failed and recorded why, process alive throughout; (b) temporarily hid `credentials.json`/`token.json`, confirmed Gmail failed the same way and recorded the error, then restored the files and restarted, confirming `/health` returned to a clean `stale: false` state with both error fields `null` — not just a fresh heartbeat sitting next to a stale leftover error.

**Explicitly not built:** any retry logic, any acknowledgment flow, any history/log of past errors, any UI for viewing past crashes. A crash is either currently true (shown) or resolved (cleared) — there's no in-between state or audit trail. If a persistent incident log is ever wanted, that's a different feature, not a variant of this one.

**Still outstanding (unrelated to this fix, pre-existing):** the real Slack bot token in `.env` is genuinely dead and needs regenerating from [api.slack.com/apps](https://api.slack.com/apps) — this feature makes that failure *survivable*, not *resolved*.

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

## Week 3+ idea: Attention budget

**The idea:** most triage tools (this one included, so far) treat "should this interrupt me" as a pure content question — score the message, compare to a fixed threshold, done. But attention itself is a depletable resource, not an infinite gate to filter through. Give yourself a daily interrupt budget (e.g. 15 notifications) — once it's spent, even a message that would normally clear the threshold gets queued instead of firing immediately. This is closer to how behavioral economics treats scarce attention than how any consumer notification tool actually works.

**How it would work:**

- Add a per-day (or rolling-window) counter of notifications fired, alongside the existing `notified` count already implicit in the `items` table.
- Once the budget is spent, items that clear the normal score threshold get a new status — e.g. `queued` — instead of immediately notifying; they surface in the dashboard as "would have notified" so nothing is silently lost, just deferred.
- Budget resets on a schedule (daily, or a rolling 24h window) and is itself a per-source or global setting depending on how the in-dashboard tuning controls idea above shapes up.
- Optional: let higher-scoring items "bump" a lower-scoring queued item if the budget is full but something more urgent arrives — a priority-queue behavior rather than strict first-come-first-served exhaustion.

**Open questions to resolve before building this:**

- What's a sane default budget, and should it differ by source (Slack vs Gmail naturally have different volumes)?
- Should queued items get released as a batch once the budget resets, or trickle out on their original schedule the next day?
- Does an urgent (9–10 score) item ever bypass the budget entirely, or is the budget a hard cap with no exceptions?

## Week 3+ idea: Weak-signal escalation across messages

**The idea:** every message is currently scored in complete isolation — stage 1 and stage 2 both only ever look at one message against the focus text. But real urgency sometimes only becomes visible in aggregate: if three different people ask about the same unmerged PR within an hour, each message individually might land at a 4 or 5 (casual, not urgent) and never notify — yet the fact that it keeps coming up *is* itself a strong signal that something's actually blocking people. Almost no triage tool aggregates across messages like this; everything scores independently.

**How it would work:**

- After stage 2 scores an item, run a lightweight aggregate check: how many other items in some recent window (e.g. last few hours) have a similar embedding to this one (reusing the stage-1 embedding model, comparing against recently stored embeddings rather than just the focus text)?
- If a cluster of similar-topic messages crosses some count threshold within the window, escalate the *next* one (or retroactively flag the cluster) even though no single message alone cleared the notify bar — effectively a repetition-based override on top of the existing per-message score.
- This needs the embeddings already computed at stage 1 to be persisted queryably (they already are, via `embedding_score`, but the actual vector itself isn't currently stored — only the scalar similarity to focus — so this would require storing the raw embedding vector per item, e.g. via `pgvector` or a simple in-memory recent-embeddings cache).

**Open questions to resolve before building this:**

- What counts as "similar enough" to cluster — a cosine similarity threshold between two messages' embeddings, distinct from the existing focus-similarity threshold?
- How many occurrences within what time window justifies escalation — needs tuning to avoid false escalation on naturally repetitive but unimportant chatter (e.g. a recurring automated digest email).
- Does escalation fire a notification directly, or just visually flag the cluster in the dashboard for you to notice?

## Week 3+ idea: On-device personalization via local fine-tuning

**The idea:** the feedback-driven tuning already planned for Week 3+ adjusts a single threshold number from 👍/👎 data. This goes further — periodically fine-tune (e.g. LoRA-adapt) the local `qwen2.5:3b-instruct` model itself on your accumulated feedback, so the model's actual judgment adapts to your specific taste over time rather than just a static prompt plus a global cutoff. Consumer "personalization" almost always means preference toggles; on-device model adaptation from real usage is rare even in commercial products, and fits the project's zero-cost/fully-local ethos exactly.

**How it would work:**

- Periodically (e.g. weekly, run manually or via a scheduled task) export `(focus_text, content, llm_score, thumbs_up)` rows from the `items`/`feedback` tables as a small training set.
- Run a LoRA fine-tune pass on `qwen2.5:3b-instruct` using that set — Ollama doesn't do this natively, so this would likely mean a separate local fine-tuning toolchain (e.g. `unsloth` or plain `peft`/`transformers`) producing an adapter, then serving the adapted model through Ollama (via a custom Modelfile layering the LoRA weights) instead of the stock model.
- Needs a clear rollback path — keep the previous adapter/model available and compare scoring behavior on the golden-set regression (see the self-auditing idea below) before fully switching over, since a bad fine-tune could silently make judgment worse, not better.

**Open questions to resolve before building this:**

- Is there realistically enough feedback volume from single-user usage to make fine-tuning meaningful, or does it need weeks/months of data first?
- CPU-only fine-tuning (no discrete GPU) may be slow even for a 3B model with LoRA — needs a feasibility check before committing to this over just the simpler threshold-tuning approach.
- How to validate a new fine-tune didn't regress before trusting it live — ties directly into the self-auditing/golden-set idea below.

## Week 3+ idea: Flow-state-aware dynamic strictness

**The idea:** the calendar integration already planned suppresses interrupts based on explicit calendar state ("in a meeting"). This goes further using purely local, passive signals: read idle time and active-window activity (no cloud, no calendar needed) to infer whether you're in deep, uninterrupted flow versus already context-switching a lot, and dynamically raise or lower the interrupt threshold based on that inferred state — not just a binary busy/free from a calendar, but real behavioral signal about how deep you currently are.

**How it would work:**

- A lightweight local background check (e.g. via `pywin32`/`pygetwindow` for active window + a simple idle-time check via `GetLastInputInfo` on Windows) samples periodically: how long has the active window been the same, how recently was there input activity.
- Derive a rough "flow score" — long uninterrupted stretch in one app = likely deep focus = raise the interrupt threshold temporarily; frequent window-switching = already fragmented attention = threshold can relax back to normal, since an extra interrupt costs less right now.
- Feed this as a temporary multiplier/offset on top of whatever the per-source threshold already is (from the in-dashboard tuning controls idea), not a replacement for it.

**Open questions to resolve before building this:**

- How to calibrate "deep flow" vs. just idle/away from keyboard — long inactivity isn't the same as long focus, and the signal needs to distinguish them (e.g. idle time near zero + same window for a long stretch = flow; idle time high = probably not at the desk at all).
- Privacy/scope consideration: this reads window titles, which could include sensitive info (document names, URLs) — needs to stay purely local and probably shouldn't log the actual titles anywhere, just the derived flow score.
- Does this apply globally or only during hours you'd otherwise expect to be working?

## Week 3+ idea: Self-auditing the AI judge

**The idea:** every prompt rewrite, threshold change, or model swap so far has been validated by live-testing against real messages in the moment — which works, but is manual and easy to skip under time pressure. Keep a small fixed "golden set" of representative messages with known-expected scores (a handful of clearly-irrelevant, clearly-urgent, and deliberately-borderline examples), and automatically re-run it after any change to the prompt, thresholds, or model. If the scoring distribution shifts unexpectedly from the last known-good baseline, flag it before trusting the change. This kind of regression testing for an AI judge's behavior is standard in serious ML production systems and essentially never present in personal tools — but this project already stumbled into needing exactly this today (a prompt rewrite made without this check could easily have silently broken something that live-testing happened to catch).

**How it would work:**

- A small fixture file (e.g. `backend/tests/golden_set.json`) of `{focus_text, content, sender, source, expected_score_range}` entries, covering the known-tricky cases already discovered live (casual-but-related, marketing/bulk mail, urgent-and-related, empty content, etc.).
- A CLI command (e.g. `python -m app.cli audit`) that runs every golden-set case through the current `llm.score_item()` and reports any that fall outside their expected range, plus a diff against the previous run's scores if one was saved.
- Run this manually after any prompt/threshold/model change, before restarting the live listener with it — cheap insurance against exactly the kind of regression that's been caught live so far.

**Open questions to resolve before building this:**

- How many golden-set cases are enough to be meaningful without becoming a maintenance burden to keep updated as the focus text/use case evolves?
- Should this block a config change (hard gate) or just warn (soft check you can override)?

## Week 3+ idea: Per-sender adaptive trust

**The idea:** right now relevance is judged purely from message content against the focus text — the sender's identity plays no role beyond being included in the LLM prompt as context. But real-world triage isn't purely content-based: some senders are reliably noise regardless of topic (a marketing address, a low-signal group chat) and some are reliably worth attention (your manager, a close collaborator) almost independent of what they're currently saying. Blend a lightweight per-sender trust prior — learned purely from your own feedback history, not hardcoded rules — into the final score.

**How it would work:**

- Maintain a simple running statistic per sender (e.g. mean llm_score and thumbs-up rate over their historical items) — a small aggregate query over the existing `items`/`feedback` tables grouped by `sender`, no new model needed to start.
- Blend this as a modest adjustment to the LLM's per-message score (e.g. a sender with a strong history of thumbs-down on high scores nudges future scores down slightly; a sender with a strong history of thumbs-up on notifications nudges up) rather than a hard override — content relevance should still dominate.
- This is a natural extension of the feedback-driven tuning already planned, just applied per-sender instead of globally.

**Open questions to resolve before building this:**

- How much history is needed per sender before the prior is trustworthy (avoid overreacting to one or two data points from a new sender)?
- Should this be visible/explainable in the dashboard (e.g. "score adjusted down: this sender's messages are usually not relevant") so it doesn't feel like an opaque black box?
- Risk of the prior becoming self-fulfilling — if a sender's messages start getting suppressed, you get less chance to give feedback on them, potentially entrenching an early wrong impression.

## Alternate form: Browser extension

**The idea:** instead of (or alongside) the React dashboard, ship Signal Filter's frontend as a browser extension. This isn't a rewrite — the Python backend (Slack/Gmail connectors, Ollama, Postgres, the FastAPI API) keeps running locally exactly as it does today; an extension is just a different client hitting the same `localhost:8000` API the dashboard already talks to. Two distinct versions worth building, in order of ambition:

1. **Popup/side-panel dashboard** — the simplest version: the extension's popup (or a persistent side panel, which Chrome/Edge support via the Side Panel API) fetches `/items` and `/focus` the same way `App.tsx` does now, showing Surfaced/Filtered right from the browser toolbar instead of a separate tab. Close to a direct port of the existing dashboard into an extension shell.
2. **Inline injection into Gmail/Slack's own web UI** — the more differentiated version, already noted as a long-term idea before this was written up in detail: a content script that reads the current Gmail/Slack web page and injects a relevance badge or highlight directly next to each message in the inbox/channel list, using scores already computed by the existing pipeline (matched up via `thread_id`/sender/content, or a new endpoint like `GET /items/by-thread/{thread_id}`). This means never needing to open a separate dashboard at all — the triage decision shows up right where the message already is.

**What doesn't change:** the extension is purely a frontend. It cannot host the Slack Socket Mode connection, the Gmail poller, Ollama, or Postgres — those need a long-running local process regardless, especially since Manifest V3 (the current Chrome extension platform) intentionally limits how long extension background scripts can run, ruling out hosting the actual pipeline inside the extension itself. The backend stays exactly as architected; this only adds a new way to see its output.

**How it would work, technically:**

- Manifest V3 extension, `host_permissions` scoped to `http://localhost:8000/*` so it's allowed to call the local API from a content script or popup (Chrome blocks arbitrary localhost fetches from web pages by default, but an extension with explicit permission is exempt).
- Reuse `frontend/src/api.ts`'s fetch wrappers largely as-is — the API surface doesn't need to change for the popup version.
- For inline injection: a content script matching `mail.google.com` / `app.slack.com`, using `MutationObserver` to catch Gmail's/Slack's dynamically-rendered message lists (both are heavy SPAs, so this can't rely on a static DOM), matching each visible message to its `Item` row and rendering a small badge (color-coded by score, tooltip with the LLM's reason) without altering the site's own functionality.

**Open questions to resolve before building this:**

- Gmail and Slack's web UIs are both unstable/obfuscated DOM targets that change over time — a content script matching their internals is inherently more fragile than the connectors talking to their official APIs, and would need ongoing maintenance as their frontends change.
- Does the popup version replace the standalone dashboard, or do both coexist (dashboard for a fuller view, extension for at-a-glance/inline)?
- CORS is already handled for `localhost` broadly (see the dashboard's CORS fix) — an extension's origin (`chrome-extension://...`) would need to be added to the allowed origins too.
- Packaging/distribution: purely a local unlisted extension (load unpacked, or a private Chrome Web Store listing), since this is a personal tool reading personal data — not intended for public distribution as-is.

## Cost notes

Everything above runs at $0: Postgres/FastAPI/React/CLI are local and open-source, MiniLM + Qwen2.5:3b run locally via Ollama (no API billing), Slack/Gmail APIs are free-tier for personal-volume use, and Socket Mode avoids needing any public hosting or ngrok.

## Open questions / future decisions

- How the similarity threshold gets tuned over time (manual vs. learned from feedback)
- Whether `qwen2.5:3b-instruct` CPU inference speed holds up in practice once tested against real message volume — fallback would be a smaller/faster model or a tighter prompt
- Browser extension as an alternate frontend — see detailed idea above ("Alternate form: Browser extension")
- Long-term: calendar-aware auto-focus detection, multi-user/team version
