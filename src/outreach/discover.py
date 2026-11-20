"""Find new manufacturers and draft the research columns.

The browser opens pages. This module decides which pages become a row:
dedupe, a named contact on the company's own site, a Maharashtra / Gujarat /
Bengaluru fit, then Verified Trigger, Workflow Handoff, and Short Workflow
Topic. A row is returned only when those three fields pass the copy QA rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from outreach.models import Lead
from outreach.qa import check_research

QUERIES: tuple[str, ...] = (
    "Pune Chakan MIDC manufacturer official website contact email director -indiamart",
    "Ahmedabad Vatva GIDC manufacturer info@ OR sales@ contact director -indiamart",
    "Bhosari Pune fabrication pvt ltd contact director email -indiamart",
    "Vasai manufacturer plant contact director email -indiamart",
    "Vapi GIDC manufacturer contact director email -indiamart",
    "Rajkot foundry manufacturer contact director email -indiamart",
    "Bengaluru Peenya manufacturer contact director email -indiamart",
    "Sanand Gujarat manufacturer contact director email -indiamart",
)

SKIP_HOST_PARTS: tuple[str, ...] = (
    "indiamart.",
    "justdial.",
    "tradeindia.",
    "sulekha.",
    "facebook.",
    "youtube.",
    "instagram.",
    "linkedin.",
    "twitter.",
    "x.com",
    "wikipedia.",
    "google.",
    "brave.com",
    "search.brave.",
    "amazon.",
    "alibaba.",
    "made-in-china.",
    "exportersindia.",
    "zaubacorp.",
    "tofler.",
    "dnb.com",
    "crunchbase.",
    "scribd.",
    "dial4trade.",
    "tracxn.",
    "companydetails.",
    "companydatabase.",
    "falconebiz.",
    "industrialguide.",
    "gujaratdirectory.",
    "hindustanyellowpages.",
    "midcindia.",
    "gidc.co.in",
    "konkanindustrialpublications.",
)

SHARED_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "yahoo.co.in",
    "yahoo.in",
    "rediffmail.com",
    "hotmail.com",
    "outlook.com",
}

AREAS = (
    "vatva",
    "mehsana",
    "chakan",
    "bhosari",
    "lodhika",
    "bamanbore",
    "vapi",
    "sanand",
    "vasai",
    "peenya",
    "ankleshwar",
    "dahej",
    "wagle",
)
CITIES = (
    "ahmedabad",
    "pune",
    "rajkot",
    "vadodara",
    "surat",
    "bengaluru",
    "bangalore",
    "mumbai",
    "thane",
)

# Longer phrases win. These are product words that already appear on real sites.
PRODUCT_PHRASES = (
    "asphalt batch mix plants",
    "asphalt batch mix plant",
    "concrete batching plants",
    "crane components",
    "casting and forging components",
    "castings and forgings",
    "grey cast iron castings",
    "organic pigment powders and emulsions",
    "organic pigment powders",
    "pigment powder",
    "industrial gaskets",
    "rubber moulded parts",
    "packaging-line machines",
    "end of packaging line",
    "pressure vessels",
    "sheet metal stamping",
)

# Printed under a named person, but still a shared inbox.
NAMED_INBOX_LOCALS = {"info", "sales", "contact", "works", "ceo", "director", "md"}
SKIP_LOCALS = {"career", "careers", "hr", "purchase", "webmaster", "noreply", "support", "admin"}
JUNK_EMAIL_PARTS = ("example.com", "wixpress", "sentry.io", "godaddy", "schema.org", "domain.com")
BAD_NAME_TOKENS = {
    "contact",
    "person",
    "email",
    "sales",
    "office",
    "india",
    "gujarat",
    "pune",
    "home",
    "about",
    "limited",
    "private",
    "industries",
    "industry",
    "company",
    "director",
    "chairman",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
MR_RE = re.compile(
    r"(?:contact person\s*:?\s*)?(?:mr|mrs|ms)\.?\s*([A-Za-z][A-Za-z]+(?:\s+[A-Za-z][A-Za-z]+){0,3})",
    re.I,
)
PLAIN_NAME_RE = re.compile(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})$")
ROLE_RE = re.compile(r"\b(ceo|chairman|managing director|director|md)\b", re.I)
UNIT_WORD = {"2": "two", "3": "three", "4": "four", "5": "five", "two": "two", "three": "three", "four": "four"}
COUNT_WORD = {2: "two", 3: "three", 4: "four", 5: "five"}
LEGAL_RE = re.compile(r"\b(pvt\.?|private|ltd\.?|limited|inc\.?|llp|co\.?)\b", re.I)


@dataclass(frozen=True)
class Seen:
    companies: frozenset[str] = field(default_factory=frozenset)
    domains: frozenset[str] = field(default_factory=frozenset)
    emails: frozenset[str] = field(default_factory=frozenset)

    def union(self, other: Seen) -> Seen:
        return Seen(
            companies=self.companies | other.companies,
            domains=self.domains | other.domains,
            emails=self.emails | other.emails,
        )

    def with_prospect(self, company: str, email: str, website: str) -> Seen:
        domains = set(self.domains)
        host = host_of(website)
        if host:
            domains.add(host)
        email_domain = email.split("@", 1)[-1]
        if email_domain not in SHARED_EMAIL_DOMAINS:
            domains.add(email_domain)
        return Seen(
            companies=self.companies | {company_key(company)},
            domains=frozenset(domains),
            emails=self.emails | {email.casefold()},
        )


@dataclass(frozen=True)
class CapturedPage:
    url: str
    title: str
    h1: str
    text: str
    source: str = "own"


@dataclass(frozen=True)
class Prospect:
    company: str
    first_name: str
    email: str
    industry: str
    trigger: str
    handoff: str
    topic: str
    website: str
    notes: str
    email_kind: str = "named"

    def row(self, lead_id: str) -> list[str]:
        """A–T. Subject through Next Action Date stay blank for assemble/send."""
        return [
            lead_id,
            "Done",
            "Queued",
            "",
            self.company,
            self.first_name,
            self.email,
            self.industry,
            self.trigger,
            self.handoff,
            self.topic,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            self.notes,
        ]


def seen_from_leads(leads: list[Lead]) -> Seen:
    companies: set[str] = set()
    domains: set[str] = set()
    emails: set[str] = set()
    for lead in leads:
        key = company_key(lead.text("company"))
        if key:
            companies.add(key)
        email = lead.text("email").casefold()
        if "@" in email:
            emails.add(email)
            domain = email.split("@", 1)[1]
            if domain not in SHARED_EMAIL_DOMAINS:
                domains.add(domain)
        website = _website_from_notes(lead.text("notes"))
        host = host_of(website)
        if host:
            domains.add(host)
    return Seen(frozenset(companies), frozenset(domains), frozenset(emails))


def next_lead_id(leads: list[Lead]) -> str:
    highest = 0
    for lead in leads:
        match = re.fullmatch(r"LEAD-(\d+)", lead.lead_id.strip(), re.I)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"LEAD-{highest + 1:03d}"


def host_of(url: str) -> str:
    match = re.search(r"https?://([^/]+)", url.strip(), re.I)
    if not match:
        return ""
    host = match.group(1).lower()
    if host.startswith("www."):
        host = host[4:]
    return host.split(":")[0]


def company_key(name: str) -> str:
    cleaned = LEGAL_RE.sub(" ", name.casefold())
    return re.sub(r"[^a-z0-9]+", "", cleaned)


def skip_host(host: str) -> bool:
    if not host or "." not in host:
        return True
    return any(part in host for part in SKIP_HOST_PARTS)


def blocked(host: str, title: str, seen: Seen) -> str:
    if skip_host(host):
        return "directory or skipped host"
    if host in seen.domains:
        return "domain already on the tracker"
    key = company_key(title)
    if len(key) >= 6 and key in seen.companies:
        return "company already on the tracker"
    return ""


def consider_site(
    home: CapturedPage,
    extras: list[CapturedPage],
    seen: Seen,
    *,
    today: str,
) -> tuple[Prospect | None, str]:
    if len(home.text.strip()) < 200:
        return None, "homepage did not load"
    loaded_extras = [page for page in extras if len(page.text.strip()) >= 80]
    own_extras = [page for page in loaded_extras if page.source != "third_party"]
    if not own_extras:
        return None, "contact or about page did not load"
    company = company_name(home)
    if not company:
        return None, "company name was not on the page"
    if company_key(company) in seen.companies:
        return None, "company already on the tracker"
    own_pages = [home, *own_extras]
    third_pages = [page for page in loaded_extras if page.source == "third_party"]
    combined = "\n".join(page.text for page in own_pages)
    low = combined.lower()
    if not _has_geo(low):
        return None, "not in Maharashtra, Gujarat, or Bengaluru"
    if not _has_role(low):
        return None, "not a manufacturer, fabricator, oem, or distributor"
    if not _has_multi(low):
        return None, "no multi-plant, multi-step, or dispatch flow"
    pair = _best_pair(own_pages)
    if pair is None:
        pair = _fallback_pair(own_pages)
    if pair is None:
        return None, "no named person with an email on the site"
    first_name, email, pair_note, email_kind = pair
    if email.casefold() in seen.emails:
        return None, "email already on the tracker"
    email_domain = email.split("@", 1)[1]
    if email_domain not in SHARED_EMAIL_DOMAINS and email_domain in seen.domains:
        return None, "domain already on the tracker"
    drafted = _draft_fields(low, combined)
    if drafted is None:
        return None, "could not draft trigger, handoff, and topic from the site"
    trigger, handoff, topic = drafted
    qa = check_research(
        company=company,
        first_name=first_name,
        trigger=trigger,
        handoff=handoff,
        topic=topic,
    )
    if not qa.ok:
        return None, f"research QA: {qa.summary}"
    website = next((page.url for page in own_pages[1:] if page.url), home.url)
    notes = f"Researched {today}; {website}; {pair_note}"
    flagged = _third_party_personal(third_pages, _first_names(own_pages))
    flagged = [item for item in flagged if item != email]
    if flagged:
        notes += "; Third-party only, not used: " + ", ".join(flagged)
    return (
        Prospect(
            company=company,
            first_name=first_name,
            email=email,
            industry="Manufacturers",
            trigger=trigger,
            handoff=handoff,
            topic=topic,
            website=website,
            notes=notes,
            email_kind=email_kind,
        ),
        "ok",
    )


def company_name(home: CapturedPage) -> str:
    chunks = re.split(r"\s+[|–—]\s+|\s+-\s+", home.title)
    branded = [chunk.strip(" |-") for chunk in chunks if chunk.strip() and not _generic_title(chunk)]
    branded = [chunk for chunk in branded if 1 <= len(chunk.split()) <= 8]
    if branded:
        return branded[-1]
    h1 = " ".join(home.h1.split())
    if h1 and not _generic_title(h1) and 1 <= len(h1.split()) <= 8:
        return h1
    return ""


def _generic_title(text: str) -> bool:
    low = text.strip().casefold()
    if not low:
        return True
    return low.startswith(("contact", "welcome", "home", "about", "best ", "leading "))


def _has_geo(low: str) -> bool:
    if any(re.search(rf"\b{place}\b", low) for place in AREAS + CITIES):
        return True
    return any(word in low for word in ("gujarat", "maharashtra", "gidc", "midc"))


def _has_role(low: str) -> bool:
    return any(
        word in low
        for word in ("manufacturer", "fabricator", "fabrication", "oem", "distributor", "foundry", "forging")
    )


def _has_multi(low: str) -> bool:
    if _unit_count(low) >= 2:
        return True
    if "sales office" in low and "works" in low:
        return True
    if "foundry" in low and ("forg" in low or "machine shop" in low):
        return True
    if "dispatch" in low and any(word in low for word in ("plant", "works", "unit", "factory", "foundry")):
        return True
    if "dealer" in low or "distributor" in low:
        return True
    if "export" in low and "manufactur" in low:
        return True
    if "installation" in low and "manufactur" in low:
        return True
    return False


def _unit_count(low: str) -> int:
    match = re.search(r"\b(two|three|four|five|\d)\s+manufacturing units\b", low)
    if match:
        raw = match.group(1)
        if raw.isdigit():
            return int(raw)
        return {"two": 2, "three": 3, "four": 4, "five": 5}[raw]
    found = set(re.findall(r"manufacturing unit\s*-?\s*(\d+|i{1,3}\b)", low))
    numbers = set()
    for token in found:
        if token.isdigit():
            numbers.add(int(token))
        elif token in {"i", "ii", "iii", "iv"}:
            numbers.add({"i": 1, "ii": 2, "iii": 3, "iv": 4}[token])
    if len(numbers) >= 2:
        return len(numbers)
    return 0


def email_hunt_queries(company: str, names: list[str], domain: str, current_email: str) -> list[str]:
    """Search strings only. This never invents a firstname@domain address."""
    queries: list[str] = []
    if names and current_email:
        first = names[0].split()[0]
        queries.append(f"{company} {first} {current_email} official website contact director email")
    quoted = []
    for name in names[:3]:
        first = name.split()[0].casefold()
        if len(first) >= 3 and first not in BAD_NAME_TOKENS:
            quoted.append(f'"{first}@"')
    if quoted and domain and domain not in SHARED_EMAIL_DOMAINS:
        queries.append(" OR ".join(quoted) + f" {domain}")
    return queries


def named_people(pages: list[CapturedPage]) -> list[str]:
    found: list[str] = []
    for page in pages:
        if page.source == "third_party":
            continue
        for _first, full in _people_on_page(page.text):
            if full not in found:
                found.append(full)
    return found


def _best_pair(pages: list[CapturedPage]) -> tuple[str, str, str, str] | None:
    ranked: list[tuple[int, str, str, str, str]] = []
    for page in pages:
        if page.source == "third_party":
            continue
        for rank, first, email, note in _pairs_on_page(page.text):
            kind = "personal" if rank == 0 else "named"
            ranked.append((rank, first, email, note, kind))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    _rank, first, email, note, kind = ranked[0]
    return first, email, note, kind


def _fallback_pair(pages: list[CapturedPage]) -> tuple[str, str, str, str] | None:
    """General inbox on the site, plus a decision-maker named somewhere on the site."""
    people: list[tuple[str, str]] = []
    emails: list[str] = []
    for page in pages:
        if page.source == "third_party":
            continue
        for person in _people_on_page(page.text):
            if person not in people:
                people.append(person)
        for line in page.text.splitlines():
            for email in _emails_in(line):
                if email.split("@", 1)[0] in NAMED_INBOX_LOCALS and email not in emails:
                    emails.append(email)
    if not people or not emails:
        return None
    order = ["sales", "info", "contact", "works", "ceo", "director", "md"]
    emails.sort(key=lambda email: order.index(email.split("@", 1)[0]) if email.split("@", 1)[0] in order else 99)
    email = emails[0]
    first, full = people[0]
    local = email.split("@", 1)[0]
    return first, email, f"{local}@ on the site; first name {full} from the site", "general"


def _pairs_on_page(text: str) -> list[tuple[int, str, str, str]]:
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    found: list[tuple[int, str, str, str]] = []
    for index, line in enumerate(rows):
        emails = _emails_in(line)
        if not emails:
            continue
        named = _nearest_name(rows, index)
        if named is None:
            continue
        first, full = named
        for email in emails:
            rank = _email_rank(email, full)
            if rank is None:
                continue
            local = email.split("@", 1)[0]
            found.append((rank, first, email, f"{local}@ listed under {full}"))
    return found


def _emails_in(line: str) -> list[str]:
    found = []
    for raw in EMAIL_RE.findall(line):
        email = raw.strip(".").lower()
        if any(part in email for part in JUNK_EMAIL_PARTS):
            continue
        if email.endswith((".png", ".jpg", ".jpeg", ".svg", ".webp")):
            continue
        if email not in found:
            found.append(email)
    return found


def _nearest_name(rows: list[str], email_index: int) -> tuple[str, str] | None:
    start = max(0, email_index - 8)
    for index in range(email_index - 1, start - 1, -1):
        line = rows[index]
        match = MR_RE.search(line)
        if match:
            named = _clean_person(match.group(1))
            if named:
                return named
        plain = PLAIN_NAME_RE.match(line)
        if not plain:
            continue
        neighbors = []
        if index + 1 < len(rows):
            neighbors.append(rows[index + 1])
        if index - 1 >= 0:
            neighbors.append(rows[index - 1])
        if any(ROLE_RE.search(neighbor) for neighbor in neighbors):
            named = _clean_person(plain.group(1))
            if named:
                return named
    return None


def _clean_person(raw: str) -> tuple[str, str] | None:
    tokens = [token for token in re.split(r"\s+", raw.strip()) if token]
    if not tokens or len(tokens) > 4:
        return None
    if any(token.casefold() in BAD_NAME_TOKENS for token in tokens):
        return None
    first = tokens[0].capitalize()
    full = " ".join(token.capitalize() for token in tokens)
    if len(first) < 3:
        return None
    return first, full


def _email_rank(email: str, full_name: str) -> int | None:
    """0 = personal address printed under a person. 1 = shared inbox printed under a person.

    full_name is part of the call so a future check can require the local part
    to contain the name. An address is personal when the site prints it under
    someone and it is not a shared inbox. Nothing here invents firstname@domain.
    """
    del full_name
    local = email.split("@", 1)[0].lower()
    if local in SKIP_LOCALS:
        return None
    if local in NAMED_INBOX_LOCALS:
        return 1
    return 0


def _people_on_page(text: str) -> list[tuple[str, str]]:
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    found: list[tuple[str, str]] = []
    for index, line in enumerate(rows):
        match = MR_RE.search(line)
        named = _clean_person(match.group(1)) if match else None
        if named is None:
            plain = PLAIN_NAME_RE.match(line)
            if plain:
                neighbors = []
                if index + 1 < len(rows):
                    neighbors.append(rows[index + 1])
                if index - 1 >= 0:
                    neighbors.append(rows[index - 1])
                if any(ROLE_RE.search(neighbor) for neighbor in neighbors):
                    named = _clean_person(plain.group(1))
        if named and named not in found:
            found.append(named)
    return found


def _first_names(pages: list[CapturedPage]) -> set[str]:
    return {first.casefold() for first, _full in (person for page in pages for person in _people_on_page(page.text))}


def _third_party_personal(pages: list[CapturedPage], first_names: set[str]) -> list[str]:
    found: list[str] = []
    for page in pages:
        if page.source != "third_party":
            continue
        for line in page.text.splitlines():
            for email in _emails_in(line):
                local = re.sub(r"[^a-z0-9]", "", email.split("@", 1)[0].lower())
                if local in NAMED_INBOX_LOCALS or local in SKIP_LOCALS:
                    continue
                personal = any(len(name) >= 3 and name in local for name in first_names)
                if personal and email not in found:
                    found.append(email)
    return found


def _draft_fields(low: str, original: str) -> tuple[str, str, str] | None:
    product = _product(low, original)
    places = _places(low)
    units = _unit_count(low)
    if not product or not places:
        return None
    trigger = _trigger(product, places, units)
    handoff = _handoff(low, places, units)
    topic = _topic(product)
    if not trigger or not handoff or not topic:
        return None
    return trigger, handoff, topic


def _product(low: str, original: str) -> str:
    for phrase in sorted(PRODUCT_PHRASES, key=len, reverse=True):
        if phrase in low or phrase in original.lower():
            return phrase
    match = re.search(
        r"(?:manufacturer|fabricator|supplier)(?:\s+(?:and|&)\s+[a-z]+){0,3}\s+of\s+([^.\n]{4,90})",
        low,
    )
    if not match:
        return ""
    chunk = match.group(1)
    chunk = re.split(r"\b(?:that|which|with|for|from|available|who)\b", chunk, maxsplit=1)[0]
    chunk = chunk.split(",")[0]
    words = [word for word in chunk.split() if word not in {"the", "a", "an", "our", "your"}][:6]
    if len(words) < 2:
        return ""
    phrase = " ".join(words).strip(" -")
    if any(bad in phrase for bad in ("solution", "quality", "leading", "region", "customer")):
        return ""
    return phrase


def _places(low: str) -> list[str]:
    areas = [place for place in AREAS if re.search(rf"\b{place}\b", low)]
    if areas:
        return areas
    return [place for place in CITIES if re.search(rf"\b{place}\b", low)]


def _trigger(product: str, places: list[str], units: int) -> str:
    if units >= 2 and len(places) >= 2:
        text = f"{product} built across {units} manufacturing units in {places[0]} and {places[1]}"
    elif units >= 2:
        text = f"{product} built across {units} manufacturing units in {places[0]}"
    elif len(places) >= 2:
        text = f"{product} at its {places[0]} and {places[1]} plants"
    else:
        text = f"{product} made at its {places[0]} works"
    words = text.split()
    if len(words) > 28:
        return ""
    if len(words) < 4:
        return ""
    return text


def _handoff(low: str, places: list[str], units: int) -> str:
    if "sales office" in low and "works" in low:
        return f"orders moving from the {places[0]} works to the sales office for dispatch"
    if "foundry" in low and "machine shop" in low:
        return "jobs moving from the foundry through the machine shop to dispatch"
    if len(places) >= 2:
        return f"jobs moving between the {places[0]} and {places[1]} units before dispatch"
    if units >= 2:
        word = COUNT_WORD.get(units, str(units))
        return f"jobs moving between the {word} {places[0]} units before dispatch"
    if "export" in low:
        return f"orders moving from the {places[0]} works out for export dispatch"
    if "installation" in low:
        return f"finished jobs moving from the {places[0]} works out for site installation"
    if "dispatch" in low:
        return f"orders moving from the {places[0]} works out for dispatch"
    return ""


def _topic(product: str) -> str:
    low = product.lower()
    if "crane" in low:
        return "crane orders"
    if "pigment" in low:
        return "pigment orders"
    if "gasket" in low:
        return "gasket orders"
    if any(word in low for word in ("casting", "forging", "foundry")):
        return "foundry orders"
    if "plant" in low:
        return "plant orders"
    if "packaging" in low:
        return "packaging orders"
    if "machine" in low:
        return "machine orders"
    if "component" in low:
        return "component orders"
    if "vessel" in low:
        return "vessel orders"
    head = low.split()[0] if low else ""
    if head.isalpha() and len(head) > 3:
        return f"{head} orders"
    return ""


def _website_from_notes(notes: str) -> str:
    match = re.search(r"https?://\S+", notes)
    if not match:
        return ""
    return match.group(0).rstrip(";,.")
