#!/usr/bin/env python3
"""Find new manufacturers in Brave and draft Outreach Tracker rows A–K and T.

Reads the current tracker, plus earlier batches in config/settings.yaml, and
drops any company, domain, or email already listed. Opens Brave through
Playwright. Email order is: a personal address on the company's own site, then
a shared inbox printed under a named person, then the general inbox on that
site. A personal address found only on a directory is flagged and not written.
The script never invents a firstname@domain address. Nothing is written unless
--write is set. Subject and the four emails stay blank for `outreach assemble`.

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
