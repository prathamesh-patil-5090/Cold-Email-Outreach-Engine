"""Command line for verify, assemble, and send."""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from outreach.assemble import assemble_leads
from outreach.calendar import in_send_window, today_in
from outreach.columns import (
    ASSEMBLE_COLUMNS,
    COLUMNS,
    SEND_COLUMNS,
    VERIFY_COLUMNS,
    missing_headers,
)
from outreach.config import ConfigError, load_settings
from outreach.models import SheetData
from outreach.plan import plan_sends
from outreach.sheets import GoogleSheetRepository
from outreach.state import SendState, sent_today_by_mailbox
from outreach.verify import default_resolver, load_disposable_domains, verify_leads
from outreach.worker import run_sends

WAITING = (
    'Outreach Tracker has no "Lead ID" header yet, so there is nothing to do.\n'
    "Nothing was changed. When the Grok bot writes the headers and new leads, run this again.\n"
    "Print the bot prompt with: outreach prompt"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="outreach", description="Outreach Tracker verify, assemble, and send.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show whether the sheet is ready and how many leads are queued")
    sub.add_parser("prompt", help="Print the 5-lead Grok discovery prompt")
    sub.add_parser("verify", help="MX-check queued emails and record the result in Notes")
    sub.add_parser("assemble", help="Fill subject and the four emails from research fields")

    send = sub.add_parser("send", help="Send due touches. Dry-run unless --confirm is set")
    _send_flags(send)
    run = sub.add_parser("run", help="Verify, assemble, then send. Dry-run unless --confirm is set")
    _send_flags(run)

    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc)
        return 2

    if args.command == "prompt":
        today = today_in(ZoneInfo(settings.timezone))
        text = (settings.root / "prompts" / "grok_discovery.txt").read_text()
        print(text.replace("{{today}}", f"{today.strftime('%b')} {today.day}, {today.year}"))
        return 0

    try:
        repo = GoogleSheetRepository(settings)
        data = repo.load()
    except ConfigError as exc:
        print(exc)
        return 2

    if args.command == "status":
        print(_status(data))
        return 0
    if args.command == "verify":
        return _verify(data, repo, settings)
    if args.command == "assemble":
        return _assemble(data, repo)
    if args.command == "send":
        return _send(data, repo, settings, args)
    if args.command == "run" and not data.ready:
        print(WAITING)
        return 0
    if args.command == "run":
        if _verify(data, repo, settings) != 0:
            return 2
        if _assemble(data, repo) != 0:
            return 2
        return _send(data, repo, settings, args)
    return 2


def _send_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--confirm", action="store_true", help="Actually send. Without this, print the plan only")
    parser.add_argument("--once", action="store_true", help="Send at most one email")
    parser.add_argument("--max-sends", type=int, default=None)
    parser.add_argument("--ignore-window", action="store_true", help="Allow sends outside 09:30–17:30 IST weekdays")
    parser.add_argument("--retry-unconfirmed", action="store_true", help="Retry a touch whose SMTP result was never confirmed")


def _verify(data: SheetData, repo, settings) -> int:
    if not _guard(data, VERIFY_COLUMNS):
        return 0
    summary = verify_leads(
        data.leads,
        disposable=load_disposable_domains(settings.root / "config" / "disposable_domains.txt"),
        resolver=default_resolver(),
    )
    for lead in data.leads:
        if lead.dirty:
            repo.save(lead)
    print(f"Checked {len(summary.checked)}.")
    print(f"Valid {len(summary.valid)}: {', '.join(summary.valid) or '-'}")
    print(f"Invalid {len(summary.invalid)}: {', '.join(summary.invalid) or '-'}")
    if summary.retryable:
        print("DNS retry later:")
        for lead_id, detail in summary.retryable:
            print(f"  {lead_id}: {detail}")
    if summary.waiting:
        print(f"{summary.waiting} queued row(s) have no contact email yet. Left untouched.")
    if not summary.checked and not summary.waiting:
        print("No queued emails are waiting for a check. Existing sent rows were left alone.")
    return 0


def _assemble(data: SheetData, repo) -> int:
    if not _guard(data, ASSEMBLE_COLUMNS):
        return 0
    summary = assemble_leads(data.leads)
    for lead in data.leads:
        if lead.dirty:
            repo.save(lead)
    print(f"Assembled {len(summary.assembled)}: {', '.join(summary.assembled) or '-'}")
    print(f"Already had copy: {len(summary.already)}")
    if summary.waiting:
        print("Waiting on the Grok bot:")
        for lead_id, reason in summary.waiting:
            print(f"  {lead_id}: {reason}")
    elif not summary.assembled:
        print("No blank rows are ready to assemble.")
    return 0


