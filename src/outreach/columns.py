"""Canonical Outreach Tracker columns.

The live sheet is the source of truth. The older PRD schema (Email_Verified,
AI_Status, Touch_Stage, and the rest) is intentionally not required. When a
header is missing, the matching step waits for the Grok bot instead of
creating columns.
"""

from __future__ import annotations

# key -> exact header written on the Outreach Tracker tab
COLUMNS: dict[str, str] = {
    "lead_id": "Lead ID",
    "research_status": "Research Status",
    "outreach_status": "Outreach Status",
    "assigned_sender": "Assigned Sender Email",
    "company": "Company Name",
    "first_name": "Contact First Name",
    "email": "Contact Email",
    "industry": "Industry / Segment",
    "trigger": "Verified Trigger",
    "handoff": "Workflow Handoff",
    "topic": "Short Workflow Topic",
    "subject": "Subject Line",
    "day0": "Day 0 Email",
    "day4": "Day 4 Follow-up 1",
    "day8": "Day 8 Follow-up 2",
    "day14": "Day 14 Close Loop",
    "message_id": "Message-ID",
    "last_action": "Last Action Date",
    "next_action": "Next Action Date",
    "notes": "Notes",
}

COLUMN_KEYS: tuple[str, ...] = tuple(COLUMNS)

HEADER_TO_KEY: dict[str, str] = {name.casefold(): key for key, name in COLUMNS.items()}

VERIFY_COLUMNS: tuple[str, ...] = ("lead_id", "email", "outreach_status", "notes")
ASSEMBLE_COLUMNS: tuple[str, ...] = (
    "lead_id",
    "company",
    "first_name",
    "trigger",
    "handoff",
    "topic",
    "subject",
    "day0",
    "day4",
    "day8",
    "day14",
)
FIND_COLUMNS: tuple[str, ...] = (
    "lead_id",
    "research_status",
    "outreach_status",
    "company",
    "first_name",
    "email",
    "industry",
    "trigger",
    "handoff",
    "topic",
    "notes",
)

SEND_COLUMNS: tuple[str, ...] = ASSEMBLE_COLUMNS + (
    "email",
    "outreach_status",
    "assigned_sender",
    "message_id",
    "last_action",
    "next_action",
    "notes",
)

VALID_MARK = "Email check: VALID"
INVALID_MARK = "Email check: INVALID"

# Day 0 is allowed from these outreach statuses. Blank is allowed only when
# the row already has a lead id; Grok is expected to write "Queued".
DAY0_STATUSES = {"queued", "not sent", "ready"}

STOP_PREFIXES = ("replied", "bounced", "stopped", "invalid", "completed", "closed", "needs review")


def header_name(key: str) -> str:
    return COLUMNS[key]


def missing_headers(present: set[str], keys: tuple[str, ...]) -> list[str]:
    return [COLUMNS[key] for key in keys if key not in present]
