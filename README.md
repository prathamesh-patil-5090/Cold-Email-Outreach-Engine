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

Create a Google service account, put the JSON path in `GOOGLE_SERVICE_ACCOUNT_FILE`, and share **Client Leads status** with that account as Editor. Create one Zoho app password per outreach mailbox and fill the seven `ZOHO_APP_PASSWORD_...` values. The reply inbox does not need one.

`config/settings.yaml` points at the live spreadsheet. `SMTP_HOST` defaults to `smtp.zoho.in`.

## Commands

```bash
outreach prompt          # discovery prompt for the Grok bot, with today's date filled in
outreach status          # headers, lead count, and anything still missing
outreach verify          # MX-check queued rows
outreach assemble        # fill L–P where I, J, and K are present and the emails are blank
outreach send            # dry-run of today's queue
outreach send --confirm  # send during the window, then wait out the per-mailbox jitter
outreach run             # verify, assemble, and print the send plan
outreach run --confirm   # verify, assemble, and send
```

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
