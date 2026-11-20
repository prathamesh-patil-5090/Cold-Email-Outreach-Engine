from outreach.discover import (
    CapturedPage,
    Seen,
    company_key,
    consider_site,
    email_hunt_queries,
    next_lead_id,
    seen_from_leads,
)
from outreach.qa import check_research
from tests.test_sheet_grid import lead


def test_next_lead_id_follows_the_highest_row():
    leads = [lead(lead_id="LEAD-057"), lead(lead_id="LEAD-071"), lead(lead_id="LEAD-066")]
    assert next_lead_id(leads) == "LEAD-072"
    assert next_lead_id([]) == "LEAD-001"


def test_seen_blocks_company_domain_and_email():
    seen = seen_from_leads(
        [
            lead(
                lead_id="LEAD-031",
                company="Ojass Auto Components Pvt. Ltd.",
                email="office@ojass.co.in",
                notes="Researched Jan 1; https://ojass.co.in/contact; office@ on the site",
            )
        ]
    )
    assert company_key("Ojass Auto Components") in seen.companies
    assert "ojass.co.in" in seen.domains
    assert "office@ojass.co.in" in seen.emails


def test_fabhind_style_page_becomes_a_research_row():
    home = CapturedPage(
        url="https://fabhind.in/",
        title="Asphalt plants - FABHIND",
        h1="FABHIND",
        text=(
            "FABHIND is a manufacturer involved in the manufacturing, supplying and "
            "installation of Asphalt Batch Mix Plant, concrete plants and tyre recycling plants. "
            "We have three manufacturing units in Gujarat. " * 4
        ),
    )
    contact = CapturedPage(
        url="https://fabhind.in/contact.html",
        title="Contact - FABHIND",
        h1="Contact Us",
        text=(
            "Plot no.16, Vatva, GIDC, Ahmedabad.\n"
            "Mr. Ritesh Prajapati\n"
            "sales@fabhind.com\n"
            "UNIT 2 Mehsana address\n"
        ),
    )
    prospect, reason = consider_site(home, [contact], Seen(), today="2026-11-21")
    assert reason == "ok"
    assert prospect is not None
    assert prospect.company == "FABHIND"
    assert prospect.first_name == "Ritesh"
    assert prospect.email == "sales@fabhind.com"
    assert prospect.topic == "plant orders"
    assert "vatva" in prospect.trigger
    assert prospect.row("LEAD-072")[11] == ""
    assert check_research(
        company=prospect.company,
        first_name=prospect.first_name,
        trigger=prospect.trigger,
        handoff=prospect.handoff,
        topic=prospect.topic,
    ).ok


def test_unnamed_inbox_is_dropped():
    home = CapturedPage(
        url="https://example-mfg.in/",
        title="Reliable Works",
        h1="Reliable Works",
        text="We are a manufacturer of crane components at our Vatva GIDC works and sales office. " * 6,
    )
    contact = CapturedPage(
        url="https://example-mfg.in/contact",
        title="Contact",
        h1="Contact",
        text="Email sales@example-mfg.in for the Vatva works and the sales office. No person is named on this contact page.\n",
    )
    prospect, reason = consider_site(home, [contact], Seen(), today="2026-11-21")
    assert prospect is None
    assert "named person" in reason


def test_known_email_is_dropped():
    home = CapturedPage(
        url="https://powerlineindustries.in/",
        title="Powerline Industries",
        h1="Powerline Industries",
        text="Manufacturer of crane components at the Vatva GIDC registered works and sales office. " * 5,
    )
    contact = CapturedPage(
        url="https://powerlineindustries.in/contact_us.php",
        title="Contact us - Powerline Industries",
        h1="Contact us",
        text=(
            "Registered works, Vatva GIDC, Ahmedabad.\n"
            "CONTACT PERSON : MR. ISHWAR PATEL\n"
            "works@powerlineindustries.in\n"
        ),
    )
    seen = Seen(emails=frozenset({"works@powerlineindustries.in"}))
    prospect, reason = consider_site(home, [contact], seen, today="2026-11-21")
    assert prospect is None
    assert "email already" in reason


