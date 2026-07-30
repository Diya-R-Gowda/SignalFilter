2. **Signal Filter** — smarter notifications

The idea: You're not overwhelmed because you get too many notifications — you're overwhelmed because most of them don't matter right now. This tool learns what you're currently focused on and only interrupts you for things actually relevant to that, muting the rest.

Why it's hard: Your priorities change hour to hour, and "urgent" is relative to what you're working on. A message that's critical during a product launch is noise the rest of the week. The tool has to understand meaning, not just filter by keyword or sender — and do it fast enough to work in real time.

How you'd build it, roughly: Connect it to Slack, email, calendar. You tell it "I'm currently focused on X." An AI scores every incoming message against that focus and only pushes through the truly important stuff, learning from your thumbs up/down feedback.

Starting small: Start with just Slack + Gmail, and you manually type what you're focused on. Later, it figures out your focus automatically from your calendar and activity, essentially becoming your whole inbox.



2. **Signal Filter** — semantic notification triage

The problem: Notification fatigue isn't a volume problem, it's a relevance problem. "Do Not Disturb" and priority inboxes use rigid rules (sender, keyword) not actual meaning or your current state.

Why it's unsolved: Needs to understand your current task/goal, model what's actually urgent to that goal (not urgent in general), and adapt as your priorities shift hour to hour — while running fast enough to triage in real time across Slack/email/calendar.

Architecture:

FastAPI backend with connectors (Slack, Gmail, calendar APIs) pulling incoming messages
Python worker classifies each item against your declared "current focus" (a short text you set, updated throughout the day) using an LLM + lightweight embedding similarity for speed
TypeScript/React dashboard: single unified stream, ranked by relevance-to-current-focus, with a fast feedback loop (thumbs up/down retrains ranking)
Push only the few real interrupts to a native notification

MVP → long-term: MVP = single Slack workspace + Gmail, manual focus-text input. Long-term = auto-detects focus from calendar/activity, becomes a real inbox replacement.



**GAME PLAN**

Going with Signal Filter — semantic notification triage. It's the most broadly "in-demand" because notification overload hits literally everyone with a job (not a niche audience), there's no dominant winner yet (Superhuman/Sanebox solve inbox ranking but not cross-app, focus-aware triage), and it has an obvious path to a real product/business if you want to take it there later.

What you're building

A system where you tell it what you're focused on right now (in plain language), and it watches your Slack + email + calendar and only surfaces what's actually relevant to that focus — everything else gets queued into a low-priority digest instead of pinging you.

Architecture

Data layer

Connectors: Gmail API, Slack API (start with these two — biggest volume), Google Calendar API (for context: meetings = signal about what's "in focus")
FastAPI backend polls/webhooks these sources, normalizes everything into one Item schema: {source, sender, content, timestamp, thread_id}

Intelligence layer (Python)

User sets/updates a short "current focus" string throughout the day (e.g. "finishing Q3 pricing deck" / "debugging payment webhook")
Embed the focus text + embed each incoming item (sentence-transformers, local, cheap, fast — no LLM call needed for this part)
Cosine similarity gives a fast relevance score; only borderline/high-value cases (VIP senders, anything mentioning your name directly, calendar conflicts) get escalated to an LLM call for nuanced judgment
Feedback loop: user's 👍/👎 on triage decisions fine-tunes a lightweight classifier (logistic regression on embeddings — simple, no need for heavy ML infra) over time

Frontend (TypeScript/React)

Single unified stream: ranked list, top = most relevant to current focus
One-line "why this surfaced" explanation under each item (builds trust in the ranking)
Focus-switcher at the top (change your "current focus" in one click)
Digest view for everything filtered out — never silently discarded, just deprioritized

Delivery

Native OS notification only for the top-ranked handful; everything else lives in the app
Optional: Chrome extension (TS) to inject the same relevance score into native Gmail/Slack UI, so you don't need people to migrate off tools they already use — this is a big adoption unlock
Week-by-week plan (4 weeks to a real MVP)

Week 1 — Ingestion + schema

FastAPI project scaffold, Gmail + Slack OAuth, pull last 24h of messages into normalized Item schema, store in Postgres
Deliverable: a script that dumps unified JSON of your real inbox/Slack

Week 2 — Relevance engine

Add "current focus" input, generate embeddings (sentence-transformers, run locally — no API cost), score all items against focus
Deliverable: CLI or simple endpoint that returns items ranked by relevance for a given focus string

Week 3 — Frontend

React/TS unified stream UI, focus-switcher, 👍/👎 feedback buttons wired to backend
Deliverable: working local app you use yourself for a few real days

Week 4 — Feedback loop + polish

Store feedback, retrain lightweight classifier per user, add the "why surfaced" explanation (LLM call, cached), add digest view for filtered items
Deliverable: demo-able product with your own real usage data as proof it works

Beyond week 4 (if you want to go long-term): native notifications, calendar-aware auto-focus detection, browser extension injecting scores into Gmail/Slack directly, multi-user/team version, and eventually a "does this actually need my attention right now" score that factors in your calendar (busy vs free).

Want me to scaffold the actual repo structure (FastAPI backend + React/TS frontend boilerplate) so you can start coding Week 1 today?
