"""Optional Postgres mirror of the Outreach Tracker."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from outreach.config import ConfigError, Settings
from outreach.models import Lead
from outreach.state import SendRecord

FIELD_MAP = (
    ("research_status", "research_status"),
    ("outreach_status", "outreach_status"),
    ("assigned_sender", "assigned_sender"),
    ("company", "company_name"),
    ("first_name", "contact_first_name"),
    ("email", "contact_email"),
    ("industry", "industry"),
    ("trigger", "verified_trigger"),
    ("handoff", "workflow_handoff"),
    ("topic", "short_workflow_topic"),
    ("subject", "subject_line"),
    ("day0", "day0_email"),
    ("day4", "day4_email"),
    ("day8", "day8_email"),
    ("day14", "day14_email"),
    ("message_id", "message_id"),
    ("notes", "notes"),
)


@dataclass
class SyncSummary:
    upserted: int
    send_events: int


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def require_database_url() -> str:
    url = database_url()
    if not url:
        raise ConfigError(
            "DATABASE_URL is not set. Add your Postgres connection string to .env, e.g.\n"
            "DATABASE_URL=postgresql://user:pass@host:5432/dbname"
        )
    return url


def connect(url: str | None = None):
    try:
        import psycopg
    except ImportError as exc:
        raise ConfigError("Install psycopg: pip install 'psycopg[binary]'") from exc
    return psycopg.connect(url or require_database_url())


def ensure_schema(settings: Settings, url: str | None = None) -> None:
    schema = (settings.root / "sql" / "schema.sql").read_text()
    with connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(schema)
        conn.commit()


def sync_leads(settings: Settings, leads: Iterable[Lead], url: str | None = None) -> SyncSummary:
    rows = list(leads)
    if not rows:
        return SyncSummary(upserted=0, send_events=0)
    ensure_schema(settings, url)
    sql = """
        INSERT INTO leads (
            lead_id, spreadsheet_id, worksheet, row_number,
            research_status, outreach_status, assigned_sender,
            company_name, contact_first_name, contact_email, industry,
            verified_trigger, workflow_handoff, short_workflow_topic,
            subject_line, day0_email, day4_email, day8_email, day14_email,
            message_id, last_action_date, next_action_date, notes, raw, synced_at
        ) VALUES (
            %(lead_id)s, %(spreadsheet_id)s, %(worksheet)s, %(row_number)s,
            %(research_status)s, %(outreach_status)s, %(assigned_sender)s,
            %(company_name)s, %(contact_first_name)s, %(contact_email)s, %(industry)s,
            %(verified_trigger)s, %(workflow_handoff)s, %(short_workflow_topic)s,
            %(subject_line)s, %(day0_email)s, %(day4_email)s, %(day8_email)s, %(day14_email)s,
            %(message_id)s, %(last_action_date)s, %(next_action_date)s, %(notes)s,
            %(raw)s::jsonb, NOW()
        )
        ON CONFLICT (lead_id) DO UPDATE SET
            spreadsheet_id = EXCLUDED.spreadsheet_id,
            worksheet = EXCLUDED.worksheet,
            row_number = EXCLUDED.row_number,
            research_status = EXCLUDED.research_status,
            outreach_status = EXCLUDED.outreach_status,
            assigned_sender = EXCLUDED.assigned_sender,
            company_name = EXCLUDED.company_name,
            contact_first_name = EXCLUDED.contact_first_name,
            contact_email = EXCLUDED.contact_email,
            industry = EXCLUDED.industry,
            verified_trigger = EXCLUDED.verified_trigger,
            workflow_handoff = EXCLUDED.workflow_handoff,
            short_workflow_topic = EXCLUDED.short_workflow_topic,
            subject_line = EXCLUDED.subject_line,
            day0_email = EXCLUDED.day0_email,
            day4_email = EXCLUDED.day4_email,
            day8_email = EXCLUDED.day8_email,
            day14_email = EXCLUDED.day14_email,
            message_id = EXCLUDED.message_id,
            last_action_date = EXCLUDED.last_action_date,
            next_action_date = EXCLUDED.next_action_date,
            notes = EXCLUDED.notes,
            raw = EXCLUDED.raw,
            synced_at = NOW()
    """
    payloads = [_lead_payload(settings, lead) for lead in rows]
    with connect(url) as conn:
        with conn.cursor() as cur:
            for payload in payloads:
                cur.execute(sql, payload)
        conn.commit()
    return SyncSummary(upserted=len(payloads), send_events=0)


def sync_send_record(settings: Settings, record: SendRecord, url: str | None = None) -> None:
    if not database_url() and url is None:
        return
    ensure_schema(settings, url)
    with connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leads (lead_id, spreadsheet_id, worksheet, raw, synced_at)
                VALUES (%s, %s, %s, '{}'::jsonb, NOW())
                ON CONFLICT (lead_id) DO NOTHING
                """,
                (record.lead_id, settings.spreadsheet_id, settings.worksheet),
            )
            cur.execute(
                """
                INSERT INTO send_events (
                    lead_id, touch, mailbox, message_id, parent_message_id,
                    to_email, subject, sent_at, smtp_ok, sheet_synced
                ) VALUES (
                    %(lead_id)s, %(touch)s, %(mailbox)s, %(message_id)s, %(parent_message_id)s,
                    %(to_email)s, %(subject)s, %(sent_at)s, %(smtp_ok)s, %(sheet_synced)s
                )
                ON CONFLICT (lead_id, touch) DO UPDATE SET
                    mailbox = EXCLUDED.mailbox,
                    message_id = EXCLUDED.message_id,
                    parent_message_id = EXCLUDED.parent_message_id,
                    to_email = EXCLUDED.to_email,
                    subject = EXCLUDED.subject,
                    sent_at = EXCLUDED.sent_at,
                    smtp_ok = EXCLUDED.smtp_ok,
                    sheet_synced = EXCLUDED.sheet_synced
                """,
                {
                    "lead_id": record.lead_id,
                    "touch": record.touch,
                    "mailbox": record.mailbox,
                    "message_id": record.message_id or None,
                    "parent_message_id": record.parent_message_id or None,
                    "to_email": record.to_email,
                    "subject": record.subject,
                    "sent_at": record.at or None,
                    "smtp_ok": record.smtp_ok,
                    "sheet_synced": record.sheet_synced,
                },
            )
        conn.commit()


def maybe_sync_leads(settings: Settings, leads: Iterable[Lead]) -> SyncSummary | None:
    if not database_url():
        return None
    return sync_leads(settings, leads)


def _lead_payload(settings: Settings, lead: Lead) -> dict:
    payload = {
        "lead_id": lead.lead_id,
        "spreadsheet_id": settings.spreadsheet_id,
        "worksheet": settings.worksheet,
        "row_number": lead.row_number,
        "last_action_date": _date_or_none(lead.text("last_action")),
        "next_action_date": _date_or_none(lead.text("next_action")),
        "raw": json.dumps(lead.values),
    }
    for key, column in FIELD_MAP:
        payload[column] = lead.text(key) or None
    return payload


def _date_or_none(value: str) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
