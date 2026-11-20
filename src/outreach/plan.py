"""Choose which due touches fit today's per-mailbox cap.

Follow-ups go before new Day 0 sends. A mailbox locked on Day 0 stays the
sender for Day 4, Day 8, and Day 14. Blank senders are filled from the
mailbox with the most remaining capacity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from outreach.calendar import add_business_days
from outreach.columns import DAY0_STATUSES, STOP_PREFIXES, VALID_MARK
from outreach.config import RampPhase
from outreach.models import Lead
from outreach.templates import followup_subject, looks_like_mail_merge_risk

# After this status, send this touch, then wait this many business days.
FOLLOWUPS: tuple[tuple[str, str, int], ...] = (
    ("sent - day 0", "day4", 4),
    ("sent - day 4", "day8", 4),
    ("sent - day 8", "day14", 6),
)
BODY_KEY = {"day0": "day0", "day4": "day4", "day8": "day8", "day14": "day14"}
NEXT_WAIT = {"day0": 4, "day4": 4, "day8": 6, "day14": None}


@dataclass(frozen=True)
class PlannedSend:
    lead_id: str
    row_number: int
    touch: str
    mailbox: str
    to_email: str
    subject: str
    body: str
    parent_message_id: str


@dataclass(frozen=True)
class Skip:
    lead_id: str
    reason: str


@dataclass
class Plan:
    sends: list[PlannedSend]
    skips: list[Skip]
    held_for_cap: list[str]


def plan_sends(
    leads: list[Lead],
    *,
    today: date,
    mailboxes: list[str],
    sent_today: dict[str, int],
    phase: RampPhase,
    reply_to: str,
) -> Plan:
    claimed = _claimed_emails(leads)
    load = {box.casefold(): sent_today.get(box.casefold(), 0) for box in mailboxes}
    order = [box.casefold() for box in mailboxes]
    display = {box.casefold(): box for box in mailboxes}
    sends: list[PlannedSend] = []
    skips: list[Skip] = []
    held: list[str] = []

    candidates: list[tuple[int, int, Lead, str]] = []
    for lead in leads:
        decision = _classify(lead, today, claimed, reply_to)
        if decision is None:
            continue
        if isinstance(decision, Skip):
            skips.append(decision)
            continue
        priority, touch = decision
        candidates.append((priority, lead.row_number, lead, touch))

    for _priority, _row, lead, touch in sorted(candidates, key=lambda item: (item[0], item[1])):
        mailbox, problem = _mailbox_for(lead, touch, load, order, display, phase.daily_per_mailbox)
        if problem == "unknown":
            skips.append(Skip(lead.lead_id, "assigned sender is not an outreach mailbox"))
            continue
        if mailbox is None:
            held.append(lead.lead_id)
            continue
        parent = lead.text("message_id") if touch != "day0" else ""
        subject = lead.text("subject") if touch == "day0" else followup_subject(lead.text("subject"))
        body = lead.text(BODY_KEY[touch])
        risk = looks_like_mail_merge_risk(body)
        if risk:
            skips.append(Skip(lead.lead_id, risk))
            continue
        if not subject or not body:
            skips.append(Skip(lead.lead_id, f"missing {touch} copy"))
            continue
        sends.append(
            PlannedSend(
                lead_id=lead.lead_id,
                row_number=lead.row_number,
                touch=touch,
                mailbox=mailbox,
                to_email=lead.text("email"),
                subject=subject,
                body=body,
                parent_message_id=parent,
            )
        )
        load[mailbox.casefold()] = load.get(mailbox.casefold(), 0) + 1
    return Plan(sends=sends, skips=skips, held_for_cap=held)


def next_action_after(today: date, touch: str) -> str:
    wait = NEXT_WAIT[touch]
    if wait is None:
        return ""
    return add_business_days(today, wait).isoformat()


def _classify(
    lead: Lead,
    today: date,
    claimed: dict[str, str],
    reply_to: str,
) -> tuple[int, str] | Skip | None:
    status = lead.status_key
    if any(status.startswith(prefix) for prefix in STOP_PREFIXES):
        return None
    if status.startswith("sent - day 14"):
        return None

    sender = lead.text("assigned_sender")
    if sender and sender.casefold() == reply_to.casefold() and status in DAY0_STATUSES:
        return Skip(lead.lead_id, "assigned to the reply inbox")

    if status in DAY0_STATUSES or (status == "" and lead.research_done and lead.text("email")):
        return _classify_day0(lead, claimed)

    for current, touch, wait in FOLLOWUPS:
        if status != current:
            continue
        due = _due_on(lead, today, wait)
        if due is None:
            return Skip(lead.lead_id, "no schedule for follow-up")
        if due > today:
            return None
        if not sender:
            return Skip(lead.lead_id, "follow-up has no assigned sender")
        return (0 if touch == "day4" else 1 if touch == "day8" else 2, touch)
    return None


def _classify_day0(lead: Lead, claimed: dict[str, str]) -> tuple[int, str] | Skip:
    if not lead.research_done:
        return Skip(lead.lead_id, "research status is not Done")
    if not lead.text("day0") or not lead.text("subject"):
        return Skip(lead.lead_id, "waiting on assembled email")
    email = lead.text("email").casefold()
    if not email:
        return Skip(lead.lead_id, "waiting on contact email")
    owner = claimed.get(email)
    if owner and owner != lead.lead_id:
        return Skip(lead.lead_id, f"duplicate of {owner}")
    if VALID_MARK not in lead.text("notes"):
        return Skip(lead.lead_id, "waiting on email verification")
    return (3, "day0")


def _due_on(lead: Lead, today: date, wait: int) -> date | None:
    raw = lead.text("next_action")
    if raw:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    last = lead.text("last_action")
    if not last:
        return None
    try:
        return add_business_days(date.fromisoformat(last[:10]), wait)
    except ValueError:
        return None


def _claimed_emails(leads: list[Lead]) -> dict[str, str]:
    """First row that owns an address. Later Day 0 rows with the same address are duplicates."""
    claimed: dict[str, str] = {}
    ordered = sorted(leads, key=lambda lead: lead.row_number)
    for lead in ordered:
        email = lead.text("email").casefold()
        if not email or email in claimed:
            continue
        status = lead.status_key
        if status.startswith("sent") or any(status.startswith(prefix) for prefix in STOP_PREFIXES):
            claimed[email] = lead.lead_id
    for lead in ordered:
        email = lead.text("email").casefold()
        if email and email not in claimed and (lead.status_key in DAY0_STATUSES or lead.status_key == ""):
            claimed[email] = lead.lead_id
    return claimed


def _mailbox_for(
    lead: Lead,
    touch: str,
    load: dict[str, int],
    order: list[str],
    display: dict[str, str],
    daily_cap: int,
) -> tuple[str | None, str | None]:
    assigned = lead.text("assigned_sender").casefold()
    if touch != "day0" or assigned:
        if assigned not in display:
            return None, "unknown"
        if load.get(assigned, 0) >= daily_cap:
            return None, "cap"
        return display[assigned], None
    available = [box for box in order if load.get(box, 0) < daily_cap]
    if not available:
        return None, "cap"
    chosen = min(available, key=lambda box: (load.get(box, 0), order.index(box)))
    return display[chosen], None
