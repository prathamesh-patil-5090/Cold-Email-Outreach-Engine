#!/usr/bin/env python3
"""Find new manufacturers in Brave and draft Outreach Tracker rows A–K and T.

Reads the current tracker, plus earlier batches in config/settings.yaml, and
drops any company, domain, or email already listed. Opens Brave through
Playwright, keeps Indian manufacturers in Maharashtra, Gujarat, or Bengaluru
that name a person next to an email on their own site, and drafts the three
research fields. Nothing is written unless --write is set. Subject and the
four emails stay blank for `outreach assemble`.

  pip install -e ".[zoho]"
  python scripts/find_leads.py
  python scripts/find_leads.py --write
  python scripts/find_leads.py --write --limit 5
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from outreach.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["find", *sys.argv[1:]]))
