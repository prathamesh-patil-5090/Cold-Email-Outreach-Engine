from datetime import date, datetime
from zoneinfo import ZoneInfo

from outreach.calendar import add_business_days, in_send_window
from outreach.config import load_settings
from outreach.plan import next_action_after


def test_followup_gaps_match_the_live_tracker():
    assert date(2026, 11, 20).weekday() == 4
    assert add_business_days(date(2026, 11, 19), 4) == date(2026, 11, 25)
    assert add_business_days(date(2026, 11, 20), 4) == date(2026, 11, 26)
    assert next_action_after(date(2026, 11, 25), "day4") == "2026-12-01"
    assert next_action_after(date(2026, 12, 1), "day8") == "2026-12-09"
    assert next_action_after(date(2026, 11, 20), "day14") == ""


def test_window_is_weekday_daytime_in_kolkata():
    zone = ZoneInfo("Asia/Kolkata")
    hours = load_settings().business_hours
    assert in_send_window(datetime(2026, 11, 20, 10, 0, tzinfo=zone), hours.start, hours.end)
    assert not in_send_window(datetime(2026, 11, 20, 21, 53, tzinfo=zone), hours.start, hours.end)
    assert not in_send_window(datetime(2026, 11, 21, 10, 0, tzinfo=zone), hours.start, hours.end)
    assert not in_send_window(datetime(2026, 11, 20, 9, 29, tzinfo=zone), hours.start, hours.end)


def test_settings_keep_the_reply_inbox_out_of_rotation():
    settings = load_settings()
    assert len(settings.mailboxes) == 7
    assert settings.reply_to == "prathamesh@pratz.is-a.dev"
    assert all(box.email != settings.reply_to for box in settings.mailboxes)
    assert settings.phase_for(date(2026, 11, 20)).daily_per_mailbox == 5
    assert settings.phase_for(date(2026, 11, 26)).name == "week2"
    assert settings.phase_for(date(2026, 12, 4)).daily_per_mailbox == 16
