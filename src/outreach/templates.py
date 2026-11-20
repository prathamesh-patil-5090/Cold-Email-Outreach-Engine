"""Render sequences in the proven Outreach Tracker voice (LEAD-002+).

Day 0 has 3 alternate structures. Day 4 / 8 / 14 stay in the live-sheet
follow-up family with light phrasing spins. Variant choice is stable per Lead ID.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

DAY0_SIGNATURE = "Best,\nPrathamesh Patil\npratz.is-a.dev"
FOLLOWUP_SIGNATURE = "Best,\nPrathamesh"

SUBJECT_VARIANTS = (
    "Question about {company}'s {topic}",
    "Quick question about {company}'s {topic}",
    "Question regarding {topic} at {company}",
    "Quick question regarding {topic} at {company}",
)

# Three distinct Day 0 layouts. Same facts, different paragraph structure.
DAY0_STRUCTURES = (
    # Structure A — classic LEAD-002 single-block discovery question
    (
        "Hi {first_name},\n\n"
        "I'm Prathamesh, a software developer helping businesses simplify operations "
        "with custom tools and automation. I came across {company} while looking into "
        "{trigger} and was curious how your team currently tracks {topic}\u2014is that "
        "handled in one system today, or does it still involve manual coordination?\n\n"
        "If relevant, open to a quick 15-minute chat? If it's already running smoothly, "
        "no worries.\n\n"
        "{day0_signature}"
    ),
    # Structure B — short intro, then a standalone ops question
    (
        "Hi {first_name},\n\n"
        "Prathamesh here \u2014 software developer. I help ops-heavy teams cut manual "
        "coordination with simple internal tools.\n\n"
        "Looking at {trigger} at {company}, how do you currently keep {topic} organised? "
        "One system, or still a mix of sheets / chats / verbal handoffs?\n\n"
        "Happy to compare notes for 15 minutes if useful; if that side is already clean, "
        "all good.\n\n"
        "{day0_signature}"
    ),
    # Structure C — observation first, then soft ask
    (
        "Hi {first_name},\n\n"
        "I was reading about {trigger} at {company} and wondered about the day-to-day "
        "side of {topic}.\n\n"
        "I'm Prathamesh, a software developer building custom tools when those handoffs "
        "get messy. Is {topic} already tracked cleanly end to end, or does it still take "
        "extra chasing?\n\n"
        "No pitch either way \u2014 reply if a short chat would help, otherwise ignore this.\n\n"
        "{day0_signature}"
    ),
)

DAY4_BODIES = (
    (
        "Just following up on my note from earlier this week about how {company} handles "
        "{topic}. If simplifying that workflow is on your radar, happy to exchange a few "
        "quick ideas. If not, no worries at all."
    ),
    (
        "Just following up on my note from earlier this week about how {company} handles "
        "{topic}. If that workflow is something you're tightening up, happy to exchange a "
        "few quick ideas. If not, no worries at all."
    ),
    (
        "Following up on my earlier note about how {company} handles {topic}. If simplifying "
        "that workflow is on your radar, happy to compare notes. If not, no worries at all."
    ),
)

DAY8_BODIES = (
    (
        "One reason I reached out is that {trigger} often involves several manual "
        "handoffs around {handoff}. Curious whether your current setup handles that "
        "smoothly or if it creates bottlenecks for your team?\n\n"
        "Happy to have a brief chat if useful\u2014otherwise no problem at all."
    ),
    (
        "One reason I reached out is that {trigger} often involves several manual "
        "handoffs around {handoff}. Curious whether your current setup handles that "
        "smoothly, or if it still creates extra chasing for the team?\n\n"
        "Happy to have a brief chat if useful\u2014otherwise no problem at all."
    ),
    (
        "The reason I wrote is that {trigger} often involves several manual handoffs "
        "around {handoff}. Does your current setup handle that smoothly, or does it "
        "create bottlenecks?\n\n"
        "Happy to have a brief chat if useful\u2014otherwise no problem at all."
    ),
)

DAY14_BODIES = (
    (
        "I'll close the loop here so I don't crowd your inbox. If streamlining "
        "{topic} becomes a priority down the line, feel free to reach out anytime."
    ),
    (
        "I'll close the loop here so I don't crowd your inbox. If {topic} becomes a "
        "priority down the line, feel free to reach out anytime."
    ),
    (
        "Closing the loop here so I don't keep bumping your inbox. If streamlining "
        "{topic} becomes a priority later, feel free to reach out anytime."
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
    day0_i = _pick(seed, "day0_structure", len(DAY0_STRUCTURES))
    day4_i = _pick(seed, "day4", len(DAY4_BODIES))
    day8_i = _pick(seed, "day8", len(DAY8_BODIES))
    day14_i = _pick(seed, "day14", len(DAY14_BODIES))

    values = {
        "company": company,
        "first_name": first_name,
        "trigger": trigger,
        "handoff": handoff,
        "topic": topic,
        "day0_signature": DAY0_SIGNATURE,
    }
    return Sequence(
        subject=SUBJECT_VARIANTS[subject_i].format(**values),
        day0=DAY0_STRUCTURES[day0_i].format(**values),
        day4=(
            f"Hi {first_name},\n\n"
            f"{DAY4_BODIES[day4_i].format(**values)}\n\n"
            f"{FOLLOWUP_SIGNATURE}"
        ),
        day8=(
            f"Hi {first_name},\n\n"
            f"{DAY8_BODIES[day8_i].format(**values)}\n\n"
            f"{FOLLOWUP_SIGNATURE}"
        ),
        day14=(
            f"Hi {first_name},\n\n"
            f"{DAY14_BODIES[day14_i].format(**values)}\n\n"
            f"{FOLLOWUP_SIGNATURE}"
        ),
        variant_key=f"s{subject_i}-d0s{day0_i}-d4{day4_i}-d8{day8_i}-d14{day14_i}",
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
