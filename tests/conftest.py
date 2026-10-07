import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.caldav_wrapper as caldav_wrapper_module
from src.caldav_wrapper import CalDAVWrapper
from src.db import Base


class FakeDavEvent:
    def __init__(self, data: str):
        self.data = data


class FakeDavCalendar:
    def __init__(self, name: str, url: str, ics_objects: list[str]):
        self.name = name
        self.url = url
        self.ics_objects = ics_objects
        self.saved_events: list[dict] = []

    def events(self):
        return [FakeDavEvent(data) for data in self.ics_objects]

    def save_event(self, **kwargs):
        self.saved_events.append(kwargs)


class FakePrincipal:
    def __init__(self, calendars: list[FakeDavCalendar]):
        self._calendars = calendars

    def calendars(self):
        return self._calendars


@pytest.fixture(autouse=True)
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(caldav_wrapper_module, "SessionLocal", sessionmaker(bind=engine))
    yield
    engine.dispose()


@pytest.fixture
def wrapper_for():
    def build(*calendars: FakeDavCalendar) -> CalDAVWrapper:
        wrapper = CalDAVWrapper.__new__(CalDAVWrapper)
        wrapper.principal = FakePrincipal(list(calendars))
        wrapper.sync()
        return wrapper

    return build


def vcalendar(*vevents: str) -> str:
    body = "\n".join(vevent.strip() for vevent in vevents)
    return f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//test//EN\n{body}\nEND:VCALENDAR\n".replace("\n", "\r\n")
