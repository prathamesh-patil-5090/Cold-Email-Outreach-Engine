"""Load settings and the mailbox ramp. Secrets stay in the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

import yaml
from dotenv import load_dotenv


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Mailbox:
    email: str
    display_name: str
    password_env: str

    def password(self) -> str:
        value = os.environ.get(self.password_env, "").strip()
        if not value:
            raise ConfigError(
                f"Missing {self.password_env} for {self.email}. "
                "Add the Zoho app password to .env."
            )
        return value

    @property
    def domain(self) -> str:
        return self.email.split("@", 1)[1]


@dataclass(frozen=True)
class RampPhase:
    name: str
    through_day: int
    daily_per_mailbox: int
    hourly_per_mailbox: int
    jitter_min_seconds: int
    jitter_max_seconds: int


@dataclass(frozen=True)
class BusinessHours:
    start: time
    end: time


@dataclass(frozen=True)
class Settings:
    spreadsheet_id: str
    prior_spreadsheet_ids: tuple[str, ...]
    worksheet: str
    timezone: str
    campaign_start: date
    business_hours: BusinessHours
    reply_to: str
    smtp_host: str
    smtp_port: int
    ramp: tuple[RampPhase, ...]
    mailboxes: tuple[Mailbox, ...]
    root: Path

    def phase_for(self, today: date) -> RampPhase:
        day_number = (today - self.campaign_start).days + 1
        if day_number < 1:
            day_number = 1
        for phase in self.ramp:
            if day_number <= phase.through_day:
                return phase
        return self.ramp[-1]

    def mailbox_by_email(self, email: str) -> Mailbox | None:
        wanted = email.strip().casefold()
        for mailbox in self.mailboxes:
            if mailbox.email.casefold() == wanted:
                return mailbox
        return None


def project_root() -> Path:
    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "config" / "settings.yaml").is_file():
            return candidate
    return Path(__file__).resolve().parents[2]


def load_settings(root: Path | None = None) -> Settings:
    root = root or project_root()
    load_dotenv(root / ".env")
    path = root / "config" / "settings.yaml"
    if not path.is_file():
        raise ConfigError(f"Missing {path}")
    raw = yaml.safe_load(path.read_text()) or {}
    hours = raw.get("business_hours") or {}
    smtp = raw.get("smtp") or {}
    mailboxes = tuple(
        Mailbox(
            email=item["email"].strip(),
            display_name=item.get("display_name", "Prathamesh Patil").strip(),
            password_env=item["password_env"].strip(),
        )
        for item in raw.get("mailboxes") or []
    )
    if len(mailboxes) != 7:
        raise ConfigError(f"Expected 7 outreach mailboxes, found {len(mailboxes)}.")
    reply_to = os.environ.get("REPLY_TO", raw.get("reply_to", "")).strip()
    if any(box.email.casefold() == reply_to.casefold() for box in mailboxes):
        raise ConfigError("The reply inbox must not be one of the outreach mailboxes.")
    ramp = tuple(
        RampPhase(
            name=item["name"],
            through_day=int(item["through_day"]),
            daily_per_mailbox=int(item["daily_per_mailbox"]),
            hourly_per_mailbox=int(item["hourly_per_mailbox"]),
            jitter_min_seconds=int(item["jitter_min_seconds"]),
            jitter_max_seconds=int(item["jitter_max_seconds"]),
        )
        for item in raw.get("ramp") or []
    )
    if not ramp:
        raise ConfigError("Ramp schedule is empty.")
    prior = raw.get("prior_spreadsheet_ids") or []
    return Settings(
        spreadsheet_id=os.environ.get("SPREADSHEET_ID", raw["spreadsheet_id"]).strip(),
        prior_spreadsheet_ids=tuple(str(item).strip() for item in prior if str(item).strip()),
        worksheet=os.environ.get("WORKSHEET_NAME", raw.get("worksheet", "Outreach Tracker")).strip(),
        timezone=raw.get("timezone", "Asia/Kolkata"),
        campaign_start=date.fromisoformat(str(raw["campaign_start"])),
        business_hours=BusinessHours(
            start=_parse_time(str(hours.get("start", "09:30"))),
            end=_parse_time(str(hours.get("end", "17:30"))),
        ),
        reply_to=reply_to,
        smtp_host=os.environ.get("SMTP_HOST", smtp.get("host", "smtp.zoho.in")).strip(),
        smtp_port=int(os.environ.get("SMTP_PORT", smtp.get("port", 587))),
        ramp=ramp,
        mailboxes=mailboxes,
        root=root,
    )


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))
