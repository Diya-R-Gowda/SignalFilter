# Signal Filter

Notification fatigue isn't a volume problem, it's a relevance problem. Signal Filter watches your Slack (and eventually Gmail) messages, compares each one against a short "what I'm focused on right now" text you set, and only fires a native notification for the messages that actually matter to that focus — everything else is logged but stays quiet.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full architecture and project plan. This README is the "how do I get it running" guide.

## How it works, briefly

Every incoming Slack message goes through two stages before a notification decision is made:

1. **Embedding filter** — a local `sentence-transformers` model (`all-MiniLM-L6-v2`) embeds the message and your focus text, and computes similarity. Cheap and fast; runs on every message. Anything below the threshold is filtered out immediately.
2. **LLM judgment** — messages that clear stage 1 go to a local LLM (`qwen2.5:3b-instruct`, run through Ollama — no API keys, no cost) which scores relevance + urgency 0–10. Scores above the cutoff trigger a native Windows toast notification.

Everything is logged to Postgres either way, so nothing is silently dropped — you can go look at what got filtered.

## Prerequisites

You'll need these installed before setup. All of them are free.

| Tool | Why | Get it |
|---|---|---|
| **Python 3.11+** | Runs the backend (built/tested on 3.14) | [python.org/downloads](https://www.python.org/downloads/) |
| **PostgreSQL** | Stores every triaged message + your feedback | [postgresql.org/download](https://www.postgresql.org/download/) |
| **Ollama** | Runs the LLM stage locally, free | [ollama.com/download](https://ollama.com/download) |
| **A Slack account** with permission to install apps to a workspace | The connector reads Slack messages | Use your own workspace, or make a free one at [slack.com/create](https://slack.com/create) if you don't want to install into a work workspace |

## Setup

All commands below assume Windows + PowerShell, run from the repo root, unless noted.

### 1. Install Postgres and set a password

If Postgres isn't installed yet, run the installer from the link above and set a password for the `postgres` user when prompted — remember it, you'll need it below.

If Postgres is already installed but you don't know the `postgres` password, reset it:

1. Open an **elevated** PowerShell (Win key → type `PowerShell` → right-click → *Run as administrator*).
2. Open the auth config: `notepad "C:\Program Files\PostgreSQL\<version>\data\pg_hba.conf"`
3. Change the `scram-sha-256` (or `md5`) entries for `local all all`, `host all all 127.0.0.1/32`, and `host all all ::1/128` to `trust`. Save.
4. `Restart-Service postgresql-x64-<version>`
5. `psql -U postgres -c "ALTER USER postgres WITH PASSWORD 'yournewpassword';"`
6. Revert step 3's changes back to `scram-sha-256`, save, then `Restart-Service postgresql-x64-<version>` again.

### 2. Create the database

```
psql -U postgres -h localhost -c "CREATE DATABASE signalfilter;"
```
(Enter the password from step 1 when prompted.)

### 3. Install Ollama and pull the model

Run the Ollama installer, then in a fresh terminal (so it picks up the updated PATH):

```
ollama pull qwen2.5:3b-instruct
```

This downloads ~2GB once. Confirm it worked: `ollama list` should show `qwen2.5:3b-instruct`.

### 4. Set up the Python backend

```
cd backend
python -m venv venv
./venv/Scripts/python.exe -m pip install --upgrade pip
./venv/Scripts/python.exe -m pip install -r requirements.txt
```

### 5. Configure environment variables

```
cd backend
copy .env.example .env
```

Open `.env` and fill in:
- `DATABASE_URL` — swap `YOUR_POSTGRES_PASSWORD` for the password from step 1.
- `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` — see step 6 below.

### 6. Create a Slack app (to get your two tokens)

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**. Name it (e.g. "Signal Filter"), pick your workspace.
2. **Socket Mode**: left sidebar → *Socket Mode* → toggle on. When prompted, generate an app-level token (any name, scope `connections:write`). Copy the token — starts with `xapp-` — this is `SLACK_APP_TOKEN`.
3. **Bot scopes**: *OAuth & Permissions* → *Scopes* → *Bot Token Scopes* → add:
   - `channels:history`, `channels:read`
   - `groups:history` (private channels)
   - `im:history`, `im:read` (DMs)
   - `mpim:history` (group DMs)
4. **Event Subscriptions**: *Event Subscriptions* → toggle on → under *Subscribe to bot events* add:
   - `message.channels`, `message.groups`, `message.im`, `message.mpim`
5. **Install the app**: *OAuth & Permissions* → *Install to Workspace* → allow. Copy the **Bot User OAuth Token** — starts with `xoxb-` — this is `SLACK_BOT_TOKEN`.
6. Paste both tokens into `backend/.env`.
7. In Slack, invite the bot to any channel you want triaged: type `/invite @Signal Filter` in that channel. DMs to the bot work without inviting.

### 7. Create the database tables

Tables are created automatically the first time you run the CLI (see below) — no separate migration step needed.

## Running it

From `backend/`, with everything above configured:

```
./venv/Scripts/python.exe -m app.cli focus "what you're focused on right now"
./venv/Scripts/python.exe -m app.cli run
```

`run` starts the Slack listener and prints a line for every message it processes (`filtered`, `scored`, or `NOTIFIED`). Messages that clear both stages trigger a real Windows notification.

Update your focus at any time from a second terminal — no restart needed, `run` re-reads the latest focus from the database on every message:

```
./venv/Scripts/python.exe -m app.cli focus "new focus text"
```

## Config reference

All tunables live in `backend/.env`:

| Variable | Default | What it does |
|---|---|---|
| `EMBEDDING_THRESHOLD` | `0.25` | Stage-1 cosine similarity cutoff (0–1). Lower = more messages reach the LLM stage. |
| `INTERRUPT_SCORE_THRESHOLD` | `6` | Stage-2 LLM score (0–10) needed to actually fire a notification. |
| `OLLAMA_MODEL` | `qwen2.5:3b-instruct` | Must already be pulled via `ollama pull`. |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Downloaded automatically from Hugging Face on first run. |

## Troubleshooting

- **`psql`/`ollama` "not recognized"** — the installer added it to PATH, but your current terminal was opened before that happened. Open a new terminal.
- **First embedding call is slow** — `all-MiniLM-L6-v2` downloads (~90MB) from Hugging Face the first time it's used, then is cached locally. Subsequent runs are fast.
- **Windows symlink warning from `huggingface_hub`** — harmless; caching still works, just uses more disk space. Ignore it, or enable Windows Developer Mode to silence it.
- **No notification fires** — check the CLI output: if a message is stuck at `filtered`, it didn't clear the stage-1 similarity threshold; if `scored` but not `NOTIFIED`, it cleared stage 1 but the LLM score was below `INTERRUPT_SCORE_THRESHOLD`. Both are visible per-message in the `items` table in Postgres.

## Project structure

```
backend/
  app/
    connectors/     # Slack (Socket Mode), Gmail (Week 2)
    models/         # SQLAlchemy models: Item, FocusState, Feedback
    services/       # embedding, llm, notify, focus
    pipeline.py     # ties the two-stage pipeline together
    cli.py          # `focus` / `run` commands
    config.py       # reads backend/.env
CONTRIBUTING.md      # full project plan and architecture
```
