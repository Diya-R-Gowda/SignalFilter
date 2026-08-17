# Things only you can do

Checklist of actions that need you specifically (credentials, manual testing) —
everything else is being built without waiting on these.

## 1. Gmail OAuth credentials (needed before the Gmail connector can run) — done, saved to `backend/credentials.json`

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

## 2. Try the dashboard in a browser

I type-checked and built the frontend and smoke-tested the API endpoints directly, but I can't open a browser — you're the first person to actually look at the dashboard rendered. Steps are in the root `README.md` under "Running it → API + dashboard". Quick version:

```
# terminal 2, from backend/
./venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000

# terminal 3
cd frontend
npm install
npm run dev
```

Then open `http://localhost:5173`. Let me know if anything looks broken or the layout needs work — it's intentionally minimal styling for now.

## 3. Test the Gmail connector live (after #1 above) — done, live traffic flowing for days

Once `backend/credentials.json` exists: `./venv/Scripts/python.exe -m app.cli run --source gmail` (or `--source all` to run Slack + Gmail together), approve the OAuth prompt in the browser that opens, then send yourself a test email and check it shows up in the CLI output / dashboard.

## 4. Decide: rewrite git history to purge old Slack tokens from info.md?

`info.md` had two real Slack tokens (a `SLACK_APP_TOKEN` and a Bot User OAuth Token) pasted into it in plaintext during early setup. Both were confirmed dead via Slack's `auth.test` (`"ok": false, "invalid_auth"` for each) and have now been redacted from the file's current content. They still exist in the file's git history though — introduced in `d05a43e` ("Created info.md, added game plan") and still present through `f222ab7` ("editied info.md"), i.e. every commit from the second one onward.

Two options, and this needs your explicit choice — not something to default on:

1. **Leave history as-is.** Reasonable since both tokens are already dead and the repo is private (confirmed via `gh repo view` — not publicly exposed).
2. **Rewrite history** with `git filter-repo` (or BFG Repo-Cleaner) to purge the token strings from every commit, then force-push to `origin/main`. This is disruptive: it rewrites every commit SHA from `d05a43e` onward and requires a force-push. Since this is a solo project there's likely no other clone to worry about invalidating, but it's still a one-way door worth deciding deliberately rather than doing by default.

Let me know which you'd prefer, or if you'd rather just leave it (given the tokens are confirmed dead already, there's no urgency either way).

## 5. Add the `chat:write` scope to the Slack app (needed for GitHub-aware auto-reply's Tier A to actually post)

Tier A is fully built and end-to-end tested (drafting, matching, actionable toast, feedback capture) — the one piece that needs you specifically is that the Slack bot is currently read-only. To let it post a confirmed reply:

1. Go to https://api.slack.com/apps and open the Signal Filter app.
2. **OAuth & Permissions** → under **Bot Token Scopes**, add `chat:write`.
3. Slack will prompt you to reinstall the app to the workspace — do that.
4. The Bot User OAuth Token may change on reinstall; if so, update `SLACK_BOT_TOKEN` in `backend/.env`.

Until this is done, clicking "Yes, post it" on a drafted-reply toast will fail with a clear `missing_scope` error in the console and `reply_posted_at` will stay unset — it won't silently pretend to have posted.

## 6. Restart the running `cli.py run` process to pick up Part 1 + Part 2 Tier A

Both features are live in the code but the currently-running background process was started before these changes and won't pick them up (new schema columns, new background threads, new pipeline behavior) until it's restarted. No rush — just flagging that a restart is needed before either feature actually takes effect in your real daily usage, rather than assuming it already has.

---

*(This file is scratch/working-notes, not part of the permanent docs — safe to delete once everything below is done.)*
