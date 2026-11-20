"""Fill Subject Line and the four email bodies when research fields exist."""

from __future__ import annotations

from dataclasses import dataclass, field

from outreach.columns import COLUMNS, DAY0_STATUSES
from outreach.models import Lead
from outreach.qa import NEEDS_REVIEW, apply_qa_result, check_research, check_sequence
from outreach.templates import render_sequence

RESEARCH_FIELDS = ("trigger", "handoff", "topic", "company", "first_name")
FORCEABLE = DAY0_STATUSES | {NEEDS_REVIEW.casefold(), ""}


@dataclass
class AssembleSummary:
    assembled: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    waiting: list[tuple[str, str]] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)


def assemble_leads(leads: list[Lead], *, force: bool = False) -> AssembleSummary:
    summary = AssembleSummary()
    for lead in leads:
        if not lead.lead_id:
            continue
        has_copy = bool(lead.text("subject") or lead.text("day0"))
        if has_copy and not force:
            summary.already.append(lead.lead_id)
            continue
        if has_copy and force and lead.status_key not in FORCEABLE:
            summary.already.append(lead.lead_id)
            continue
        if not lead.research_done:
            summary.waiting.append((lead.lead_id, "research status is not Done"))
            continue
        missing = [lead_label(key) for key in RESEARCH_FIELDS if not lead.text(key)]
        if missing:
            summary.waiting.append((lead.lead_id, "waiting on " + ", ".join(missing)))
            continue

        _normalize_research_fields(lead)
        research = check_research(
            company=lead.text("company"),
            first_name=lead.text("first_name"),
            trigger=lead.text("trigger"),
            handoff=lead.text("handoff"),
            topic=lead.text("topic"),
        )
        if not research.ok:
            # Force rewrites should not leave stale L–P sitting on a failed row.
            if force:
                for key in ("subject", "day0", "day4", "day8", "day14"):
                    if lead.text(key):
                        lead.set_field(key, "")
            apply_qa_result(lead, research)
            summary.rejected.append((lead.lead_id, research.summary))
            continue

        sequence = render_sequence(
            company=lead.text("company"),
            first_name=lead.text("first_name"),
            trigger=lead.text("trigger"),
            handoff=lead.text("handoff"),
            topic=lead.text("topic"),
            lead_id=lead.lead_id,
        )
        copy = check_sequence(
            sequence,
            company=lead.text("company"),
            first_name=lead.text("first_name"),
            topic=lead.text("topic"),
        )
        if not copy.ok:
            if force:
                for key in ("subject", "day0", "day4", "day8", "day14"):
                    if lead.text(key):
                        lead.set_field(key, "")
            apply_qa_result(lead, copy, variant_key=sequence.variant_key)
            summary.rejected.append((lead.lead_id, copy.summary))
            continue

        lead.set_field("subject", sequence.subject)
        lead.set_field("day0", sequence.day0)
        lead.set_field("day4", sequence.day4)
        lead.set_field("day8", sequence.day8)
        lead.set_field("day14", sequence.day14)
        apply_qa_result(lead, copy, variant_key=sequence.variant_key)
        summary.assembled.append(lead.lead_id)
    return summary


def lead_label(key: str) -> str:
    return COLUMNS[key]


def _normalize_research_fields(lead: Lead) -> None:
    """Fix small Grok slips before QA. Buzzwords and empty fields still fail."""
    for key in ("trigger", "handoff", "topic"):
        raw = lead.text(key)
        if not raw:
            continue
        cleaned = " ".join(raw.split()).strip()
        if cleaned.endswith("."):
            cleaned = cleaned[:-1].rstrip()
        if key == "topic":
            cleaned = cleaned.lower()
        elif cleaned and cleaned[0].isalpha() and cleaned[0].isupper():
            cleaned = cleaned[0].lower() + cleaned[1:]
        if cleaned != lead.text(key):
            lead.set_field(key, cleaned)
