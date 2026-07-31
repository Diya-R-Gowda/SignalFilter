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
  connectors/     # Slack (Socket Mode), Gmail (Week 2)
  models/         # SQLAlchemy models: Item, FocusState, Feedback
  services/       # embedding, llm, notify, focus
  pipeline.py     # ties the two-stage pipeline together
  cli.py          # `focus` / `run` commands
  config.py       # reads backend/.env
```