def test_personal_email_under_a_printed_name_wins():
    home = CapturedPage(
        url="https://www.rgkgroup.net/",
        title="RGK Group of Industries",
        h1="RGK Group of Industries",
        text=(
            "Manufacturer of casting and forging components. "
            "Foundry, forging and machine shop at Lodhika GIDC and Bamanbore GIDC, Rajkot. " * 4
        ),
    )
    contact = CapturedPage(
        url="https://www.rgkgroup.net/contact-us.php",
        title="Contact Us",
        h1="Contact Us",
        text=(
            "mktg@rgkgroup.net\n"
            "Mr. Ramnik Kotecha\n"
            "Email: rgkotecha@rgkgroup.net\n"
            "Mr. Bhavesh Pabari\n"
            "Email: bjpabari@rgkgroup.net\n"
        ),
    )
    prospect, reason = consider_site(home, [contact], Seen(), today="2026-11-21")
    assert reason == "ok"
    assert prospect is not None
    assert prospect.first_name == "Ramnik"
    assert prospect.email == "rgkotecha@rgkgroup.net"
    assert prospect.email_kind == "personal"
    assert prospect.topic == "foundry orders"


def test_personal_address_on_the_company_site_beats_a_shared_inbox():
    home = CapturedPage(
        url="https://aximindia.com/",
        title="Axim India",
        h1="Axim India",
        text=(
            "Axim India is a manufacturer of organic pigment powders and emulsions "
            "at its Vatva GIDC shed and exports them. " * 5
        ),
    )
    contact = CapturedPage(
        url="https://aximindia.com/contact.html",
        title="Contact Us",
        h1="Contact Us",
        text=(
            "Nishant Agrawal\n"
            "(Chairman)\n"
            "E-mail: axim.india@gmail.com\n"
            "Kathan Agrawal\n"
            "(CEO)\n"
            "E-mail: info@aximindia.com\n"
            "Vatva GIDC Ahmedabad\n"
        ),
    )
    prospect, reason = consider_site(home, [contact], Seen(), today="2026-11-21")
    assert reason == "ok"
    assert prospect is not None
    assert prospect.first_name == "Nishant"
    assert prospect.email == "axim.india@gmail.com"
    assert prospect.email_kind == "personal"


def test_directory_personal_email_is_flagged_and_not_used():
    home = CapturedPage(
        url="https://www.shubhamautomation.co.in/",
        title="Shubham Automation",
        h1="Shubham Automation",
        text=(
            "Shubham Automation is a manufacturer of packaging-line machines "
            "at Manufacturing Unit 1 and Manufacturing Unit 2 in Vatva GIDC. " * 4
        ),
    )
    about = CapturedPage(
        url="https://www.shubhamautomation.co.in/about-us/",
        title="About Us",
        h1="About",
        text="Biren Patel\nDirector\nHeaded by Biren Patel, marketing and sales, from the about page of the company.\n",
    )
    contact = CapturedPage(
        url="https://www.shubhamautomation.co.in/contact-us/",
        title="Contact Us",
        h1="Contact",
        text="Business inquiries for the Vatva works.\nEmail: sales@shubhamautomation.co.in\nVatva GIDC, Ahmedabad.\n",
    )
    directory = CapturedPage(
        url="https://directory.aicc.ind.in/shubham-automation-services/",
        title="AICC directory",
        h1="Shubham Automation",
        text="Directory listing. Biren Patel biren@shubhamautomation.co.in. The address on this listing is old.\n",
        source="third_party",
    )
    prospect, reason = consider_site(home, [about, contact, directory], Seen(), today="2026-11-21")
    assert reason == "ok"
    assert prospect is not None
    assert prospect.email == "sales@shubhamautomation.co.in"
    assert prospect.first_name == "Biren"
    assert "biren@shubhamautomation.co.in" not in prospect.email
    assert "Third-party only, not used: biren@shubhamautomation.co.in" in prospect.notes


def test_hunt_queries_do_not_invent_an_address():
    queries = email_hunt_queries(
        "Shubham Automation",
        ["Biren Patel", "Prashant Patel"],
        "shubhamautomation.co.in",
        "sales@shubhamautomation.co.in",
    )
    assert queries
    assert any('"biren@"' in query for query in queries)
    assert all("biren@shubhamautomation.co.in" not in query for query in queries)
