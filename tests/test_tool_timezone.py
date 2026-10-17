import asyncio
import datetime

import pytest

import src.mcp_server as mcp_server


class RecordingWrapper:
    def __init__(self):
        self.created: list[tuple] = []
        self.listed: list[tuple] = []

    def create_event(self, calendar_name, summary, start, end, description, location):
        self.created.append((start, end))

    def list_events(self, start_date, end_date, calendar_name=None):
        self.listed.append((start_date, end_date))
        return []


@pytest.fixture
def recording_wrapper(monkeypatch):
    wrapper = RecordingWrapper()
    monkeypatch.setattr(mcp_server, "caldav_wrapper", wrapper)
    return wrapper


def create(start: str, end: str):
    arguments = {"calendar_name": "Work", "summary": "Review", "start": start, "end": end}
    asyncio.run(mcp_server.handle_call_tool("calendar_create_event", arguments))


def test_create_reads_times_without_offset_as_calendar_timezone(recording_wrapper):
    create("2026-10-08T14:00:00", "2026-10-08T15:00:00")

    assert recording_wrapper.created == [(datetime.datetime(2026, 10, 8, 12, 0), datetime.datetime(2026, 10, 8, 13, 0))]


def test_create_keeps_explicit_offset(recording_wrapper):
    create("2026-10-08T14:00:00+00:00", "2026-10-08T15:00:00Z")

    assert recording_wrapper.created == [(datetime.datetime(2026, 10, 8, 14, 0), datetime.datetime(2026, 10, 8, 15, 0))]


def test_list_reads_dates_as_calendar_timezone_days(recording_wrapper):
    arguments = {"start_date": "2026-10-08", "end_date": "2026-10-08"}
    asyncio.run(mcp_server.handle_call_tool("calendar_list_events", arguments))

    assert recording_wrapper.listed == [(datetime.datetime(2026, 10, 7, 22, 0), datetime.datetime(2026, 10, 8, 22, 0))]


def test_calendar_timezone_is_configurable(recording_wrapper, monkeypatch):
    monkeypatch.setenv("CALENDAR_TIMEZONE", "America/New_York")

    create("2026-10-08T14:00:00", "2026-10-08T15:00:00")

    assert recording_wrapper.created == [(datetime.datetime(2026, 10, 8, 18, 0), datetime.datetime(2026, 10, 8, 19, 0))]


def test_time_arguments_name_the_calendar_timezone():
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.handle_list_tools())}

    for tool_name, argument in [
        ("calendar_list_events", "start_date"),
        ("calendar_list_events", "end_date"),
        ("calendar_create_event", "start"),
        ("calendar_create_event", "end"),
    ]:
        assert "Europe/Berlin" in tools[tool_name].inputSchema["properties"][argument]["description"]
