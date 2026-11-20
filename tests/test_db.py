from outreach.config import load_settings
from outreach.db import _lead_payload
from tests.test_sheet_grid import lead


def test_lead_payload_maps_sheet_fields():
    settings = load_settings()
    row = lead(
        lead_id="LEAD-057",
        research_status="Done",
        outreach_status="Queued",
        company="Acme",
        first_name="Asha",
        email="asha@acme.in",
        trigger="two plants",
        handoff="jobs to dispatch",
        topic="plant jobs",
        subject="Question about Acme's plant jobs",
        day0="body",
        last_action="2026-11-20",
        next_action="2026-11-26",
        notes="Researched",
    )
    payload = _lead_payload(settings, row)
    assert payload["lead_id"] == "LEAD-057"
    assert payload["company_name"] == "Acme"
    assert payload["contact_email"] == "asha@acme.in"
    assert payload["verified_trigger"] == "two plants"
    assert payload["subject_line"] == "Question about Acme's plant jobs"
    assert str(payload["last_action_date"]) == "2026-11-20"
    assert "LEAD-057" in payload["raw"]
