# Signal Filter — backend

For full setup instructions (Postgres, Ollama, Slack app creation, env vars), see the [root README](../README.md).

## Quick reference (once everything is set up)

```
./venv/Scripts/python.exe -m app.cli focus "what you're focused on right now"
./venv/Scripts/python.exe -m app.cli run
```

## Layout

```
app/
  connectors/     # Slack (Socket Mode), Gmail (history.list polling)
  models/         # SQLAlchemy models: Item, FocusState, Feedback, SyncState
  services/       # embedding, llm, notify, focus, sync_state
  pipeline.py     # ties the two-stage pipeline together
  cli.py          # `focus` / `run [--source slack|gmail|all]` commands
  main.py         # FastAPI app: /items, /focus, /items/{id}/feedback
  schemas.py      # Pydantic request/response models for the API
  config.py       # reads backend/.env
```
