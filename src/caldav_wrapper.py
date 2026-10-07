import os
import datetime
from typing import List, Optional
import caldav
import icalendar
import recurring_ical_events
from src.db import Calendar, CalendarObject, SessionLocal


class CalDAVWrapper:
    def __init__(self):
        self.base_url = os.getenv("CALDAV_BASE_URL")
        self.username = os.getenv("CALDAV_USERNAME")
        self.password = os.getenv("CALDAV_PASSWORD")

        if not all([self.base_url, self.username, self.password]):
            raise ValueError("CALDAV credentials not set in environment variables")

        self.client = caldav.DAVClient(url=self.base_url, username=self.username, password=self.password)
        # Attempt to find principal, handling both root URL and direct principal URL
        try:
            self.principal = self.client.principal()
        except:
            # If auto-discovery fails, assume base_url might be direct calendar home or needs specific handling
            # Some servers like Nextcloud/iCloud might need specific URL structures if auto-discovery fails
            # But commonly, principal() call failing means auth error or wrong base URL.
            # However, the user error suggests 405 Method Not Allowed on Propfind.
            # This often happens if the URL points to a resource that doesn't support PROPFIND at root,
            # or if we need to append a slash.
            if not self.base_url.endswith("/"):
                self.client = caldav.DAVClient(url=self.base_url + "/", username=self.username, password=self.password)
                self.principal = self.client.principal()
            else:
                raise

    def sync(self):
        """Syncs remote calendars and events to local database"""
        session = SessionLocal()
        try:
            calendars = self.principal.calendars()
            for cal in calendars:
                db_cal = session.query(Calendar).filter(Calendar.url == str(cal.url)).first()
                if not db_cal:
                    db_cal = Calendar(name=cal.name or "Unknown", url=str(cal.url))
                    session.add(db_cal)
                    session.commit()
                    session.refresh(db_cal)
                else:
                    if cal.name and db_cal.name != cal.name:
                        db_cal.name = cal.name
                        session.commit()

                events = cal.events()
                session.query(CalendarObject).filter(CalendarObject.calendar_id == db_cal.id).delete()

                for event in events:
                    try:
                        calendar_object = _to_calendar_object(event.data)
                    except Exception as e:
                        print(f"Error syncing event {event}: {e}")
                        continue
                    if calendar_object:
                        calendar_object.calendar_id = db_cal.id
                        session.add(calendar_object)

                session.commit()

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def list_calendars(self) -> List[dict]:
        session = SessionLocal()
        try:
            calendars = session.query(Calendar).all()
            return [{"id": c.id, "name": c.name, "url": c.url} for c in calendars]
        finally:
            session.close()

    def list_events(
        self, start_date: datetime.datetime, end_date: datetime.datetime, calendar_name: Optional[str] = None
    ) -> List[dict]:
        session = SessionLocal()
        try:
            query = (
                session.query(CalendarObject)
                .join(Calendar)
                .filter(
                    CalendarObject.first_start < end_date,
                    CalendarObject.last_end.is_(None) | (CalendarObject.last_end >= start_date),
                )
            )
            if calendar_name:
                query = query.filter(Calendar.name == calendar_name)

            range_start = start_date.replace(tzinfo=datetime.timezone.utc)
            range_end = end_date.replace(tzinfo=datetime.timezone.utc)
            results = []
            for obj in query.all():
                ical = icalendar.Calendar.from_ical(obj.ics)
                for occurrence in recurring_ical_events.of(ical).between(range_start, range_end):
                    if str(occurrence.get("status", "")).upper() == "CANCELLED":
                        continue
                    results.append(_occurrence_to_dict(occurrence, obj))

            return sorted(results, key=lambda e: e["start"])
        finally:
            session.close()

    def create_event(
        self,
        calendar_name: str,
        summary: str,
        start: datetime.datetime,
        end: datetime.datetime,
        description: str = "",
        location: str = "",
    ):
        # Create on server first
        cal = self._get_dav_calendar(calendar_name)
        if not cal:
            raise ValueError(f"Calendar '{calendar_name}' not found on server")

        cal.save_event(
            dtstart=_as_utc(start), dtend=_as_utc(end), summary=summary, description=description, location=location
        )

        # Trigger sync to update local DB
        self.sync()

    def delete_event(self, calendar_name: str, uid: str):
        cal = self._get_dav_calendar(calendar_name)
        if not cal:
            raise ValueError(f"Calendar '{calendar_name}' not found on server")

        event = cal.event_by_uid(uid)
        event.delete()

        # Trigger sync
        self.sync()

    def _get_dav_calendar(self, name: str):
        calendars = self.principal.calendars()
        for cal in calendars:
            if cal.name == name:
                return cal
        return None


def _to_calendar_object(ics: str) -> Optional[CalendarObject]:
    ical = icalendar.Calendar.from_ical(ics)
    vevents = [c for c in ical.walk("VEVENT")]
    if not vevents:
        return None

    recurring = any("RRULE" in v or "RDATE" in v for v in vevents)
    return CalendarObject(
        uid=str(vevents[0].get("uid")),
        ics=ics if isinstance(ics, str) else ics.decode("utf-8"),
        recurring=recurring,
        first_start=min(_to_naive_utc(start) for v in vevents for start in _start_candidates(v)),
        last_end=None if recurring else max(_to_naive_utc(v.end) for v in vevents),
    )


def _start_candidates(vevent: icalendar.Event) -> list[datetime.date]:
    rdates = vevent.get("RDATE", [])
    if not isinstance(rdates, list):
        rdates = [rdates]
    candidates = [vevent.start]
    for rdate in rdates:
        for value in rdate.dts:
            candidates.append(value.dt[0] if isinstance(value.dt, tuple) else value.dt)
    return candidates


def _occurrence_to_dict(occurrence: icalendar.Event, obj: CalendarObject) -> dict:
    return {
        "uid": obj.uid,
        "summary": str(occurrence.get("summary", "")),
        "description": str(occurrence.get("description", "")),
        "start": _to_naive_utc(occurrence.start).isoformat(),
        "end": _to_naive_utc(occurrence.end).isoformat(),
        "all_day": not isinstance(occurrence.start, datetime.datetime),
        "recurring": obj.recurring,
        "location": str(occurrence.get("location", "")),
        "calendar": obj.calendar.name,
    }


def _to_naive_utc(value: datetime.date) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        return datetime.datetime.combine(value, datetime.time.min)
    if value.tzinfo is not None:
        return value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value
