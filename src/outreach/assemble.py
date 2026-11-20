"""Fill Subject Line and the four email bodies when research fields exist."""

from __future__ import annotations

from dataclasses import dataclass

from outreach.columns import COLUMNS
from outreach.models import Lead
from outreach.templates import looks_like_mail_merge_risk, render_sequence

RESEARCH_FIELDS = ("trigger", "handoff", "topic", "company", "first_name")


@dataclass
class AssembleSummary:
    assembled: list[str]
    already: list[str]
    waiting: list[tuple[str, str]]


def assemble_leads(leads: list[Lead]) -> AssembleSummary:
    summary = AssembleSummary(assembled=[], already=[], waiting=[])
    for lead in leads:
        if not lead.lead_id:
            continue
        if lead.text("subject") or lead.text("day0"):
            summary.already.append(lead.lead_id)
            continue
        if not lead.research_done:
            summary.waiting.append((lead.lead_id, "research status is not Done"))
            continue
        missing = [lead_label(key) for key in RESEARCH_FIELDS if not lead.text(key)]
        if missing:
            summary.waiting.append((lead.lead_id, "waiting on " + ", ".join(missing)))
            continue
        sequence = render_sequence(
            company=lead.text("company"),
            first_name=lead.text("first_name"),
            trigger=lead.text("trigger"),
            handoff=lead.text("handoff"),
            topic=lead.text("topic"),
        )
        risky = looks_like_mail_merge_risk(sequence.day0) or looks_like_mail_merge_risk(sequence.day8)
        if risky:
            summary.waiting.append((lead.lead_id, risky))
            continue
        lead.set_field("subject", sequence.subject)
        lead.set_field("day0", sequence.day0)
        lead.set_field("day4", sequence.day4)
        lead.set_field("day8", sequence.day8)
        lead.set_field("day14", sequence.day14)
        summary.assembled.append(lead.lead_id)
    return summary


def lead_label(key: str) -> str:
    return COLUMNS[key]
