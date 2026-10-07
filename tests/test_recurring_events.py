import datetime

from tests.conftest import FakeDavCalendar, vcalendar

WEEKLY_STANDUP = """
BEGIN:VEVENT
UID:standup
DTSTART;TZID=Europe/Berlin:20261006T090000
DTEND;TZID=Europe/Berlin:20261006T093000
RRULE:FREQ=WEEKLY;COUNT=6
SUMMARY:Standup
END:VEVENT
"""

OCTOBER = (datetime.datetime(2026, 10, 1), datetime.datetime(2026, 11, 1))


def starts(events: list[dict], summary: str | None = None) -> list[str]:
    return sorted(e["start"] for e in events if summary is None or e["summary"] == summary)


def test_moved_occurrence_appears_only_at_its_new_time(wrapper_for):
    moved = """
BEGIN:VEVENT
UID:standup
RECURRENCE-ID;TZID=Europe/Berlin:20261013T090000
DTSTART;TZID=Europe/Berlin:20261014T140000
DTEND;TZID=Europe/Berlin:20261014T143000
SUMMARY:Standup (moved)
END:VEVENT
"""
    wrapper = wrapper_for(FakeDavCalendar("Work", "https://dav/work/", [vcalendar(WEEKLY_STANDUP, moved)]))

    events = wrapper.list_events(*OCTOBER)

    assert starts(events) == [
        "2026-10-06T07:00:00",
        "2026-10-14T12:00:00",
        "2026-10-20T07:00:00",
        "2026-10-27T08:00:00",
    ]
    assert [e["summary"] for e in events if e["start"] == "2026-10-14T12:00:00"] == ["Standup (moved)"]


def test_excluded_occurrence_is_not_listed(wrapper_for):
    with_exdate = WEEKLY_STANDUP.replace(
        "SUMMARY:Standup", "EXDATE;TZID=Europe/Berlin:20261020T090000\nSUMMARY:Standup"
    )
    wrapper = wrapper_for(FakeDavCalendar("Work", "https://dav/work/", [vcalendar(with_exdate)]))

    events = wrapper.list_events(*OCTOBER)

    assert "2026-10-20T07:00:00" not in starts(events)
    assert len(events) == 3


def test_cancelled_occurrence_is_not_listed(wrapper_for):
    cancelled = """
BEGIN:VEVENT
UID:standup
RECURRENCE-ID;TZID=Europe/Berlin:20261013T090000
DTSTART;TZID=Europe/Berlin:20261013T090000
DTEND;TZID=Europe/Berlin:20261013T093000
STATUS:CANCELLED
SUMMARY:Standup
END:VEVENT
"""
    wrapper = wrapper_for(FakeDavCalendar("Work", "https://dav/work/", [vcalendar(WEEKLY_STANDUP, cancelled)]))

    events = wrapper.list_events(*OCTOBER)

    assert "2026-10-13T07:00:00" not in starts(events)
    assert len(events) == 3


def test_series_keeps_local_wall_clock_time_across_dst_change(wrapper_for):
    wrapper = wrapper_for(FakeDavCalendar("Work", "https://dav/work/", [vcalendar(WEEKLY_STANDUP)]))

    events = wrapper.list_events(datetime.datetime(2026, 10, 26), datetime.datetime(2026, 11, 1))

    assert [(e["start"], e["end"]) for e in events] == [("2026-10-27T08:00:00", "2026-10-27T08:30:00")]


def test_additional_rdate_occurrence_is_listed(wrapper_for):
    with_rdate = WEEKLY_STANDUP.replace("SUMMARY:Standup", "RDATE;TZID=Europe/Berlin:20261016T110000\nSUMMARY:Standup")
    wrapper = wrapper_for(FakeDavCalendar("Work", "https://dav/work/", [vcalendar(with_rdate)]))

    events = wrapper.list_events(*OCTOBER)

    assert "2026-10-16T09:00:00" in starts(events)


def test_series_ends_at_until(wrapper_for):
    with_until = WEEKLY_STANDUP.replace("COUNT=6", "UNTIL=20261013T070000Z")
    wrapper = wrapper_for(FakeDavCalendar("Work", "https://dav/work/", [vcalendar(with_until)]))

    events = wrapper.list_events(*OCTOBER)

    assert starts(events) == ["2026-10-06T07:00:00", "2026-10-13T07:00:00"]


def test_yearly_all_day_event_recurs_on_its_date(wrapper_for):
    birthday = """
BEGIN:VEVENT
UID:birthday
DTSTART;VALUE=DATE:19901009
DTEND;VALUE=DATE:19901010
RRULE:FREQ=YEARLY
SUMMARY:Birthday
END:VEVENT
"""
    wrapper = wrapper_for(FakeDavCalendar("Birthdays", "https://dav/bday/", [vcalendar(birthday)]))

    events = wrapper.list_events(*OCTOBER)

    assert [(e["start"], e["end"], e["all_day"]) for e in events] == [
        ("2026-10-09T00:00:00", "2026-10-10T00:00:00", True)
    ]


def test_occurrences_are_marked_as_recurring(wrapper_for):
    single = """
BEGIN:VEVENT
UID:dentist
DTSTART:20261015T080000Z
DTEND:20261015T090000Z
SUMMARY:Dentist
END:VEVENT
"""
    wrapper = wrapper_for(FakeDavCalendar("Work", "https://dav/work/", [vcalendar(WEEKLY_STANDUP), vcalendar(single)]))

    events = wrapper.list_events(*OCTOBER)

    assert {e["summary"]: e["recurring"] for e in events} == {"Standup": True, "Dentist": False}


def test_event_running_into_the_range_is_listed(wrapper_for):
    conference = """
BEGIN:VEVENT
UID:conference
DTSTART;VALUE=DATE:20260930
DTEND;VALUE=DATE:20261003
SUMMARY:Conference
END:VEVENT
"""
    wrapper = wrapper_for(FakeDavCalendar("Work", "https://dav/work/", [vcalendar(conference)]))

    events = wrapper.list_events(*OCTOBER)

    assert [e["summary"] for e in events] == ["Conference"]


def test_calendar_filter_applies_to_series(wrapper_for):
    wrapper = wrapper_for(
        FakeDavCalendar("Work", "https://dav/work/", [vcalendar(WEEKLY_STANDUP)]),
        FakeDavCalendar("Private", "https://dav/private/", [vcalendar(WEEKLY_STANDUP.replace("standup", "gym"))]),
    )

    events = wrapper.list_events(*OCTOBER, calendar_name="Private")

    assert {e["calendar"] for e in events} == {"Private"}
    assert len(events) == 4


def test_resync_reflects_changes_to_a_series(wrapper_for):
    calendar = FakeDavCalendar("Work", "https://dav/work/", [vcalendar(WEEKLY_STANDUP)])
    wrapper = wrapper_for(calendar)
    calendar.ics_objects = [vcalendar(WEEKLY_STANDUP.replace("COUNT=6", "COUNT=1"))]

    wrapper.sync()

    assert starts(wrapper.list_events(*OCTOBER)) == ["2026-10-06T07:00:00"]