def _send(data: SheetData, repo, settings, args) -> int:
    if not _guard(data, SEND_COLUMNS):
        return 0
    zone = ZoneInfo(settings.timezone)
    now = datetime.now(zone)
    today = now.date()
    phase = settings.phase_for(today)
    state = SendState.load(settings.root / "data" / "send_state.json")
    plan = plan_sends(
        data.leads,
        today=today,
        mailboxes=[box.email for box in settings.mailboxes],
        sent_today=sent_today_by_mailbox(data.leads, state, today.isoformat()),
        phase=phase,
        reply_to=settings.reply_to,
    )
    window = in_send_window(now, settings.business_hours.start, settings.business_hours.end)
    print(_format_plan(plan, phase=phase, today=today, window_open=window))
    if not args.confirm:
        print("Dry run. Re-run with --confirm to send during the window.")
        return 0
    if not window and not args.ignore_window:
        print("Outside the send window (Mon–Fri 09:30–17:30 Asia/Kolkata). Nothing was sent.")
        return 0
    if plan.sends:
        missing = []
        needed = {job.mailbox.casefold() for job in plan.sends}
        for box in settings.mailboxes:
            if box.email.casefold() in needed and not os.environ.get(box.password_env, "").strip():
                missing.append(f"{box.password_env} ({box.email})")
        if missing:
            print("Missing Zoho app passwords:")
            for item in missing:
                print(f"  {item}")
            return 2
    max_sends = 1 if args.once else args.max_sends
    from outreach.mailer import SmtpMailer

    summary = run_sends(
        data.leads,
        plan,
        repo=repo,
        settings=settings,
        state=state,
        mailer=SmtpMailer(settings),
        confirm=True,
        max_sends=max_sends,
        ignore_window=args.ignore_window,
        retry_unconfirmed=args.retry_unconfirmed,
        now_fn=lambda: datetime.now(zone),
        sleep=time.sleep,
    )
    print(f"Sent {len(summary.sent)}: {', '.join(summary.sent) or '-'}")
    if summary.synced:
        print(f"Sheet sync repaired: {', '.join(summary.synced)}")
    if summary.stopped_duplicates:
        print(f"Stopped duplicates: {', '.join(summary.stopped_duplicates)}")
    if summary.unconfirmed:
        print(
            "Unconfirmed earlier attempts, left unsent: "
            + ", ".join(summary.unconfirmed)
            + ". Check the Zoho Sent folder, then retry with --retry-unconfirmed if they were not sent."
        )
    for lead_id, detail in summary.failed:
        print(f"Failed {lead_id}: {detail}")
    if summary.deferred:
        print(f"Deferred {len(summary.deferred)} because the window or hourly cap closed.")
    return 0


def _guard(data: SheetData, keys: tuple[str, ...]) -> bool:
    if not data.ready:
        print(WAITING)
        return False
    missing = missing_headers(data.present, keys)
    if missing:
        print("Outreach Tracker is missing columns this step needs:")
        for name in missing:
            print(f"  - {name}")
        print("Nothing was changed. The Grok bot can add these headers before the next run.")
        return False
    return True


def _status(data: SheetData) -> str:
    if not data.ready:
        expected = "\n".join(f"  - {name}" for name in COLUMNS.values())
        return WAITING + "\nExpected headers:\n" + expected
    counts: dict[str, int] = {}
    for lead in data.leads:
        label = lead.status or "(blank)"
        counts[label] = counts.get(label, 0) + 1
    lines = [f"Header row: {data.header_row}", f"Leads: {len(data.leads)}"]
    if not data.leads:
        lines.append("No lead rows yet. The Grok bot has not appended prospects.")
    for label, count in sorted(counts.items()):
        lines.append(f"  {label}: {count}")
    if data.absent:
        lines.append("Headers not on the sheet yet:")
        lines.extend(f"  - {name}" for name in data.absent)
    else:
        lines.append("All A–T headers are present.")
    return "\n".join(lines)


def _format_plan(plan, *, phase, today, window_open: bool) -> str:
    lines = [
        f"{today.isoformat()}  {phase.name}  "
        f"{phase.daily_per_mailbox}/mailbox/day, {phase.hourly_per_mailbox}/hour, "
        f"jitter {phase.jitter_min_seconds // 60}–{phase.jitter_max_seconds // 60} min. "
        f"Window open: {'yes' if window_open else 'no'}.",
        f"Ready to send: {len(plan.sends)}",
    ]
    for job in plan.sends:
        lines.append(f"  {job.lead_id}  {job.touch}  {job.mailbox}  {job.to_email}")
    if plan.skips:
        lines.append("Waiting or skipped:")
        for skip in plan.skips[:40]:
            lines.append(f"  {skip.lead_id}: {skip.reason}")
        if len(plan.skips) > 40:
            lines.append(f"  … {len(plan.skips) - 40} more")
    if plan.held_for_cap:
        lines.append("Over today's mailbox cap: " + ", ".join(plan.held_for_cap))
    return "\n".join(lines)
