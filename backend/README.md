# Signal Filter — backend

Week 1 MVP: Slack → two-stage triage pipeline (MiniLM embedding filter → local Ollama LLM score) → native Windows notification, all driven from a CLI. See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for the full project plan.

## Prerequisites (one-time)

- **Postgres** running locally with a `signalfilter` database (already set up — see `.env`)
- **Ollama** running with the model pulled: `ollama pull qwen2.5:3b-instruct`
- **Python deps** installed into `backend/venv` (already done — `pip install -r requirements.txt`)

## Create a Slack app (needed once, to get your tokens)

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**. Name it (e.g. "Signal Filter"), pick your workspace.
2. **Socket Mode**: in the left sidebar, go to *Socket Mode* → toggle it on. You'll be asked to generate an app-level token — name it anything, scope `connections:write`. Copy the token (starts with `xapp-`) → this is `SLACK_APP_TOKEN`.
3. **Bot scopes**: go to *OAuth & Permissions* → *Scopes* → *Bot Token Scopes* → add:
   - `channels:history`, `channels:read`
   - `groups:history` (private channels)
   - `im:history`, `im:read` (DMs)
   - `mpim:history` (group DMs)
4. **Event Subscriptions**: go to *Event Subscriptions* → toggle on → under *Subscribe to bot events* add:
   - `message.channels`, `message.groups`, `message.im`, `message.mpim`
5. **Install the app**: go to *OAuth & Permissions* → *Install to Workspace* → allow. Copy the **Bot User OAuth Token** (starts with `xoxb-`) → this is `SLACK_BOT_TOKEN`.
6. Paste both tokens into `backend/.env`:
   ```
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   ```
7. In Slack itself, invite the bot to whichever channels you want triaged: `/invite @Signal Filter` in each channel. (DMs to the bot work without inviting.)

## Running it

From `backend/`, with the venv active:

```
./venv/Scripts/python.exe -m app.cli focus "what you're focused on right now"
./venv/Scripts/python.exe -m app.cli run
```

`run` starts the Slack listener. Every incoming message gets embedded, filtered against your focus, and — if it clears both stages — triggers a native Windows notification. Everything else is logged to Postgres (`items` table) regardless, so nothing is silently dropped.

You can update your focus at any time in a second terminal — `run` re-reads the latest focus from the DB on every message, no restart needed:

```
./venv/Scripts/python.exe -m app.cli focus "new focus text"
```

## Config

All tunables live in `backend/.env` (see `app/config.py` for defaults):

- `EMBEDDING_THRESHOLD` (default `0.25`) — stage-1 cosine similarity cutoff. Lower = more items reach the LLM stage.
- `INTERRUPT_SCORE_THRESHOLD` (default `6`) — stage-2 LLM score (0–10) needed to actually fire a notification.
- `OLLAMA_MODEL` (default `qwen2.5:3b-instruct`) — must already be pulled via `ollama pull`.
