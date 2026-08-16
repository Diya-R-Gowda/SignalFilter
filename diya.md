# Signal Filter — Plans

A consolidated record of plans made for this project via Claude Code's plan mode — both a historical one that's long since been built and shipped, and the two most recent ones (approved, not yet built). Not a permanent architecture doc like `CONTRIBUTING.md` — this is specifically the plan-mode output, kept for reference.

---

## Plan: Week 2 — Gmail connector + FastAPI HTTP API + React dashboard *(historical — built and shipped)*

### Context

Week 1 delivered a fully working Slack → pipeline → Windows-notification loop, validated live. Per `CONTRIBUTING.md`'s Week 2 plan, the next milestone is: a second connector (Gmail) so the pipeline isn't Slack-only, and a first UI (React dashboard) so items and feedback don't require querying Postgres directly. This plan builds both, reusing the existing `process_item()` pipeline, `Item`/`FocusState`/`Feedback` models, and connector pattern established in Week 1 — no changes to the core two-stage ranking logic.

Confirmed current state (via exploration, at the time): no `main.py`/FastAPI app instance existed yet despite `fastapi`/`uvicorn` already in `requirements.txt`; no `frontend/` directory existed yet; no Google API libraries installed yet; Node v22.20.0 / npm 11.6.2 were available locally so Vite scaffolding would work directly.

### 1. Gmail connector

- Add `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib` to `backend/requirements.txt`.
- **User action required first** (like the Slack app in Week 1): create a Google Cloud project, enable the Gmail API, create OAuth 2.0 **Desktop app** credentials, download `credentials.json`.
- New file `backend/app/connectors/gmail_connector.py`:
  - First-run OAuth via `InstalledAppFlow.run_local_server()`, caching the refresh token to `backend/token.json` (gitignored, like `.env`).
  - Poll loop (30–60s) using `history.list` with a stored cursor, avoiding re-scanning the whole inbox each poll.
  - Normalize each new message into the same shape `process_item()` expects: `source="gmail"`, `sender` = From header, `content` = subject + snippet, `thread_id` = Gmail `threadId`, `source_timestamp` = `internalDate`.
  - Calls the existing `process_item()` from `pipeline.py` — no pipeline changes needed.
- New model `backend/app/models/sync_state.py`: a small generic `SyncState(key, value)` table to persist the Gmail `historyId` cursor across restarts, keyed so it can be reused for future connectors' cursors too.
- CLI: extend `backend/app/cli.py`'s `run` command with a `--source` flag (`slack` / `gmail` / `all`, default `all`), starting the relevant listener(s) as background threads.

### 2. FastAPI HTTP API

- New file `backend/app/main.py`: creates the `FastAPI()` app, adds `CORSMiddleware`.
- New file `backend/app/schemas.py`: `ItemOut`, `FocusOut`/`FocusIn`, `FeedbackIn`.
- Endpoints: `GET /items?source=&notified=&limit=`, `GET /focus`, `POST /focus`, `POST /items/{id}/feedback`.
- Run via `uvicorn app.main:app --reload --port 8000`.

### 3. React dashboard

- Scaffold `frontend/` with Vite + React + TS.
- Polls `GET /items` every few seconds and `GET /focus` on load.
- Two sections: Surfaced (`notified=true`) vs Filtered (`notified=false`).
- Focus switcher + 👍/👎 feedback buttons wired to the API.
- Plain CSS, kept small.

### Outcome

Built exactly as planned — this is why `CONTRIBUTING.md`'s status table shows the Gmail connector, FastAPI API, and React dashboard all `🟢 Done`, each with real live-testing behind them (a real test email correctly scored/filtered, API smoke-tested via `TestClient`, dashboard type-checks and builds cleanly). Everything since (feedback tuning, digest mode, connector health, attention budget, weak-signal escalation, calendar integration, and more) was built on top of this same foundation.

---

## Plan: Flow-state-aware dynamic strictness *(approved 2026-08-16, not yet built)*

### Context

