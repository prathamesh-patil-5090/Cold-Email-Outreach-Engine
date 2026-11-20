# Outreach engine

Python side of the Client Leads pipeline. The Grok bot finds prospects and writes the research columns. This package checks the email, fills the four-touch sequence, and sends it through the seven Zoho mailboxes.

The sheet is allowed to be empty. If the `Lead ID` header or a later column is not there yet, the commands stop and change nothing. When the bot appends `LEAD-057` and the rest, the same commands pick those rows up.

`prathamesh@pratz.is-a.dev` is the reply inbox. It is not used for cold sends.

## What each side writes

| Columns | Who |
| --- | --- |
| A–K and T (`Lead ID` through `Short Workflow Topic`, plus `Notes`) | Grok bot |
| L–P (`Subject Line` and the four emails) | `outreach assemble` |
| G and T, email check note | `outreach verify` |
| C, D, Q, R, S after a send | `outreach send --confirm` |

Verification uses [python-email-validator](https://github.com/JoshData/python-email-validator) for syntax and MX, plus `config/disposable_domains.txt`. There is no separate verified column. A pass is stored as `Email check: VALID` in Notes. A hard failure sets Outreach Status to `Invalid Email`. Rows with no email yet are left alone.

Day 0 through Day 14 are the same copy as `LEAD-002` onward. Subject is `Question about {Company}'s {topic}`. Follow-ups go out after 4, then 4, then 6 business days, which is the gap already on the tracker (19 Nov → 25 Nov, 20 Nov → 26 Nov). Weekends are skipped. Sends only run Monday–Friday, 09:30–17:30 Asia/Kolkata.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
```

### Google service account (`service-account.json`)

Your Google login can open the sheet in the browser. The Python worker cannot use that login. It needs a **service account** JSON key, then the sheet must be shared with that robot email as Editor.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or pick a project.
2. **APIs & Services → Library** → enable **Google Sheets API**.
3. **APIs & Services → Credentials → Create credentials → Service account**.
   - Name it something like `outreach-engine`.
   - Skip optional roles. Click **Done**.
4. Open the new service account → **Keys → Add key → Create new key → JSON**.
5. Download the file and move it into this repo as `service-account.json` (already in `.gitignore`):

```bash
cp ~/Downloads/your-project-xxxxx.json ./service-account.json
```

6. Open the JSON and copy `client_email` (looks like `outreach-engine@your-project.iam.gserviceaccount.com`).
7. In the Google Sheet, click **Share**, paste that email, set role to **Editor**, uncheck “Notify people”, then Share.
8. In `.env`:

```bash
GOOGLE_SERVICE_ACCOUNT_FILE=./service-account.json
```

`config/settings.yaml` already points at the Test spreadsheet (`1E-A_q42Jjd3S57UliOArAwABhfDOxJJBoJP3SxaNfrc`). Override with `SPREADSHEET_ID=` in `.env` if you switch sheets later. `SMTP_HOST` defaults to `smtp.zoho.in`.

### Postgres mirror

Set `DATABASE_URL` in `.env` (Neon / any Postgres). Then:

```bash
outreach sync-db
```

That creates `leads` + `send_events` (see `sql/schema.sql`) and upserts every current sheet row. `verify`, `assemble`, and a confirmed `send` also sync when `DATABASE_URL` is set.

### Zoho app passwords (Playwright)

All seven outreach mailboxes share one Zoho web login password. Put that in `.env` as `ZOHO_LOGIN_PASSWORD`, then:

```bash
pip install -e ".[zoho]"
playwright install chromium
python scripts/fetch_zoho_app_passwords.py
```

A Chromium window opens for each mailbox, signs in at `accounts.zoho.in`, opens [Security → App Passwords](https://accounts.zoho.in/home#security/app_password), clicks **+ Generate New Password**, and writes the result into the matching `ZOHO_APP_PASSWORD_...` line in `.env`. If Zoho asks for MFA/CAPTCHA, complete it in the window (default wait 120s).

```bash
python scripts/fetch_zoho_app_passwords.py --only p.patil@pratz.is-a.dev
python scripts/fetch_zoho_app_passwords.py --dry-run
```

The reply inbox does not need an app password.

## Commands

```bash
outreach prompt          # discovery prompt for the Grok bot, with today's date filled in
outreach status          # headers, lead count, and anything still missing
outreach verify          # MX-check queued rows
outreach assemble        # fill L–P with a rotating template variant + copy QA
outreach check           # re-QA assembled copy; mark bad rows Needs Review
outreach sync-db         # upsert sheet rows into Postgres
outreach send            # dry-run of today's queue
outreach send --confirm  # send during the window, then wait out the per-mailbox jitter
outreach run             # verify, assemble, check, then print the send plan
outreach run --confirm   # verify, assemble, check, and send
```

`assemble` picks stable subject / Day 0 / Day 4 / Day 8 / Day 14 variants from the Lead ID (so the same row does not reshuffle). Copy QA rejects buzzwords, broken topic phrases, missing company/name joins, links/HTML, and overlong Day 0 bodies. Failures stay off the send queue as `Needs Review`.

`--once` sends a single email. `--max-sends N` caps a run. `--ignore-window` is only for a deliberate send outside business hours.

A send is written to `data/send_state.json` before SMTP returns is treated as unconfirmed and is not retried automatically. If the Sent folder shows it did not go out, run `outreach send --confirm --retry-unconfirmed`.

## Caps

| Phase | Per mailbox / day | Per mailbox / hour | Gap between sends |
| --- | --- | --- | --- |
| Days 1–7 from 2026-11-19 | 5 | 2 | 25–45 min |
| Days 8–14 | 10 | 3 | 15–25 min |
| Day 15+ | 16 | 4 | 8–18 min |

The daily count includes rows already marked sent today, so a second run does not add another 35 on top of a batch that already went out.

## Tests

```bash
pytest
```
