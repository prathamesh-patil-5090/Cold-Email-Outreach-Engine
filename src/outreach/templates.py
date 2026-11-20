"""Render rotating plain-text sequences from the three research phrases.

Variant choice is stable per Lead ID so re-running assemble does not reshuffle
copy for the same row. Day 0–14 stay link-free and HTML-free.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

DAY0_SIGNATURE = "Best,\nPrathamesh Patil\npratz.is-a.dev"
FOLLOWUP_SIGNATURE = "Best,\nPrathamesh"

SUBJECT_VARIANTS = (
    "Question about {company}'s {topic}",
    "Quick question on {topic} at {company}",
    "How {company} handles {topic}",
    "Curious about {topic} at {company}",
)

DAY0_VARIANTS = (
    (
        "Hi {first_name},\n\n"
        "I'm Prathamesh, a software developer helping businesses simplify operations "
        "with custom tools and automation. "
        "I came across {company} while looking into {trigger} and was curious how your "
        "team currently tracks {topic}\u2014is that handled in one system today, or does "
        "it still involve manual coordination?\n\n"
        "If relevant, open to a quick 15-minute chat? If it's already running smoothly, "
        "no worries.\n\n"
        "{day0_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "I'm Prathamesh \u2014 I build custom tools and automation for ops-heavy teams. "
        "Saw {company}'s work around {trigger} and wondered how you currently keep "
        "{topic} organized across the team.\n\n"
        "Worth a short chat if useful; if that side is already clean, all good.\n\n"
        "{day0_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "Prathamesh here. I help manufacturers and distributors cut manual coordination "
        "with lightweight internal tools. Looking at {trigger} at {company}, I was "
        "curious whether {topic} lives in one place today or still moves across a few "
        "handoffs.\n\n"
        "Happy to compare notes for 15 minutes if that's useful.\n\n"
        "{day0_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "I'm Prathamesh, a software developer. I noticed {company} while reading about "
        "{trigger}. Quick question: how does your team track {topic} day to day\u2014"
        "mostly one system, or still some spreadsheet / WhatsApp / verbal handoffs?\n\n"
        "No pitch needed either way. Open to a brief call only if it's relevant.\n\n"
        "{day0_signature}"
    ),
)

DAY4_VARIANTS = (
    (
        "Hi {first_name},\n\n"
        "Just following up on my note from earlier this week about how {company} handles "
        "{topic}. If simplifying that workflow is on your radar, happy to exchange a few "
        "quick ideas. If not, no worries at all.\n\n"
        "{followup_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "Circling back on {topic} at {company}. If now isn't the right time, feel free to "
        "ignore this. If it is, I can share a couple of simple ways teams keep that "
        "handoff cleaner.\n\n"
        "{followup_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "Wanted to bump my earlier note on {topic}. Still happy to chat if that workflow "
        "is something you're tightening up this quarter.\n\n"
        "{followup_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "Quick follow-up only. Are you the right person at {company} for questions around "
        "{topic}, or should I reach someone else on the ops side?\n\n"
        "{followup_signature}"
    ),
)

DAY8_VARIANTS = (
    (
        "Hi {first_name},\n\n"
        "One reason I reached out is that {trigger} often involves several manual "
        "handoffs around {handoff}. Curious whether your current setup handles that "
        "smoothly or if it creates bottlenecks for your team?\n\n"
        "Happy to have a brief chat if useful\u2014otherwise no problem at all.\n\n"
        "{followup_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "From the outside, {trigger} looks like it depends on clean coordination around "
        "{handoff}. Is that already tight at {company}, or does it still take extra "
        "chasing between teams?\n\n"
        "Either answer is useful \u2014 no need to force a call.\n\n"
        "{followup_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "Sharing the angle more plainly: when {trigger} is in play, {handoff} is usually "
        "where delays show up. How are you handling that today?\n\n"
        "If it's already solved, I'll leave you alone.\n\n"
        "{followup_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "Last useful question from me for a bit \u2014 with {trigger}, does {handoff} stay "
        "visible end to end, or do people still reconcile it manually?\n\n"
        "Happy to compare notes if helpful.\n\n"
        "{followup_signature}"
    ),
)

DAY14_VARIANTS = (
    (
        "Hi {first_name},\n\n"
        "I'll close the loop here so I don't crowd your inbox. If streamlining "
        "{topic} becomes a priority down the line, feel free to reach out anytime.\n\n"
        "{followup_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "Closing this thread for now. If {topic} at {company} becomes painful later, "
        "you can reply to this email anytime.\n\n"
        "{followup_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "I'll step back so I'm not another follow-up in the pile. Door's open if "
        "{topic} ever needs a cleaner system.\n\n"
        "{followup_signature}"
    ),
    (
        "Hi {first_name},\n\n"
        "Last note from me. Wishing you a smooth quarter on {topic} \u2014 reach out if a "
        "custom tool would help later.\n\n"
        "{followup_signature}"
    ),
)


@dataclass(frozen=True)
class Sequence:
    subject: str
    day0: str
    day4: str
    day8: str
    day14: str
    variant_key: str


def render_sequence(
    *,
    company: str,
    first_name: str,
    trigger: str,
    handoff: str,
    topic: str,
    lead_id: str = "",
) -> Sequence:
    company = _phrase(company, strip_period=False)
    first_name = _phrase(first_name, strip_period=False)
    trigger = _phrase(trigger, strip_period=True)
    handoff = _phrase(handoff, strip_period=True)
    topic = _phrase(topic, strip_period=True)
    seed = lead_id or f"{company}|{first_name}|{topic}"
    subject_i = _pick(seed, "subject", len(SUBJECT_VARIANTS))
    day0_i = _pick(seed, "day0", len(DAY0_VARIANTS))
    day4_i = _pick(seed, "day4", len(DAY4_VARIANTS))
    day8_i = _pick(seed, "day8", len(DAY8_VARIANTS))
    day14_i = _pick(seed, "day14", len(DAY14_VARIANTS))
    values = {
        "company": company,
        "first_name": first_name,
        "trigger": trigger,
        "handoff": handoff,
        "topic": topic,
        "day0_signature": DAY0_SIGNATURE,
        "followup_signature": FOLLOWUP_SIGNATURE,
    }
    return Sequence(
        subject=SUBJECT_VARIANTS[subject_i].format(**values),
        day0=DAY0_VARIANTS[day0_i].format(**values),
        day4=DAY4_VARIANTS[day4_i].format(**values),
        day8=DAY8_VARIANTS[day8_i].format(**values),
        day14=DAY14_VARIANTS[day14_i].format(**values),
        variant_key=f"s{subject_i}-d0{day0_i}-d4{day4_i}-d8{day8_i}-d14{day14_i}",
    )


def followup_subject(subject: str) -> str:
    if subject.casefold().startswith("re:"):
        return subject
    return f"Re: {subject}"


def looks_like_mail_merge_risk(body: str) -> str | None:
    """Plain text only. Day 0 through Day 14 do not carry links or HTML."""
    lowered = body.lower()
    if "http://" in lowered or "https://" in lowered or "www." in lowered:
        return "body contains a link"
    if "<" in body and ">" in body:
        return "body contains HTML"
    return None


def _pick(seed: str, salt: str, size: int) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % size


def _phrase(value: str, *, strip_period: bool) -> str:
    text = " ".join(value.split())
    if strip_period and text.endswith("."):
        text = text[:-1].rstrip()
    return text
