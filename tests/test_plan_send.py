from datetime import date, datetime
from zoneinfo import ZoneInfo

import smtplib

from outreach.columns import VALID_MARK
from outreach.config import RampPhase, load_settings
from outreach.mailer import build_message, rfc_message_id
from outreach.plan import plan_sends
from outreach.state import SendRecord, SendState
from outreach.worker import apply_send, run_sends

from tests.test_sheet_grid import lead


MAILBOXES = [
    "p.patil@pratz.is-a.dev",
    "prathamesh.p@pratz.is-a.dev",
]
PHASE = RampPhase("week1", 7, 5, 2, 0, 0)
TODAY = date(2026, 11, 23)


def _queued(lead_id, email, row, sender=""):
    return lead(
        row=row,
        lead_id=lead_id,
        research_status="Done",
        outreach_status="Queued",
        assigned_sender=sender,
        company="Acme Pvt. Ltd.",
        first_name="Asha",
        email=email,
        trigger="two units in Wagle Estate",
        handoff="jobs moving to dispatch",
        topic="fabrication jobs",
        subject="Question about Acme Pvt. Ltd.'s fabrication jobs",
        day0="Hi Asha,\n\nBody.\n\nBest,\nPrathamesh Patil\npratz.is-a.dev",
        day4="day 4",
        day8="day 8",
        day14="day 14",
        notes=f"Researched Nov 20; {VALID_MARK} (named inbox, mx=aspmx.l.google.com)",
    )


def test_incomplete_research_is_not_a_send():
    row = lead(lead_id="LEAD-057", research_status="Done", outreach_status="Queued", email="a@acme.in")
    plan = plan_sends(
        [row],
        today=TODAY,
        mailboxes=MAILBOXES,
        sent_today={},
        phase=PHASE,
        reply_to="prathamesh@pratz.is-a.dev",
    )
    assert plan.sends == []
    assert plan.skips[0].reason == "waiting on assembled email"


def test_rotation_skips_a_full_mailbox_and_a_duplicate():
    sent = [
        lead(
            row=index,
            lead_id=f"LEAD-{index:03d}",
            outreach_status="Sent - Day 0",
            assigned_sender=MAILBOXES[0],
            email=f"sent{index}@acme.in",
            last_action=TODAY.isoformat(),
        )
        for index in range(1, 6)
    ]
    fresh = _queued("LEAD-057", "asha@acme.in", 20)
    copy = _queued("LEAD-058", "asha@acme.in", 21)
    plan = plan_sends(
        [*sent, fresh, copy],
        today=TODAY,
        mailboxes=MAILBOXES,
        sent_today={MAILBOXES[0].casefold(): 5},
        phase=PHASE,
        reply_to="prathamesh@pratz.is-a.dev",
    )
    assert [job.lead_id for job in plan.sends] == ["LEAD-057"]
    assert plan.sends[0].mailbox == MAILBOXES[1]
    assert any(skip.lead_id == "LEAD-058" and skip.reason.startswith("duplicate") for skip in plan.skips)


def test_followup_uses_the_locked_sender_on_the_business_day():
    row = _queued("LEAD-002", "info@prime-dental.in", 8, sender=MAILBOXES[0])
    row.set_field("outreach_status", "Sent - Day 0")
    row.set_field("last_action", "2026-11-19")
    row.set_field("next_action", "2026-11-25")
    row.set_field("message_id", "<day0@pratz.is-a.dev>")
    too_early = plan_sends(
        [row],
        today=date(2026, 11, 24),
        mailboxes=MAILBOXES,
        sent_today={},
        phase=PHASE,
        reply_to="prathamesh@pratz.is-a.dev",
    )
    assert too_early.sends == []
    due = plan_sends(
        [row],
        today=date(2026, 11, 25),
        mailboxes=MAILBOXES,
        sent_today={},
        phase=PHASE,
        reply_to="prathamesh@pratz.is-a.dev",
    )
    assert due.sends[0].touch == "day4"
    assert due.sends[0].mailbox == MAILBOXES[0]
    assert due.sends[0].subject.startswith("Re: ")
    assert due.sends[0].parent_message_id == "<day0@pratz.is-a.dev>"


def test_numeric_zoho_id_is_not_used_as_a_thread_header():
    assert rfc_message_id("1795067500939108000") is None
    assert rfc_message_id("<abc@pratz.is-a.dev>") == "<abc@pratz.is-a.dev>"


