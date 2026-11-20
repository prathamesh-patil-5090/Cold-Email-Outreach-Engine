"""Local send ledger so a crash cannot send the same touch twice."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class SendRecord:
    lead_id: str
    touch: str
    mailbox: str
    message_id: str
    parent_message_id: str
    to_email: str
    subject: str
    at: str
    smtp_ok: bool
    sheet_synced: bool

    @property
    def key(self) -> tuple[str, str]:
        return (self.lead_id, self.touch)


class SendState:
    def __init__(self, path: Path, records: list[SendRecord] | None = None):
        self.path = path
        self.records = records or []

    def get(self, lead_id: str, touch: str) -> SendRecord | None:
        for record in self.records:
            if record.lead_id == lead_id and record.touch == touch:
                return record
        return None

    def upsert(self, record: SendRecord) -> None:
        for index, existing in enumerate(self.records):
            if existing.key == record.key:
                self.records[index] = record
                return
        self.records.append(record)

    def remove(self, lead_id: str, touch: str) -> None:
        self.records = [
            record
            for record in self.records
            if not (record.lead_id == lead_id and record.touch == touch)
        ]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"sends": [asdict(record) for record in self.records]}, indent=2)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.path)

    @classmethod
    def load(cls, path: Path) -> "SendState":
        if not path.is_file():
            return cls(path, [])
        raw = json.loads(path.read_text())
        records = [SendRecord(**item) for item in raw.get("sends", [])]
        return cls(path, records)


def sent_today_by_mailbox(leads, state: SendState, today_iso: str) -> dict[str, int]:
    """Count each lead once, from the sheet or from an unsynced ledger row."""
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for lead in leads:
        if lead.text("last_action") != today_iso:
            continue
        if not lead.status_key.startswith("sent"):
            continue
        mailbox = lead.text("assigned_sender").casefold()
        if not mailbox or lead.lead_id in seen:
            continue
        seen.add(lead.lead_id)
        counts[mailbox] = counts.get(mailbox, 0) + 1
    for record in state.records:
        if not record.smtp_ok or not record.at.startswith(today_iso):
            continue
        if record.lead_id in seen:
            continue
        seen.add(record.lead_id)
        mailbox = record.mailbox.casefold()
        counts[mailbox] = counts.get(mailbox, 0) + 1
    return counts

