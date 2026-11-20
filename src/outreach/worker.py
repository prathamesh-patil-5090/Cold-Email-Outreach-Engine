"""Send planned touches, then write the tracker row."""

from __future__ import annotations

import random
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from outreach.calendar import in_send_window
from outreach.config import Settings
from outreach.mailer import SmtpMailer, build_message, new_message_id
from outreach.models import Lead
from outreach.plan import Plan, next_action_after
from outreach.state import SendRecord, SendState
from outreach.verify import _append

STATUS_AFTER = {
    "day0": "Sent - Day 0",
    "day4": "Sent - Day 4",
    "day8": "Sent - Day 8",
    "day14": "Sent - Day 14",
}


@dataclass
class SendSummary:
    sent: list[str]
    synced: list[str]
    failed: list[tuple[str, str]]
    unconfirmed: list[str]
    stopped_duplicates: list[str]
    deferred: list[str]


def apply_send(lead: Lead, record: SendRecord) -> None:
    sent_on = record.at[:10]
    status = STATUS_AFTER[record.touch]
    lead.set_field("assigned_sender", record.mailbox)
    lead.set_field("outreach_status", status)
    lead.set_field("last_action", sent_on)
    lead.set_field("next_action", next_action_after(_date(sent_on), record.touch))
    if record.touch == "day0" and record.message_id:
        lead.set_field("message_id", record.message_id)
    clause = f"{status} on {sent_on} from {record.mailbox}"
    if clause not in lead.text("notes"):
        lead.set_field("notes", _append(lead.text("notes"), clause))


def run_sends(
    leads: list[Lead],
    plan: Plan,
    *,
    repo,
    settings: Settings,
    state: SendState,
    mailer: SmtpMailer,
    confirm: bool,
    max_sends: int | None,
    ignore_window: bool,
    retry_unconfirmed: bool,
    now_fn,
    sleep,
    rng: random.Random | None = None,
) -> SendSummary:
    summary = SendSummary(sent=[], synced=[], failed=[], unconfirmed=[], stopped_duplicates=[], deferred=[])
    zone = ZoneInfo(settings.timezone)
    rng = rng or random.SystemRandom()
    by_id = {lead.lead_id: lead for lead in leads}

    if confirm:
        summary.synced = _sync_ledger(by_id, repo, state)
        summary.stopped_duplicates = _stop_duplicates(plan, by_id, repo)

    pending = []
    for job in plan.sends:
        existing = state.get(job.lead_id, job.touch)
        if existing and existing.smtp_ok:
            continue
        if existing and not existing.smtp_ok and not retry_unconfirmed:
            summary.unconfirmed.append(job.lead_id)
            continue
        if existing and not existing.smtp_ok and retry_unconfirmed and confirm:
            state.remove(job.lead_id, job.touch)
            state.save()
        pending.append(job)

    if not confirm:
        return summary

    phase = settings.phase_for(now_fn().astimezone(zone).date())
    next_eligible: dict[str, datetime] = {}
    sent_count = 0
    while pending and (max_sends is None or sent_count < max_sends):
        now = now_fn().astimezone(zone)
        if not ignore_window and not in_send_window(now, settings.business_hours.start, settings.business_hours.end):
            summary.deferred.extend(job.lead_id for job in pending)
            break
        ready_job = None
        soonest: datetime | None = None
        for job in pending:
            ready_at = _ready_at(state, job.mailbox, now, phase.hourly_per_mailbox, next_eligible)
            if ready_at <= now:
                ready_job = job
                break
            if soonest is None or ready_at < soonest:
                soonest = ready_at
        if ready_job is None:
            if soonest is None:
                break
            wait = (soonest - now).total_seconds()
            if not ignore_window:
                window_end = now.replace(
                    hour=settings.business_hours.end.hour,
                    minute=settings.business_hours.end.minute,
                    second=0,
                    microsecond=0,
                )
                if soonest >= window_end:
                    summary.deferred.extend(job.lead_id for job in pending)
                    break
            sleep(max(0, wait))
            if now_fn().astimezone(zone) <= now:
                summary.deferred.extend(job.lead_id for job in pending)
                break
            continue

        job = ready_job
        pending.remove(job)
        mailbox = settings.mailbox_by_email(job.mailbox)
        lead = by_id.get(job.lead_id)
        if mailbox is None or lead is None:
            summary.failed.append((job.lead_id, "mailbox or lead disappeared"))
            continue
        message_id = new_message_id(mailbox.domain)
        parent = job.parent_message_id if job.touch != "day0" else ""
        record = SendRecord(
            lead_id=job.lead_id,
            touch=job.touch,
            mailbox=mailbox.email,
            message_id=message_id if job.touch == "day0" else parent,
            parent_message_id=parent,
            to_email=job.to_email,
            subject=job.subject,
            at=now.isoformat(timespec="seconds"),
            smtp_ok=False,
            sheet_synced=False,
        )
        # Day 0 stores the id we generate. Follow-ups keep the original id in the sheet.
        if job.touch == "day0":
            record.message_id = message_id
        state.upsert(record)
        state.save()
        message = build_message(
            mailbox=mailbox,
            reply_to=settings.reply_to,
            to_email=job.to_email,
            subject=job.subject,
            body=job.body,
            message_id=message_id,
            parent_message_id=parent,
        )
        try:
            mailer.send(mailbox, message)
        except smtplib.SMTPRecipientsRefused as exc:
            state.remove(job.lead_id, job.touch)
            state.save()
            lead.set_field("outreach_status", "Bounced")
            lead.set_field("notes", _append(lead.text("notes"), f"Bounced on {now.date().isoformat()}: {exc}"))
            repo.save(lead)
            summary.failed.append((job.lead_id, "recipient refused"))
            continue
        except smtplib.SMTPAuthenticationError as exc:
            state.remove(job.lead_id, job.touch)
            state.save()
            summary.failed.append((job.lead_id, f"auth failed for {mailbox.email}: {exc.smtp_code}"))
            pending = [item for item in pending if item.mailbox.casefold() != mailbox.email.casefold()]
            continue
        except (smtplib.SMTPException, OSError) as exc:
            state.remove(job.lead_id, job.touch)
            state.save()
            summary.failed.append((job.lead_id, str(exc)))
            continue
        except Exception as exc:
            state.remove(job.lead_id, job.touch)
            state.save()
            summary.failed.append((job.lead_id, str(exc)))
            continue

        record.smtp_ok = True
        state.upsert(record)
        state.save()
        apply_send(lead, record)
        try:
            repo.save(lead)
        except Exception as exc:  # sheet sync is retried on the next run
            summary.failed.append((job.lead_id, f"sent but sheet update failed: {exc}"))
            sent_count += 1
            summary.sent.append(job.lead_id)
            continue
        record.sheet_synced = True
        state.upsert(record)
        state.save()
        summary.sent.append(job.lead_id)
        sent_count += 1
        gap = rng.randint(phase.jitter_min_seconds, phase.jitter_max_seconds)
        next_eligible[mailbox.email.casefold()] = now + timedelta(seconds=gap)
    return summary


