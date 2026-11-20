"""Syntax, MX, and disposable-domain checks via python-email-validator.

There is no Email_Verified column on the tracker. Results are written into
Notes, and a hard failure moves Outreach Status to "Invalid Email". A blank
email is left alone so a row the Grok bot has not finished is not rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from email_validator import EmailNotValidError, caching_resolver, validate_email

from outreach.columns import DAY0_STATUSES, INVALID_MARK, VALID_MARK
from outreach.models import Lead

GENERIC_LOCALS = {
    "accounts",
    "admin",
    "contact",
    "enquiries",
    "enquiry",
    "hello",
    "info",
    "mail",
    "marketing",
    "office",
    "operations",
    "sales",
    "service",
    "support",
    "team",
}

OWN_DOMAINS = {"pratz.is-a.dev", "prathameshpatil.is-a.dev"}

RETRYABLE_SNIPPETS = ("timed out", "timeout", "temporary", "try again", "servfail")


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    normalized: str
    detail: str
    retryable: bool = False


@dataclass
class VerifySummary:
    checked: list[str]
    valid: list[str]
    invalid: list[str]
    retryable: list[tuple[str, str]]
    waiting: int


def load_disposable_domains(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    domains: set[str] = set()
    for line in path.read_text().splitlines():
        line = line.strip().casefold()
        if not line or line.startswith("#"):
            continue
        domains.add(line)
    return domains


def clean_email(value: str) -> str:
    text = value.strip()
    if text.casefold().startswith("mailto:"):
        text = text[7:]
    return text.strip().strip("<>").strip()


def needs_verification(lead: Lead) -> bool:
    email = clean_email(lead.text("email"))
    if not email:
        return False
    status = lead.status_key
    if status not in DAY0_STATUSES and status != "":
        return False
    notes = lead.text("notes")
    if VALID_MARK in notes or INVALID_MARK in notes:
        return False
    return True


def check_email(
    email: str,
    *,
    disposable: set[str],
    resolver=None,
    validator=validate_email,
) -> VerificationResult:
    address = clean_email(email)
    if "@" not in address:
        try:
            validator(address, check_deliverability=False, allow_smtputf8=False)
        except EmailNotValidError as exc:
            return VerificationResult(False, address, str(exc), retryable=False)
        return VerificationResult(False, address, "not an email address", retryable=False)

    domain = address.rsplit("@", 1)[1].casefold().rstrip(".")
    local = address.split("@", 1)[0].casefold()
    if domain in OWN_DOMAINS:
        return VerificationResult(False, address, "address is on an outreach domain", retryable=False)
    if domain in disposable:
        return VerificationResult(False, address, f"disposable domain {domain}", retryable=False)

    try:
        info = validator(
            address,
            check_deliverability=True,
            allow_smtputf8=False,
            dns_resolver=resolver,
        )
    except EmailNotValidError as exc:
        message = str(exc)
        retryable = any(snippet in message.casefold() for snippet in RETRYABLE_SNIPPETS)
        return VerificationResult(False, address, message, retryable=retryable)

    mx_host = _mx_host(info)
    kind = f"generic {local}@" if local in GENERIC_LOCALS else "named inbox"
    detail = f"{kind}, mx={mx_host}" if mx_host else kind
    return VerificationResult(True, info.normalized, detail, retryable=False)


def apply_verification(lead: Lead, result: VerificationResult) -> None:
    if result.retryable:
        return
    if result.ok:
        if result.normalized and result.normalized != lead.text("email"):
            lead.set_field("email", result.normalized)
        lead.set_field("notes", _append(lead.text("notes"), f"{VALID_MARK} ({result.detail})"))
        return
    lead.set_field("notes", _append(lead.text("notes"), f"{INVALID_MARK} ({result.detail})"))
    if lead.status_key in DAY0_STATUSES or lead.status_key == "":
        lead.set_field("outreach_status", "Invalid Email")


def verify_leads(
    leads: list[Lead],
    *,
    disposable: set[str],
    resolver=None,
) -> VerifySummary:
    summary = VerifySummary(checked=[], valid=[], invalid=[], retryable=[], waiting=0)
    for lead in leads:
        if not needs_verification(lead):
            if lead.lead_id and not clean_email(lead.text("email")) and (
                lead.status_key in DAY0_STATUSES or lead.status_key == ""
            ):
                summary.waiting += 1
            continue
        result = check_email(lead.text("email"), disposable=disposable, resolver=resolver)
        summary.checked.append(lead.lead_id)
        if result.retryable:
            summary.retryable.append((lead.lead_id, result.detail))
            continue
        apply_verification(lead, result)
        if result.ok:
            summary.valid.append(lead.lead_id)
        else:
            summary.invalid.append(lead.lead_id)
    return summary


def default_resolver():
    return caching_resolver(timeout=10)


def _mx_host(info: object) -> str:
    records = getattr(info, "mx", None) or []
    if not records:
        return ""
    first = records[0]
    if isinstance(first, (tuple, list)) and len(first) >= 2:
        return str(first[1]).rstrip(".")
    return str(first).rstrip(".")


def _append(existing: str, clause: str) -> str:
    if clause in existing:
        return existing
    existing = existing.strip()
    if not existing:
        return clause
    return f"{existing}; {clause}"
