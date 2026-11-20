"""Quality checks on Grok research fields and assembled email copy.

Bad Grok inputs (buzzwords, empty topic, awkward fragments) should not reach
SMTP. Failing rows stay Queued/Needs Review with a Notes mark.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from outreach.columns import DAY0_STATUSES
from outreach.models import Lead
from outreach.templates import Sequence, looks_like_mail_merge_risk
from outreach.verify import _append

QA_PASS = "Copy QA: PASS"
QA_FAIL = "Copy QA: FAIL"
NEEDS_REVIEW = "Needs Review"

BUZZWORDS = {
    "synergy",
    "leverage",
    "cutting-edge",
    "cutting edge",
    "best-in-class",
    "best in class",
    "revolutionary",
    "world-class",
    "world class",
    "next-gen",
    "next gen",
    "ai-powered",
    "ai powered",
    "game-changer",
    "game changer",
    "robust",
    "seamless",
    "holistic",
    "paradigm",
    "disrupt",
    "unlock value",
    "digital transformation",
}

SALESY = {
    "book a call",
    "schedule a demo",
    "our solution",
    "we offer",
    "pricing",
    "limited time",
    "guaranteed",
    "act now",
}

PLACEHOLDER_RE = re.compile(
    r"(\{\{|\[\[[^\]]+\]\]|TBD|TODO|lorem ipsum|xxx+|your company|insert )"
    ,
    re.I,
)
BROKEN_JOIN_RE = re.compile(
    r"(looking into\s+[,.\u2014-]|tracks\s+[,.\u2014-]|handles\s+[,.\u2014-]|around\s+[,.\u2014-]|Hi\s*,)",
    re.I,
)


@dataclass(frozen=True)
class QAResult:
    ok: bool
    issues: tuple[str, ...]

    @property
    def summary(self) -> str:
        if self.ok:
            return "ok"
        return "; ".join(self.issues)


def check_research(
    *,
    company: str,
    first_name: str,
    trigger: str,
    handoff: str,
    topic: str,
) -> QAResult:
    issues: list[str] = []
    if not company.strip():
        issues.append("company is blank")
    if not first_name.strip():
        issues.append("first name is blank")
    elif len(first_name.split()) > 3:
        issues.append("first name looks too long")

    issues.extend(_phrase_issues("Verified Trigger", trigger, min_words=4, max_words=28, lowercase_start=True))
    issues.extend(_phrase_issues("Workflow Handoff", handoff, min_words=4, max_words=28, lowercase_start=True))
    issues.extend(_topic_issues(topic))

    for label, text in (("trigger", trigger), ("handoff", handoff), ("topic", topic)):
        hit = _buzzword_hit(text)
        if hit:
            issues.append(f"{label} has buzzword '{hit}'")
    return QAResult(ok=not issues, issues=tuple(issues))


def check_sequence(sequence: Sequence, *, company: str, first_name: str, topic: str) -> QAResult:
    issues: list[str] = []
    for label, body in (
        ("subject", sequence.subject),
        ("day0", sequence.day0),
        ("day4", sequence.day4),
        ("day8", sequence.day8),
        ("day14", sequence.day14),
    ):
        if not body.strip():
            issues.append(f"{label} is blank")
            continue
        risk = looks_like_mail_merge_risk(body)
        if risk:
            issues.append(f"{label}: {risk}")
        if PLACEHOLDER_RE.search(body):
            issues.append(f"{label} still has a placeholder")
        if BROKEN_JOIN_RE.search(body):
            issues.append(f"{label} has a broken phrase join from a bad research field")
        if "  " in body.replace("\n\n", "\n"):
            issues.append(f"{label} has doubled spaces")
        lowered = body.casefold()
        for phrase in SALESY:
            if phrase in lowered:
                issues.append(f"{label} sounds salesy ({phrase})")
                break

    day0_words = _word_count(sequence.day0)
    if day0_words > 95:
        issues.append(f"day0 is too long ({day0_words} words; keep under 95)")
    if day0_words < 35:
        issues.append(f"day0 is too short ({day0_words} words)")

    if first_name and f"Hi {first_name}" not in sequence.day0:
        issues.append("day0 greeting does not use the contact first name")
    if company and company not in sequence.day0:
        issues.append("day0 is missing the company name")
    if topic and topic not in sequence.subject and topic not in sequence.day0:
        issues.append("topic never appears in subject or day0")
    if not sequence.subject.strip() or len(sequence.subject) > 120:
        issues.append("subject length looks wrong")

    return QAResult(ok=not issues, issues=tuple(issues))


def check_lead_copy(lead: Lead) -> QAResult:
    research = check_research(
        company=lead.text("company"),
        first_name=lead.text("first_name"),
        trigger=lead.text("trigger"),
        handoff=lead.text("handoff"),
        topic=lead.text("topic"),
    )
    if not research.ok:
        return research
    if not lead.text("day0"):
        return QAResult(ok=False, issues=("assembled email is missing",))
    sequence = Sequence(
        subject=lead.text("subject"),
        day0=lead.text("day0"),
        day4=lead.text("day4"),
        day8=lead.text("day8"),
        day14=lead.text("day14"),
        variant_key="sheet",
    )
    return check_sequence(
        sequence,
        company=lead.text("company"),
        first_name=lead.text("first_name"),
        topic=lead.text("topic"),
    )


def apply_qa_result(lead: Lead, result: QAResult, *, variant_key: str = "") -> None:
    notes = lead.text("notes")
    notes = _strip_qa_marks(notes)
    if result.ok:
        mark = QA_PASS if not variant_key else f"{QA_PASS} ({variant_key})"
        lead.set_field("notes", _append(notes, mark))
        return
    lead.set_field("notes", _append(notes, f"{QA_FAIL} ({result.summary})"))
    if lead.status_key in DAY0_STATUSES or lead.status_key == "":
        lead.set_field("outreach_status", NEEDS_REVIEW)


def copy_is_approved(lead: Lead) -> bool:
    notes = lead.text("notes")
    if QA_FAIL in notes:
        return False
    if lead.status_key == NEEDS_REVIEW.casefold():
        return False
    return QA_PASS in notes or bool(lead.text("day0"))


def _phrase_issues(
    label: str,
    text: str,
    *,
    min_words: int,
    max_words: int,
    lowercase_start: bool,
) -> list[str]:
    cleaned = " ".join(text.split()).strip()
    issues: list[str] = []
    if not cleaned:
        return [f"{label} is blank"]
    words = cleaned.split()
    if len(words) < min_words:
        issues.append(f"{label} is too short ({len(words)} words)")
    if len(words) > max_words:
        issues.append(f"{label} is too long ({len(words)} words)")
    if lowercase_start and cleaned[0].isalpha() and cleaned[0].isupper():
        issues.append(f"{label} should start lowercase (Grok rule)")
    if cleaned.endswith("."):
        issues.append(f"{label} should not end with a period")
    if PLACEHOLDER_RE.search(cleaned):
        issues.append(f"{label} still has a placeholder")
    return issues


def _topic_issues(topic: str) -> list[str]:
    cleaned = " ".join(topic.split()).strip()
    if not cleaned:
        return ["Short Workflow Topic is blank"]
    words = cleaned.split()
    issues: list[str] = []
    if not 2 <= len(words) <= 3:
        issues.append(f"Short Workflow Topic should be 2–3 words (got {len(words)})")
    if cleaned != cleaned.lower():
        issues.append("Short Workflow Topic should be lowercase")
    if cleaned.endswith("."):
        issues.append("Short Workflow Topic should not end with a period")
    return issues


def _buzzword_hit(text: str) -> str | None:
    lowered = text.casefold()
    for word in sorted(BUZZWORDS, key=len, reverse=True):
        if word in lowered:
            return word
    return None


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _strip_qa_marks(notes: str) -> str:
    parts = [part.strip() for part in notes.split(";") if part.strip()]
    kept = [part for part in parts if not part.startswith(QA_PASS) and not part.startswith(QA_FAIL)]
    return "; ".join(kept)
