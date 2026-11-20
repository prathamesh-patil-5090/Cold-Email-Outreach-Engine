from outreach.qa import check_research, check_sequence
from outreach.templates import DAY0_STRUCTURES, SUBJECT_VARIANTS, followup_subject, render_sequence

COMPANY = "Prime Dental Products Pvt. Ltd."
TRIGGER = "in-house production of 70+ dental formulations for 500+ dealers"
HANDOFF = "distributor orders and finished stock coordinated back to dispatch"
TOPIC = "distributor orders"

CLASSIC_DAY0 = DAY0_STRUCTURES[0].format(
    first_name="Bharat",
    company=COMPANY,
    trigger=TRIGGER,
    topic=TOPIC,
    day0_signature="Best,\nPrathamesh Patil\npratz.is-a.dev",
)


def test_three_day0_structures_are_visibly_different():
    bodies = [
        DAY0_STRUCTURES[index].format(
            first_name="Bharat",
            company=COMPANY,
            trigger=TRIGGER,
            topic=TOPIC,
            day0_signature="Best,\nPrathamesh Patil\npratz.is-a.dev",
        )
        for index in range(3)
    ]
    assert bodies[0] != bodies[1] != bodies[2]
    assert "I came across" in bodies[0]
    assert "Prathamesh here" in bodies[1]
    assert "I was reading about" in bodies[2]
    assert bodies[0].count("\n\n") == 3
    assert bodies[1].count("\n\n") >= 4
    assert bodies[2].count("\n\n") >= 4


def test_classic_structure_matches_live_sheet_voice():
    assert "I'm Prathamesh, a software developer helping businesses simplify operations" in CLASSIC_DAY0
    assert "was curious how your team currently tracks distributor orders" in CLASSIC_DAY0
    assert "is that handled in one system today" in CLASSIC_DAY0
    assert CLASSIC_DAY0.endswith("pratz.is-a.dev")


def test_all_structures_pass_qa_and_keep_required_fields():
    seen = set()
    for lead_id in (f"LEAD-{n:03d}" for n in range(57, 90)):
        sequence = render_sequence(
            company=COMPANY,
            first_name="Bharat",
            trigger=TRIGGER,
            handoff=HANDOFF,
            topic=TOPIC,
            lead_id=lead_id,
        )
        seen.add(sequence.variant_key.split("-")[1])  # d0s0 / d0s1 / d0s2
        assert sequence.day0.startswith("Hi Bharat,\n\n")
        assert COMPANY in sequence.day0
        assert TOPIC in sequence.day0 or TOPIC in sequence.subject
        assert TRIGGER in sequence.day0
        assert "http" not in sequence.day0
        assert check_sequence(sequence, company=COMPANY, first_name="Bharat", topic=TOPIC).ok
        assert sequence.subject in {
            variant.format(company=COMPANY, topic=TOPIC) for variant in SUBJECT_VARIANTS
        }
    assert {"d0s0", "d0s1", "d0s2"} <= seen


def test_same_lead_id_is_stable():
    a = render_sequence(
        company=COMPANY,
        first_name="Bharat",
        trigger=TRIGGER,
        handoff=HANDOFF,
        topic=TOPIC,
        lead_id="LEAD-057",
    )
    b = render_sequence(
        company=COMPANY,
        first_name="Bharat",
        trigger=TRIGGER,
        handoff=HANDOFF,
        topic=TOPIC,
        lead_id="LEAD-057",
    )
    assert a == b


def test_trailing_period_on_a_research_field_is_removed():
    sequence = render_sequence(
        company="Acme",
        first_name="Asha",
        trigger="two plants in Vapi.",
        handoff="jobs moving to dispatch.",
        topic="plant jobs.",
        lead_id="LEAD-PERIOD",
    )
    assert "Vapi. often" not in sequence.day8
    assert "two plants in Vapi" in sequence.day0
    assert followup_subject(sequence.subject).startswith("Re: ")


def test_qa_rejects_buzzwords_and_bad_topic():
    bad = check_research(
        company="Acme",
        first_name="Asha",
        trigger="cutting-edge synergy across plants",
        handoff="jobs moving to dispatch",
        topic="Orders",
    )
    assert not bad.ok
    good = check_research(
        company=COMPANY,
        first_name="Bharat",
        trigger=TRIGGER,
        handoff=HANDOFF,
        topic=TOPIC,
    )
    assert good.ok