The next unbuilt Week 3+ idea (`CONTRIBUTING.md`'s "Week 3+ idea: Flow-state-aware dynamic strictness" section). Calendar integration (shipped just before this) suppresses interrupts based on an *explicit* signal — a calendar event. This goes further with a *passive, inferred* signal: local idle-time + active-window tracking, no calendar or cloud involved, to guess whether Diya is in deep uninterrupted flow (raise the threshold temporarily) or already context-switching a lot (threshold can relax, since one more interrupt costs less right now).

Confirmed before proposing an approach: `pywin32`/`pygetwindow` are **not** currently in `backend/requirements.txt` — this would be a genuinely new dependency, or avoidable entirely (see below). No existing "activity tracking" code exists anywhere in the codebase.

### Recommended approach

**Detection — zero new dependencies.** Both signals this needs are available via plain `ctypes` calls into `user32.dll` (Python stdlib, no install needed) rather than pulling in `pywin32`:
- Idle time: `GetLastInputInfo` (returns the tick count of the last keyboard/mouse input; subtract from `GetTickCount()` for idle duration).
- Active window identity: `GetForegroundWindow()` + `GetWindowThreadProcessId()` to resolve the process name (e.g. `Code.exe`, `chrome.exe`) — **process name, not window title**, is the "same context" signal to track. Window titles change constantly even within one focused session (different files, browser tabs) and the idea's own privacy note flags that titles can contain sensitive content (doc names, URLs) — process name avoids ever needing to read or store that.
- This mirrors `calendar_connector.py`'s own "no new heavy dependency where a lighter stdlib path exists" instinct, just more so.

**Insertion point — same shape as every prior polling feature.** A new background thread (`backend/app/services/flow_state.py` or similar), started unconditionally in `cli.py` next to the digest and calendar threads, sampling on an interval (propose 60s). Writes a derived value to `SyncState` (e.g. `flow_state_strict_until`, mirroring `calendar_busy_until`'s exact shape) rather than any raw window/process data — nothing sensitive ever touches the database. `pipeline.py` reads this cached cursor at threshold-computation time — never a live `ctypes` call per incoming message.

**Composition with calendar's existing threshold raise — a real open question.** `pipeline.py`'s threshold logic already has one raise-to-9 rule from calendar integration. Recommend an explicit calendar signal (a real meeting) dominates the inferred flow-state signal rather than stacking (`if calendar_busy: use meeting threshold; elif flow_strict: use flow threshold; else: base`), not two independent `max()` calls that could interact unpredictably.

**The 9-10 attention-budget bypass must keep reading the raw `llm_score`**, exactly as already established for both calendar integration and the (deferred) per-sender trust design — flow-state suppression must never be able to swallow a genuinely urgent message.

**Calibration constants need a mandatory pre-ship validation pass**, matching attention budget's own precedent (its threshold looked fine in theory but falsely flagged 249/250 real burst items until validated against real data). Log real (idle, active-process) samples for a few real days *without* wiring the suppression into live notify decisions yet, then hand-check whether the derived "flow" periods actually line up with genuine focused stretches.

**Privacy constraint, carried from the idea's own writeup:** never persist or log raw window titles, and don't log the process name history either beyond what's needed for the current sample comparison — only the derived boolean/timestamp should ever land in the database.

### Open questions needing a dedicated audit pass

The specific N/M calibration constants, the exact "same process" granularity (should switching between two terminal windows count as the same context?), and whether this should apply globally or only during hours Diya would otherwise expect to be working — all better resolved via a live audit against real usage samples, matching how every other feature in this project got a dedicated audit pass with real data before a build prompt was written.

### Verification (once built)

- Confirm the `ctypes`-based idle/process detection actually works correctly on this machine (Windows 11) via a small standalone script before wiring it into a background thread.
- Confirm the background thread starts exactly once regardless of `--source` value, `SyncState` cursor updates on the expected interval, `pipeline.py`'s threshold composition (calendar overrides flow-state, never the reverse), and the 9-10 bypass still fires regardless of flow-state.

---

## Plan: GitHub-aware auto-reply with actionable notifications *(approved 2026-08-16, not yet built)*

### Context

The other unbuilt Week 3+ idea. When a Slack question is already answered by a recent commit, draft a reply from that commit and let Diya post it with one click from the notification itself, instead of just notifying and making her go answer it manually. The most ambitious unbuilt idea in the project — touches the notification layer, adds a second LLM call type, and needs a new Slack permission.

**Real technical verification done before proposing an approach** (the original idea write-up asserted `win11toast` supports action buttons via `on_click`, "feasible with no new dependency" — checked this against the actually-installed library rather than trusting that unverified claim):
- Confirmed in `backend/venv/Lib/site-packages/win11toast.py`: `toast()`/`notify()` do support a `buttons` list and an `on_click` callback that receives `e.arguments` — enough to distinguish which button fired.
- **Real constraint found, not previously documented anywhere:** `toast()` calls `asyncio.run(...)` when no event loop is already running, which **blocks the calling thread until the toast is dismissed or clicked**. An actionable toast makes this matter more than today's plain notifications: that thread has to stay alive for as long as it takes Diya to click something. **Open feasibility question, not yet verified:** does clicking a Windows toast from the Action Center after it's visually dismissed still fire the same callback, or does that only work while the toast is still on-screen and the originating thread is still blocked in `toast()`? This determines whether "click Yes 10 minutes later" actually works — needs a real, live test before the design commits to relying on it.

### Recommended approach

1. **Schema** — new nullable columns on `Item`: `drafted_reply` (text), `reply_target_channel` (may just need `source == "slack"` + the existing `thread_id`), `reply_posted_at` (nullable timestamp, makes acting on a click idempotent against a double-click or retry).

2. **Repo indexing** — reuse `embedding.py`'s existing `get_embedding()`, no new dependency. This repo's commit history is tiny, so a full persistent vector-index table is likely overkill — recommend a lightweight periodic in-memory rebuild (a new background thread, same shape as digest/calendar) pulling recent commit messages/diffs via `git log` on a slow interval.

3. **QA/reply-drafting** — a second, distinct LLM call (new function in `llm.py`, its own system prompt), not a repurposing of `score_item()`. Needs a **conservative confidence bar**: the idea's own write-up is explicit that a wrong/hallucinated auto-reply posted under Diya's name is worse than no reply at all, so default to "no confident answer" unless the match is genuinely strong, and keep drafted replies short and hedged.

4. **Delivery** — actionable toast with the drafted reply, `Yes`/`No` buttons. `on_click` looks up the item by ID (baked into the button's `arguments`), and on `Yes` posts via a new `chat.postMessage`-based function, then stamps `reply_posted_at`. **Needs the Slack bot's scope expanded to `chat:write`** — a new user action (add the scope at api.slack.com/apps, reinstall the app, new bot token back into `.env`), same class as the original Slack/Gmail credential setup. The drafting/detection half can be built and tested without this; only actual posting needs the new scope.

5. **Feeds the existing feedback signal** — Yes/No is functionally a 👍/👎, captured at the moment of interruption. Recommend writing to the same `Feedback` table via the existing upsert pattern in `main.py`'s `create_feedback`, not a parallel mechanism.

### Open questions needing a dedicated audit pass

- Does a delayed Action-Center click still fire `on_click`? Could reshape the whole delivery design if the answer is "no."
- Where to set the confidence threshold for "this counts as an answer" — needs real examples to calibrate against.
- Whether this applies only to Diya's own repos or also team repos she doesn't solely own (a permissions/trust question, not just technical).
- Repo indexing scope — recommend hardcoding to this one repo for a first build.

### Verification (once built)

- **First, before building anything else:** a small standalone script firing a toast with two buttons and an `on_click` handler, then deliberately clicking it from the Windows Action Center after its visible display duration — resolves the feasibility question above with a real test.
- Once schema + indexing + drafting are built: run against real historical Slack messages that do and don't have a genuine matching commit, confirm the confident/not-confident split lands where expected.
- Once the `chat:write` scope is live: a real end-to-end test posting into a real (test) Slack thread, confirming `reply_posted_at` gets stamped and a second click after that is a no-op.
