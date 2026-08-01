# Things only you can do

Checklist of actions that need you specifically (credentials, manual testing) —
everything else is being built without waiting on these.

## 1. Gmail OAuth credentials (needed before the Gmail connector can run)

1. Go to https://console.cloud.google.com/ and create a new project (any name, e.g. "signal-filter").
2. In the project, go to **APIs & Services → Library**, search for "Gmail API", click it, click **Enable**.
3. Go to **APIs & Services → OAuth consent screen**:
   - User type: **External** (unless you have a Google Workspace org — then Internal is fine).
   - Fill in app name ("Signal Filter"), your email as support/dev contact.
   - Scopes: skip for now (default).
   - Test users: add your own Gmail address (`diyaprosubs@gmail.com` or whichever inbox you want to connect) — required while the app is in "Testing" status.
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**.
   - Name it anything (e.g. "signal-filter-desktop").
   - Click **Create**, then **Download JSON**.
5. Save the downloaded file as `backend/credentials.json` (exact filename, already gitignored — never commit it).
6. That's it — no need to run anything yet. The first time the Gmail connector starts (`python -m app.cli run --source gmail` or `--source all`), it will open a browser window asking you to log in and approve access. After you approve once, it caches a token in `backend/token.json` (also gitignored) and won't ask again.

**Which inbox to use for testing?** Your call — `diyaprosubs@gmail.com` works fine for a personal test, or use a throwaway Gmail account if you'd rather not connect your main inbox yet. Either way, add it as a test user in step 3.

---

*(This file is scratch/working-notes, not part of the permanent docs — safe to delete once everything below is done.)*