def _sync_ledger(by_id: dict[str, Lead], repo, state: SendState) -> list[str]:
    synced: list[str] = []
    changed = False
    for record in list(state.records):
        if not record.smtp_ok or record.sheet_synced:
            continue
        lead = by_id.get(record.lead_id)
        if lead is None:
            continue
        apply_send(lead, record)
        repo.save(lead)
        record.sheet_synced = True
        state.upsert(record)
        synced.append(record.lead_id)
        changed = True
    if changed:
        state.save()
    return synced


def _stop_duplicates(plan: Plan, by_id: dict[str, Lead], repo) -> list[str]:
    stopped: list[str] = []
    for skip in plan.skips:
        if not skip.reason.startswith("duplicate of "):
            continue
        lead = by_id.get(skip.lead_id)
        if lead is None or lead.status_key not in {"queued", "not sent", "ready", ""}:
            continue
        lead.set_field("outreach_status", "Stopped")
        if skip.reason not in lead.text("notes"):
            lead.set_field("notes", _append(lead.text("notes"), skip.reason))
        repo.save(lead)
        stopped.append(lead.lead_id)
    return stopped


def _ready_at(state: SendState, mailbox: str, now: datetime, hourly_cap: int, next_eligible: dict[str, datetime]) -> datetime:
    ready = next_eligible.get(mailbox.casefold(), now)
    stamps = _recent_stamps(state, mailbox, now)
    if len(stamps) >= hourly_cap:
        release = stamps[-hourly_cap] + timedelta(hours=1)
        if release > ready:
            ready = release
    return ready


def _recent_stamps(state: SendState, mailbox: str, now: datetime) -> list[datetime]:
    wanted = mailbox.casefold()
    stamps: list[datetime] = []
    for record in state.records:
        if not record.smtp_ok or record.mailbox.casefold() != wanted:
            continue
        stamp = datetime.fromisoformat(record.at)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=now.tzinfo)
        if now - timedelta(hours=1) <= stamp <= now:
            stamps.append(stamp)
    stamps.sort()
    return stamps


def _date(value: str):
    from datetime import date

    return date.fromisoformat(value)
