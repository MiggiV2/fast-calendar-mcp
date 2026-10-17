import datetime
import os
from zoneinfo import ZoneInfo


def calendar_timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("CALENDAR_TIMEZONE", "Europe/Berlin"))


def to_naive_utc(value: datetime.datetime) -> datetime.datetime:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=calendar_timezone())
    return aware.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def to_calendar_iso(value: datetime.date) -> str:
    if not isinstance(value, datetime.datetime):
        return value.isoformat()
    aware = value if value.tzinfo is not None else value.replace(tzinfo=calendar_timezone())
    return aware.astimezone(calendar_timezone()).isoformat()
