#!/usr/bin/env python3
"""Log into each outreach Zoho mailbox and generate an app password.

Uses one shared web login password (ZOHO_LOGIN_PASSWORD) for all seven
outreach addresses. Opens a visible Chromium window so you can complete MFA
or CAPTCHA if Zoho asks. Writes each app password into .env.

Usage:
  pip install playwright
  playwright install chromium
  # in .env:
  #   ZOHO_LOGIN_PASSWORD=your-shared-zoho-password
  #   ZOHO_ACCOUNTS_HOST=accounts.zoho.in   # optional; default for India
  python scripts/fetch_zoho_app_passwords.py
  python scripts/fetch_zoho_app_passwords.py --only p.patil@pratz.is-a.dev
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from outreach.config import load_settings  # noqa: E402

APP_LABEL = "outreach-engine-smtp"
PASSWORD_RE = re.compile(r"\b([A-Za-z0-9]{4}\s+[A-Za-z0-9]{4}\s+[A-Za-z0-9]{4})\b")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Zoho app passwords for outreach mailboxes.")
    parser.add_argument("--only", action="append", default=[], help="Limit to one or more mailbox emails")
    parser.add_argument("--headed", action="store_true", default=True, help="Show the browser (default)")
    parser.add_argument("--headless", action="store_true", help="Run without a visible window")
    parser.add_argument("--dry-run", action="store_true", help="Log in and open App Passwords, do not generate")
    parser.add_argument("--pause-seconds", type=int, default=120, help="Seconds to wait if MFA is needed")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    settings = load_settings(ROOT)
    login_password = os.environ.get("ZOHO_LOGIN_PASSWORD", "").strip()
    if not login_password:
        print("Set ZOHO_LOGIN_PASSWORD in .env to the shared Zoho web login password.")
        return 2

    host = os.environ.get("ZOHO_ACCOUNTS_HOST", "accounts.zoho.in").strip().rstrip("/")
    if host.startswith("http"):
        accounts = host
    else:
        accounts = f"https://{host}"

    mailboxes = list(settings.mailboxes)
    if args.only:
        wanted = {item.casefold() for item in args.only}
        mailboxes = [box for box in mailboxes if box.email.casefold() in wanted]
        missing = wanted - {box.email.casefold() for box in mailboxes}
        if missing:
            print("Unknown mailbox(es): " + ", ".join(sorted(missing)))
            return 2

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install Playwright first:\n  pip install playwright\n  playwright install chromium")
        return 2

    results: dict[str, str] = {}
    failures: list[tuple[str, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=bool(args.headless))
        for box in mailboxes:
            print(f"\n=== {box.email} ===")
            context = browser.new_context()
            page = context.new_page()
            try:
                _sign_in(page, accounts, box.email, login_password, args.pause_seconds)
                password = _create_app_password(
                    page,
                    accounts,
                    label=f"{APP_LABEL}-{box.email.split('@')[0]}",
                    dry_run=args.dry_run,
                    pause_seconds=args.pause_seconds,
                )
                if password:
                    results[box.password_env] = password.replace(" ", "")
                    print(f"Got app password for {box.email} → {box.password_env}")
                elif args.dry_run:
                    print(f"Dry run reached App Passwords for {box.email}")
                else:
                    failures.append((box.email, "could not read generated password"))
            except PlaywrightTimeout as exc:
                shot = ROOT / "data" / f"zoho-fail-{box.email.replace('@', '_at_')}.png"
                shot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
                failures.append((box.email, f"timeout: {exc}; screenshot {shot.name}"))
                print(f"Failed {box.email}: timeout (see {shot})")
            except Exception as exc:  # keep going through the other mailboxes
                shot = ROOT / "data" / f"zoho-fail-{box.email.replace('@', '_at_')}.png"
                shot.parent.mkdir(parents=True, exist_ok=True)
                try:
                    page.screenshot(path=str(shot), full_page=True)
                except Exception:
                    pass
                failures.append((box.email, str(exc)))
                print(f"Failed {box.email}: {exc}")
            finally:
                context.close()
                time.sleep(1.5)
        browser.close()

    if results and not args.dry_run:
        env_path = ROOT / ".env"
        _write_env_passwords(env_path, results)
        print(f"\nUpdated {len(results)} password(s) in {env_path}")

    if failures:
        print("\nFailures:")
        for email, detail in failures:
            print(f"  {email}: {detail}")
        return 1
    return 0


def _sign_in(page, accounts: str, email: str, password: str, pause_seconds: int) -> None:
    page.goto(f"{accounts}/signin", wait_until="domcontentloaded", timeout=60000)
    _fill_first(page, ['input[name="LOGIN_ID"]', 'input[id="login_id"]', 'input[type="email"]'], email)
    _click_first(page, ['button#nextbtn', 'button:has-text("Next")', 'input#nextbtn'])
    page.wait_for_timeout(800)
    _fill_first(page, ['input[name="PASSWORD"]', 'input[id="password"]', 'input[type="password"]'], password)
    _click_first(page, ['button#nextbtn', 'button:has-text("Sign in")', 'input#nextbtn'])
    page.wait_for_timeout(2000)
    if _needs_human(page):
        print(
            f"  Zoho needs MFA/CAPTCHA for {email}. Complete it in the browser window. "
            f"Waiting up to {pause_seconds}s…"
        )
        deadline = time.time() + pause_seconds
        while time.time() < deadline:
            if not _needs_human(page) and ("accounts.zoho" in page.url and "signin" not in page.url):
                break
            if "/home" in page.url or "mail.zoho" in page.url:
                break
            page.wait_for_timeout(1500)
        else:
            raise RuntimeError("timed out waiting for MFA/CAPTCHA")


def _create_app_password(page, accounts: str, *, label: str, dry_run: bool, pause_seconds: int) -> str | None:
    # Exact Zoho India deep link: https://accounts.zoho.in/home#security/app_password
    target = f"{accounts}/home#security/app_password"
    page.goto(target, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    if "signin" in page.url:
        raise RuntimeError("still on sign-in after opening App Passwords")

    # Zoho keeps a hidden <span>Generate New Password</span> in the DOM. Prefer the
    # visible "+ Generate New Password" control inside Application-Specific Passwords.
    _ensure_app_password_section(page, accounts)
    if dry_run:
        print("  App Passwords section is open (dry run).")
        return None

    if _needs_human(page):
        print(f"  Extra verification required. Waiting up to {pause_seconds}s…")
        deadline = time.time() + pause_seconds
        while time.time() < deadline and _needs_human(page):
            page.wait_for_timeout(1500)

    _click_generate_new_password(page)
    page.wait_for_timeout(1000)

    name_input = page.locator(
        'div[role="dialog"] input[type="text"], '
        'input[placeholder*="Application" i], input[placeholder*="app" i], '
        'input[aria-label*="Application" i], input[type="text"]:visible'
    ).first
    name_input.wait_for(state="visible", timeout=15000)
    name_input.click()
    name_input.fill("")
    name_input.type(label, delay=20)

    confirm = page.locator(
        'div[role="dialog"] button:has-text("Generate"), '
        'button:has-text("Generate"), button:has-text("Create")'
    ).first
    confirm.click(timeout=15000)

    password = _wait_for_generated_password(page, pause_seconds=pause_seconds)
    if password:
        return password
    raise RuntimeError(
        "generated password not found. Zoho only shows it once — "
        "if a new row appeared in the list, revoke it and re-run."
    )


def _ensure_app_password_section(page, accounts: str) -> None:
    target = f"{accounts}/home#security/app_password"
    # Click the left-nav item when present; hash routes are flaky alone.
    for text in ("App Passwords", "App passwords"):
        nav = page.get_by_text(text, exact=True)
        try:
            if nav.count() and nav.first.is_visible():
                nav.first.click(timeout=5000)
                page.wait_for_timeout(1000)
                break
        except Exception:
            continue
    if "app_password" not in page.url:
        page.goto(target, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

    heading = page.get_by_text("Application-Specific Passwords", exact=False)
    try:
        heading.first.scroll_into_view_if_needed(timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(500)


def _click_generate_new_password(page) -> None:
    candidates = [
        page.locator("a", has_text=re.compile(r"Generate New Password", re.I)),
        page.locator("button", has_text=re.compile(r"Generate New Password", re.I)),
        page.locator("div, span, p", has_text=re.compile(r"^\+?\s*Generate New Password\s*$", re.I)),
        page.get_by_text("+ Generate New Password", exact=False),
        page.get_by_text("Generate New Password", exact=False),
    ]
    last_error: Exception | None = None
    for group in candidates:
        count = min(group.count(), 8)
        for index in range(count):
            item = group.nth(index)
            try:
                item.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            try:
                if item.is_visible():
                    item.click(timeout=8000)
                    return
            except Exception as exc:
                last_error = exc
        # Hidden duplicate spans: force-click the last match's parent if needed.
        if count:
            try:
                group.nth(count - 1).click(force=True, timeout=5000)
                return
            except Exception as exc:
                last_error = exc
    raise RuntimeError(f"could not click Generate New Password: {last_error}")


def _wait_for_generated_password(page, *, pause_seconds: int) -> str | None:
    deadline = time.time() + max(pause_seconds, 30)
    while time.time() < deadline:
        if _needs_human(page):
            print("  Zoho asked to re-authenticate. Complete it in the browser window…")
        match = _read_password_from_page(page)
        if match:
            return match
        page.wait_for_timeout(750)
    return _read_password_from_page(page)


def _read_password_from_page(page) -> str | None:
    scopes = [
        'div[role="dialog"]',
        '[class*="modal" i]',
        '[class*="popup" i]',
        '[class*="password" i]',
        "code",
        "pre",
        "body",
    ]
    for selector in scopes:
        try:
            locator = page.locator(selector).first
            if not locator.count():
                continue
            text = locator.inner_text(timeout=1500)
        except Exception:
            continue
        match = PASSWORD_RE.search(text or "")
        if match:
            return match.group(1)
    return None


def _needs_human(page) -> bool:
    text = ""
    try:
        text = page.inner_text("body").casefold()
    except Exception:
        return False
    markers = (
        "verify your identity",
        "enter the otp",
        "one-time password",
        "authenticator",
        "captcha",
        "unusual activity",
        "verify it's you",
    )
    return any(marker in text for marker in markers)


def _fill_first(page, selectors: list[str], value: str) -> None:
    last_error = None
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=8000)
            locator.fill(value)
            return
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"could not fill login field; last error: {last_error}")


def _click_first(page, selectors: list[str]) -> None:
    last_error = None
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=8000)
            locator.click()
            return
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"could not click login button; last error: {last_error}")


def _write_env_passwords(path: Path, values: dict[str, str]) -> None:
    if path.is_file():
        lines = path.read_text().splitlines()
    else:
        lines = (ROOT / ".env.example").read_text().splitlines()
    seen = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else ""
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in values.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
