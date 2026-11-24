import asyncio

import pytest

import src.mcp_server as mcp_server


class SyncingWrapper:
    def __init__(self):
        self.synced = 0

    def sync(self):
        self.synced += 1

    def list_calendars(self):
        return [{"id": 1, "name": "Work", "url": "https://dav/work"}]


class FlakyFactory:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def uninitialized(monkeypatch):
    monkeypatch.setattr(mcp_server, "caldav_wrapper", None)


def install(monkeypatch, factory):
    monkeypatch.setattr(mcp_server, "CalDAVWrapper", factory)
    return factory


def test_tool_call_retries_initialization_after_failed_start(monkeypatch, uninitialized):
    wrapper = SyncingWrapper()
    install(monkeypatch, FlakyFactory(wrapper))

    result = asyncio.run(mcp_server.handle_call_tool("calendar_list", {}))

    assert "Work" in result[0].text
    assert mcp_server.caldav_wrapper is wrapper
    assert wrapper.synced == 1


def test_tool_call_reports_unavailable_while_server_still_down(monkeypatch, uninitialized):
    install(monkeypatch, FlakyFactory(ConnectionError("503 no available server")))

    result = asyncio.run(mcp_server.handle_call_tool("calendar_list", {}))

    assert "not initialized" in result[0].text
    assert mcp_server.caldav_wrapper is None


def test_background_connect_retries_until_server_is_back(monkeypatch, uninitialized):
    wrapper = SyncingWrapper()
    factory = install(
        monkeypatch,
        FlakyFactory(ConnectionError("503"), ConnectionError("503"), wrapper),
    )

    asyncio.run(mcp_server.connect_with_retry(initial_delay=0, max_delay=0))

    assert factory.calls == 3
    assert mcp_server.caldav_wrapper is wrapper
    assert wrapper.synced == 1


def test_background_connect_gives_up_on_missing_credentials(monkeypatch, uninitialized):
    factory = install(monkeypatch, FlakyFactory(ValueError("CALDAV credentials not set")))

    asyncio.run(mcp_server.connect_with_retry(initial_delay=0, max_delay=0))

    assert factory.calls == 1
    assert mcp_server.caldav_wrapper is None


def test_backoff_doubles_up_to_max_delay(monkeypatch, uninitialized):
    delays = []

    async def record_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(mcp_server.asyncio, "sleep", record_sleep)
    install(monkeypatch, FlakyFactory(*[ConnectionError("503")] * 5, SyncingWrapper()))

    asyncio.run(mcp_server.connect_with_retry(initial_delay=5, max_delay=30))

    assert delays == [5, 10, 20, 30, 30]
