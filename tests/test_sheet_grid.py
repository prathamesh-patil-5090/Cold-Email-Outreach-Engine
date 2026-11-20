from outreach.columns import COLUMN_KEYS
from outreach.models import Lead, parse_grid


def lead(row=7, **fields) -> Lead:
    values = {key: "" for key in COLUMN_KEYS}
    values.update(fields)
    return Lead(row_number=row, values=values, present=set(COLUMN_KEYS))


HEADERS = [
    "Lead ID",
    "Research Status",
    "Outreach Status",
    "Assigned Sender Email",
    "Company Name",
    "Contact First Name",
    "Contact Email",
    "Industry / Segment",
    "Verified Trigger",
    "Workflow Handoff",
    "Short Workflow Topic",
    "Subject Line",
    "Day 0 Email",
    "Day 4 Follow-up 1",
    "Day 8 Follow-up 2",
    "Day 14 Close Loop",
    "Message-ID",
    "Last Action Date",
    "Next Action Date",
    "Notes",
]


def test_header_below_the_dashboard_is_found():
    grid = [
        ["B2B Outreach & Grok Bot Sequence Tracker"],
        ["TOTAL PROSPECTS"],
        [],
        [],
        [],
        HEADERS,
        ["LEAD-057", "Done", "Queued", "", "Acme Pvt. Ltd.", "Asha", "asha@acme.in"],
    ]
    data = parse_grid(grid)
    assert data.ready
    assert data.header_row == 6
    assert data.leads[0].lead_id == "LEAD-057"
    assert data.leads[0].row_number == 7
    assert data.leads[0].text("trigger") == ""
    assert "Subject Line" not in data.absent


def test_missing_header_waits_without_inventing_leads():
    data = parse_grid([["Company"], ["Acme"]])
    assert not data.ready
    assert data.leads == []
    assert "Lead ID" in data.absent


def test_partial_headers_are_reported():
    data = parse_grid([["Lead ID", "Contact Email"], ["LEAD-057", "a@b.in"]])
    assert data.ready
    assert len(data.leads) == 1
    assert "Verified Trigger" in data.absent
    assert "Notes" in data.absent


def test_blank_gap_does_not_end_the_sheet():
    grid = [HEADERS, ["LEAD-001", "Done", "Sent - Day 0"], [], ["LEAD-003", "Done", "Queued"]]
    data = parse_grid(grid)
    assert [item.lead_id for item in data.leads] == ["LEAD-001", "LEAD-003"]
