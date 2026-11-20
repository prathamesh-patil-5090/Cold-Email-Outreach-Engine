from outreach.assemble import assemble_leads
from outreach.columns import VALID_MARK
from outreach.verify import apply_verification, check_email, load_disposable_domains, verify_leads
from outreach.verify import VerificationResult

from tests.test_sheet_grid import lead


def test_disposable_and_syntax_fail_without_dns():
    disposable = load_disposable_domains(load_settings_root())
    bad = check_email("not-an-email", disposable=disposable)
    assert not bad.ok and not bad.retryable
    burned = check_email("person@mailinator.com", disposable=disposable)
    assert not burned.ok
    assert "disposable" in burned.detail
    own = check_email("p.patil@pratz.is-a.dev", disposable=disposable)
    assert "outreach domain" in own.detail


def test_valid_result_is_stored_in_notes_not_a_new_column():
    row = lead(
        lead_id="LEAD-057",
        research_status="Done",
        outreach_status="Queued",
        email="Asha@Acme.in",
        notes="Researched Nov 20; https://acme.in; named inbox",
    )
    apply_verification(
        row,
        VerificationResult(True, "asha@acme.in", "named inbox, mx=aspmx.l.google.com"),
    )
    assert row.text("email") == "asha@acme.in"
    assert VALID_MARK in row.text("notes")
    assert row.status == "Queued"
    assert "email_verified" not in row.values


def test_invalid_queued_row_is_not_left_sendable():
    row = lead(lead_id="LEAD-058", outreach_status="Queued", email="a@mailinator.com")
    verify_leads([row], disposable={"mailinator.com"})
    assert row.status == "Invalid Email"
    assert "Email check: INVALID" in row.text("notes")


def test_blank_email_waits_for_the_bot():
    row = lead(lead_id="LEAD-059", outreach_status="Queued", research_status="Done")
    summary = verify_leads([row], disposable=set())
    assert summary.checked == []
    assert summary.waiting == 1
    assert row.status == "Queued"
    assert row.dirty == set()


def test_sent_rows_are_not_rechecked():
    row = lead(
        lead_id="LEAD-002",
        outreach_status="Sent - Day 0",
        email="info@prime-dental.in",
    )
    summary = verify_leads([row], disposable=set())
    assert summary.checked == []
    assert row.status == "Sent - Day 0"


def test_assemble_waits_until_research_fields_exist_and_does_not_overwrite():
    waiting = lead(
        lead_id="LEAD-057",
        research_status="Done",
        outreach_status="Queued",
        company="Acme",
        first_name="Asha",
    )
    done = lead(
        lead_id="LEAD-002",
        research_status="Done",
        outreach_status="Sent - Day 0",
        company="Prime Dental Products Pvt. Ltd.",
        first_name="Bharat",
        trigger="in-house production of 70+ dental formulations for 500+ dealers",
        handoff="distributor orders and finished stock coordinated back to dispatch",
        topic="distributor orders",
        subject="Question about Prime Dental Products Pvt. Ltd.'s distributor orders",
        day0="already sent",
    )
    ready = lead(
        lead_id="LEAD-060",
        research_status="Done",
        outreach_status="Queued",
        company="Acme Pvt. Ltd.",
        first_name="Asha",
        trigger="two units in Wagle Estate.",
        handoff="jobs moving from the shop floor to dispatch",
        topic="fabrication jobs",
    )
    summary = assemble_leads([waiting, done, ready])
    assert waiting.lead_id in {item[0] for item in summary.waiting}
    assert waiting.text("subject") == ""
    assert done.text("day0") == "already sent"
    assert ready.lead_id in summary.assembled
    assert ready.text("subject") == "Question about Acme Pvt. Ltd.'s fabrication jobs"
    assert "two units in Wagle Estate and was curious" in ready.text("day0")


def load_settings_root():
    from outreach.config import project_root

    return project_root() / "config" / "disposable_domains.txt"