def test_confirm_sends_once_and_records_the_thread_id(tmp_path):
    row = _queued("LEAD-057", "asha@acme.in", 20)
    plan = plan_sends(
        [row],
        today=TODAY,
        mailboxes=MAILBOXES,
        sent_today={},
        phase=PHASE,
        reply_to="prathamesh@pratz.is-a.dev",
    )
    settings = load_settings()
    state = SendState(tmp_path / "send_state.json")
    mailer = _Mailer()
    zone = ZoneInfo("Asia/Kolkata")
    clock = datetime(2026, 11, 23, 10, 0, tzinfo=zone)
    repo = _Repo()
    summary = run_sends(
        [row],
        plan,
        repo=repo,
        settings=settings,
        state=state,
        mailer=mailer,
        confirm=True,
        max_sends=1,
        ignore_window=True,
        retry_unconfirmed=False,
        now_fn=lambda: clock,
        sleep=lambda _seconds: None,
        rng=_FixedRandom(),
    )
    assert summary.sent == ["LEAD-057"]
    assert row.status == "Sent - Day 0"
    assert row.text("assigned_sender") == plan.sends[0].mailbox
    assert row.text("message_id").startswith("<")
    assert row.text("last_action") == "2026-11-23"
    assert row.text("next_action") == "2026-11-27"
    assert mailer.sent[0]["Reply-To"] == "prathamesh@pratz.is-a.dev"
    assert mailer.sent[0].get_content_type() == "text/plain"
    saved = SendState.load(state.path)
    assert saved.records[0].smtp_ok and saved.records[0].sheet_synced


def test_smtp_refusal_marks_bounced_and_does_not_keep_a_claim(tmp_path):
    row = _queued("LEAD-057", "asha@acme.in", 20)
    plan = plan_sends(
        [row],
        today=TODAY,
        mailboxes=MAILBOXES,
        sent_today={},
        phase=PHASE,
        reply_to="prathamesh@pratz.is-a.dev",
    )
    state = SendState(tmp_path / "send_state.json")
    summary = run_sends(
        [row],
        plan,
        repo=_Repo(),
        settings=load_settings(),
        state=state,
        mailer=_Mailer(refuse=True),
        confirm=True,
        max_sends=1,
        ignore_window=True,
        retry_unconfirmed=False,
        now_fn=lambda: datetime(2026, 11, 23, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        sleep=lambda _seconds: None,
        rng=_FixedRandom(),
    )
    assert summary.sent == []
    assert row.status == "Bounced"
    assert state.records == []


def test_unsynced_ledger_is_written_to_the_sheet_without_a_second_send(tmp_path):
    row = _queued("LEAD-057", "asha@acme.in", 20)
    record = SendRecord(
        lead_id="LEAD-057",
        touch="day0",
        mailbox=MAILBOXES[0],
        message_id="<kept@pratz.is-a.dev>",
        parent_message_id="",
        to_email="asha@acme.in",
        subject=row.text("subject"),
        at="2026-11-23T10:00:00+05:30",
        smtp_ok=True,
        sheet_synced=False,
    )
    state = SendState(tmp_path / "send_state.json", [record])
    mailer = _Mailer()
    run_sends(
        [row],
        plan_sends([row], today=TODAY, mailboxes=MAILBOXES, sent_today={}, phase=PHASE, reply_to="prathamesh@pratz.is-a.dev"),
        repo=_Repo(),
        settings=load_settings(),
        state=state,
        mailer=mailer,
        confirm=True,
        max_sends=1,
        ignore_window=True,
        retry_unconfirmed=False,
        now_fn=lambda: datetime(2026, 11, 23, 11, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        sleep=lambda _seconds: None,
        rng=_FixedRandom(),
    )
    assert mailer.sent == []
    assert row.status == "Sent - Day 0"
    assert row.text("message_id") == "<kept@pratz.is-a.dev>"
    assert state.records[0].sheet_synced


def test_apply_send_does_not_replace_the_day0_message_id():
    row = _queued("LEAD-002", "info@prime-dental.in", 8, sender=MAILBOXES[0])
    row.set_field("message_id", "<day0@pratz.is-a.dev>")
    apply_send(
        row,
        SendRecord(
            lead_id="LEAD-002",
            touch="day4",
            mailbox=MAILBOXES[0],
            message_id="<day0@pratz.is-a.dev>",
            parent_message_id="<day0@pratz.is-a.dev>",
            to_email=row.text("email"),
            subject="Re: Question",
            at="2026-11-25T10:00:00+05:30",
            smtp_ok=True,
            sheet_synced=False,
        ),
    )
    assert row.text("message_id") == "<day0@pratz.is-a.dev>"
    assert row.status == "Sent - Day 4"
    assert row.text("next_action") == "2026-12-01"


class _Repo:
    def save(self, lead):
        lead.dirty.clear()


class _Mailer:
    def __init__(self, refuse=False):
        self.sent = []
        self.refuse = refuse

    def send(self, mailbox, message):
        if self.refuse:
            raise smtplib.SMTPRecipientsRefused({message["To"]: (550, b"no such user")})
        self.sent.append(message)


class _FixedRandom:
    def randint(self, start, end):
        return start
