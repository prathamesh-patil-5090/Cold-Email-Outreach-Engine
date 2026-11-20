"""Open Brave and collect homepage plus contact/about text.

Playwright drives a separate Brave window. It does not attach to the Brave
profile already in use, so existing tabs stay put.
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

from outreach.config import ConfigError
from outreach.discover import (
    QUERIES,
    EMAIL_RE,
    CapturedPage,
    Prospect,
    Seen,
    blocked,
    consider_site,
    email_hunt_queries,
    host_of,
    named_people,
)

DEFAULT_BRAVE = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

_READ_JS = """() => {
  const h1 = document.querySelector('h1');
  return {
    title: document.title || '',
    h1: h1 ? (h1.innerText || '') : '',
    text: (document.body && document.body.innerText) ? document.body.innerText.slice(0, 8000) : '',
    links: Array.from(document.querySelectorAll('a[href]')).map(a => ({
      href: a.getAttribute('href') || '',
      text: (a.innerText || '').trim().slice(0, 80),
    })),
  };
}"""


def find_prospects(
    seen: Seen,
    *,
    today: str,
    limit: int = 5,
    headless: bool = False,
    queries: tuple[str, ...] | None = None,
) -> list[Prospect]:
    executable = os.environ.get("BRAVE_EXECUTABLE", DEFAULT_BRAVE).strip()
    if not Path(executable).is_file():
        raise ConfigError(
            f"Brave was not found at {executable}. Install Brave, or set BRAVE_EXECUTABLE."
        )
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ConfigError("Playwright is not installed. Run: pip install -e '.[zoho]'") from exc

    wanted = queries or QUERIES
    prospects: list[Prospect] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=headless)
        page = browser.new_page()
        candidates = _search(page, wanted, seen)
        print(f"Search returned {len(candidates)} new company sites.")
        for host, url in candidates:
            if len(prospects) >= limit:
                break
            home, extras = _open_site(page, url)
            if home is None:
                print(f"  drop {host}: homepage did not load")
                continue
            prospect, reason = consider_site(home, extras, seen, today=today)
            if prospect is None:
                print(f"  drop {host}: {reason}")
                continue
            if prospect.email_kind != "personal":
                hunted = _hunt_printed_emails(page, prospect, host, [home, *extras])
                if hunted:
                    prospect, reason = consider_site(home, extras + hunted, seen, today=today)
                    if prospect is None:
                        print(f"  drop {host}: {reason}")
                        continue
            seen = seen.with_prospect(prospect.company, prospect.email, prospect.website)
            prospects.append(prospect)
            print(f"  keep {prospect.company}  {prospect.first_name}  {prospect.email}")
        browser.close()
    return prospects


def _search(page, queries: tuple[str, ...], seen: Seen) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen_hosts: set[str] = set()
    for query in queries:
        url = "https://search.brave.com/search?q=" + urllib.parse.quote(query)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(1400)
        except Exception as exc:
            print(f"Search failed ({query[:60]}): {exc}")
            continue
        links = page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href]')).map(a => ({
              href: a.href || '',
              text: (a.innerText || '').trim().slice(0, 160),
            }))"""
        )
        added = 0
        for link in links:
            href = str(link.get("href") or "")
            host = host_of(href)
            if not host or host in seen_hosts:
                continue
            reason = blocked(host, str(link.get("text") or ""), seen)
            if reason:
                continue
            seen_hosts.add(host)
            found.append((host, href))
            added += 1
            if len(found) >= 30:
                return found
        print(f"Query +{added}  {query[:68]}")
    return found


def _open_site(page, start_url: str) -> tuple[CapturedPage | None, list[CapturedPage]]:
    try:
        page.goto(start_url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(700)
        raw = page.evaluate(_READ_JS)
    except Exception:
        return None, []
    home = CapturedPage(
        url=page.url,
        title=str(raw.get("title") or ""),
        h1=str(raw.get("h1") or ""),
        text=str(raw.get("text") or ""),
    )
    extras: list[CapturedPage] = []
    host = host_of(page.url)
    links = raw.get("links") or []
    for target in _contact_links(page.url, host, links)[:4]:
        try:
            page.goto(target, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(500)
            sub = page.evaluate(_READ_JS)
        except Exception:
            continue
        extras.append(
            CapturedPage(
                url=page.url,
                title=str(sub.get("title") or ""),
                h1=str(sub.get("h1") or ""),
                text=str(sub.get("text") or ""),
            )
        )
    for pdf_url in _pdf_links(page.url, host, links)[:1]:
        brochure = _read_pdf(page, pdf_url)
        if brochure is not None:
            extras.append(brochure)
    return home, extras


def _contact_links(base: str, host: str, links: list[dict]) -> list[str]:
    chosen: list[str] = []
    for link in links:
        href = str(link.get("href") or "")
        text = str(link.get("text") or "")
        blob = f"{href} {text}".lower()
        if not any(word in blob for word in ("contact", "about", "leadership", "director", "team", "brochure", "catalogue", "catalog")):
            continue
        url = urllib.parse.urljoin(base, href)
        if not url.startswith("http"):
            continue
        if host not in host_of(url):
            continue
        if url.lower().endswith(".pdf"):
            continue
        if url not in chosen:
            chosen.append(url)
    return chosen


def _pdf_links(base: str, host: str, links: list[dict]) -> list[str]:
    chosen: list[str] = []
    for link in links:
        href = str(link.get("href") or "")
        url = urllib.parse.urljoin(base, href)
        if not url.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        if host not in host_of(url):
            continue
        if url not in chosen:
            chosen.append(url)
    return chosen


def _read_pdf(page, url: str) -> CapturedPage | None:
    try:
        response = page.context.request.get(url, timeout=20000)
        if not response.ok:
            return None
        raw = response.body().decode("latin-1", errors="ignore")
    except Exception:
        return None
    emails = EMAIL_RE.findall(raw)
    if not emails:
        return None
    return CapturedPage(url=url, title="brochure", h1="", text="\n".join(dict.fromkeys(email.lower() for email in emails)))


def _hunt_printed_emails(
    page, prospect: Prospect, company_host: str, own_pages: list[CapturedPage]
) -> list[CapturedPage]:
    """Open pages that print an address. A directory hit is marked third-party."""
    domain = prospect.email.split("@", 1)[-1]
    names = named_people(own_pages)
    if prospect.first_name not in {name.split()[0] for name in names}:
        names = [prospect.first_name, *names]
    queries = email_hunt_queries(prospect.company, names or [prospect.first_name], domain, prospect.email)
    pages: list[CapturedPage] = []
    for query in queries[:2]:
        url = "https://search.brave.com/search?q=" + urllib.parse.quote(query)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)
            links = page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href || '')"""
            )
        except Exception as exc:
            print(f"  email search failed: {exc}")
            continue
        opened = 0
        for href in links:
            host = host_of(str(href))
            if not host or host == company_host or "search.brave." in host:
                continue
            if any(part in host for part in ("youtube.", "facebook.", "instagram.", "google.")):
                continue
            try:
                page.goto(str(href), wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(500)
                raw = page.evaluate(_READ_JS)
            except Exception:
                continue
            text = str(raw.get("text") or "")
            if not EMAIL_RE.search(text):
                continue
            source = "own" if company_host in host_of(page.url) else "third_party"
            pages.append(
                CapturedPage(
                    url=page.url,
                    title=str(raw.get("title") or ""),
                    h1=str(raw.get("h1") or ""),
                    text=text[:8000],
                    source=source,
                )
            )
            opened += 1
            if opened >= 2 or len(pages) >= 3:
                break
    return pages
