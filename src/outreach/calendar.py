"""Business-day schedule in the prospect timezone. Weekends are not send days."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def in_send_window(now: datetime, start: time, end: time) -> bool:
    if now.weekday() >= 5:
        return False
    return start <= now.timetz().replace(tzinfo=None) < end


def add_business_days(start: date, days: int) -> date:
    if days < 0:
        raise ValueError("days must be >= 0")
    cursor = start
    remaining = days
    while remaining:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            remaining -= 1
    return cursor


def today_in(zone: ZoneInfo, now: datetime | None = None) -> date:
    current = now or datetime.now(zone)
    return current.astimezone(zone).date()
