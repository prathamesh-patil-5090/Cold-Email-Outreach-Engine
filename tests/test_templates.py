from outreach.templates import followup_subject, render_sequence

COMPANY = "Prime Dental Products Pvt. Ltd."
TRIGGER = "in-house production of 70+ dental formulations for 500+ dealers"
HANDOFF = "distributor orders and finished stock coordinated back to dispatch"
TOPIC = "distributor orders"


def test_day0_matches_the_tracker_copy():
    sequence = render_sequence(
        company=COMPANY,
        first_name="Bharat",
        trigger=TRIGGER,
        handoff=HANDOFF,
        topic=TOPIC,
    )
    assert sequence.subject == "Question about Prime Dental Products Pvt. Ltd.'s distributor orders"
    assert sequence.day0 == (
        "Hi Bharat,\n\n"
        "I'm Prathamesh, a software developer helping businesses simplify operations with custom tools and automation. "
        "I came across Prime Dental Products Pvt. Ltd. while looking into in-house production of 70+ dental formulations "
        "for 500+ dealers and was curious how your team currently tracks distributor orders"
        "\u2014is that handled in one system today, or does it still involve manual coordination?\n\n"
        "If relevant, open to a quick 15-minute chat? If it's already running smoothly, no worries.\n\n"
        "Best,\nPrathamesh Patil\npratz.is-a.dev"
    )
    assert sequence.day4 == (
        "Hi Bharat,\n\n"
        "Just following up on my note from earlier this week about how Prime Dental Products Pvt. Ltd. handles "
        "distributor orders. If simplifying that workflow is on your radar, happy to exchange a few quick ideas. "
        "If not, no worries at all.\n\n"
        "Best,\nPrathamesh"
    )
    assert sequence.day8 == (
        "Hi Bharat,\n\n"
        "One reason I reached out is that in-house production of 70+ dental formulations for 500+ dealers often "
        "involves several manual handoffs around distributor orders and finished stock coordinated back to dispatch. "
        "Curious whether your current setup handles that smoothly or if it creates bottlenecks for your team?\n\n"
        "Happy to have a brief chat if useful\u2014otherwise no problem at all.\n\n"
        "Best,\nPrathamesh"
    )
    assert sequence.day14 == (
        "Hi Bharat,\n\n"
        "I'll close the loop here so I don't crowd your inbox. If streamlining distributor orders becomes a priority "
        "down the line, feel free to reach out anytime.\n\n"
        "Best,\nPrathamesh"
    )
    assert "http" not in sequence.day0
    assert "<" not in sequence.day0


def test_trailing_period_on_a_research_field_is_removed():
    sequence = render_sequence(
        company="Acme",
        first_name="Asha",
        trigger="two plants in Vapi.",
        handoff="jobs moving to dispatch.",
        topic="plant jobs.",
    )
    assert "Vapi. often" not in sequence.day8
    assert "two plants in Vapi often" in sequence.day8
    assert followup_subject(sequence.subject) == "Re: Question about Acme's plant jobs"
    assert followup_subject("Re: Question about Acme's plant jobs") == "Re: Question about Acme's plant jobs"
