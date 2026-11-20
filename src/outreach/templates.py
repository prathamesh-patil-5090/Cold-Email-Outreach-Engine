"""Render the four-touch sequence used by LEAD-002 onward.

Python fills Subject Line and the four bodies. The Grok bot only supplies
the company, the first name, and the three research phrases.
"""

from __future__ import annotations

from dataclasses import dataclass

DAY0_SIGNATURE = "Best,\nPrathamesh Patil\npratz.is-a.dev"
FOLLOWUP_SIGNATURE = "Best,\nPrathamesh"


@dataclass(frozen=True)
class Sequence:
    subject: str
    day0: str
    day4: str
    day8: str
    day14: str


def render_sequence(
    *,
    company: str,
    first_name: str,
    trigger: str,
    handoff: str,
    topic: str,
) -> Sequence:
    company = _phrase(company, strip_period=False)
    first_name = _phrase(first_name, strip_period=False)
    trigger = _phrase(trigger, strip_period=True)
    handoff = _phrase(handoff, strip_period=True)
    topic = _phrase(topic, strip_period=True)
    subject = f"Question about {company}'s {topic}"
    day0 = (
        f"Hi {first_name},\n\n"
        "I'm Prathamesh, a software developer helping businesses simplify operations "
        "with custom tools and automation. "
        f"I came across {company} while looking into {trigger} and was curious how your "
        f"team currently tracks {topic}\u2014is that handled in one system today, or does "
        "it still involve manual coordination?\n\n"
        "If relevant, open to a quick 15-minute chat? If it's already running smoothly, "
        "no worries.\n\n"
        f"{DAY0_SIGNATURE}"
    )
    day4 = (
        f"Hi {first_name},\n\n"
        f"Just following up on my note from earlier this week about how {company} handles "
        f"{topic}. If simplifying that workflow is on your radar, happy to exchange a few "
        "quick ideas. If not, no worries at all.\n\n"
        f"{FOLLOWUP_SIGNATURE}"
    )
    day8 = (
        f"Hi {first_name},\n\n"
        f"One reason I reached out is that {trigger} often involves several manual "
        f"handoffs around {handoff}. Curious whether your current setup handles that "
        "smoothly or if it creates bottlenecks for your team?\n\n"
        "Happy to have a brief chat if useful\u2014otherwise no problem at all.\n\n"
        f"{FOLLOWUP_SIGNATURE}"
    )
    day14 = (
        f"Hi {first_name},\n\n"
        "I'll close the loop here so I don't crowd your inbox. If streamlining "
        f"{topic} becomes a priority down the line, feel free to reach out anytime.\n\n"
        f"{FOLLOWUP_SIGNATURE}"
    )
    return Sequence(subject=subject, day0=day0, day4=day4, day8=day8, day14=day14)


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


def _phrase(value: str, *, strip_period: bool) -> str:
    text = " ".join(value.split())
    if strip_period and text.endswith("."):
        text = text[:-1].rstrip()
    return text
