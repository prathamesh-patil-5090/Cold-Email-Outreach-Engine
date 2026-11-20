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
    CapturedPage,
    Prospect,
    Seen,
    blocked,
    consider_site,
    host_of,
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
    for target in _contact_links(page.url, host, raw.get("links") or [])[:2]:
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
    return home, extras


def _contact_links(base: str, host: str, links: list[dict]) -> list[str]:
    chosen: list[str] = []
    for link in links:
        href = str(link.get("href") or "")
        text = str(link.get("text") or "")
        blob = f"{href} {text}".lower()
        if not any(word in blob for word in ("contact", "about", "leadership", "director")):
            continue
        url = urllib.parse.urljoin(base, href)
        if not url.startswith("http"):
            continue
        if host not in host_of(url):
            continue
        if url not in chosen:
            chosen.append(url)
    return chosen
