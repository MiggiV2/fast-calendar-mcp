import datetime
import time

import pytest
from caldav.lib.vcal import create_ical

from tests.conftest import FakeDavCalendar


@pytest.fixture
def local_timezone_berlin(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_created_event_keeps_utc_time_regardless_of_host_timezone(wrapper_for, local_timezone_berlin):
    calendar = FakeDavCalendar("Work", "https://dav/work/", [])
    wrapper = wrapper_for(calendar)

    wrapper.create_event("Work", "Review", datetime.datetime(2026, 10, 8, 9, 0), datetime.datetime(2026, 10, 8, 10, 0))

    ical = create_ical(**calendar.saved_events[0])
    assert "DTSTART:20261008T090000Z" in ical
    assert "DTEND:20261008T100000Z" in ical
