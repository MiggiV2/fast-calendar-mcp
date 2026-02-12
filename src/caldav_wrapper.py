import os
import datetime
from typing import List, Optional
import caldav
from caldav.elements import dav, cdav
from sqlalchemy.orm import Session
from src.db import Calendar, Event, SessionLocal, init_db
import icalendar
from dateutil import parser
import pytz

class CalDAVWrapper:
    def __init__(self):
        self.base_url = os.getenv("CALDAV_BASE_URL")
        self.username = os.getenv("CALDAV_USERNAME")
        self.password = os.getenv("CALDAV_PASSWORD")
        
        if not all([self.base_url, self.username, self.password]):
            raise ValueError("CALDAV credentials not set in environment variables")

        self.client = caldav.DAVClient(
            url=self.base_url,
            username=self.username,
            password=self.password
        )
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
            if not self.base_url.endswith('/'):
                 self.client = caldav.DAVClient(
                    url=self.base_url + '/',
                    username=self.username,
                    password=self.password
                )
                 self.principal = self.client.principal()
            else:
                raise

    def sync(self):
        """Syncs remote calendars and events to local database"""
        session = SessionLocal()
        try:
            calendars = self.principal.calendars()
            for cal in calendars:
                # Update or create calendar in DB
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

                # Sync events
                # For simplicity in this MCP, we fetch all events. 
                # In production, use sync-token or time-range.
                events = cal.events()
                existing_uids = {e.uid for e in db_cal.events}
                fetched_uids = set()

                for event in events:
                    try:
                        ical_data = event.data
                        cal_obj = icalendar.Calendar.from_ical(ical_data)
                        
                        for component in cal_obj.walk():
                            if component.name == "VEVENT":
                                uid = str(component.get('uid'))
                                fetched_uids.add(uid)
                                
                                summary = str(component.get('summary', ''))
                                description = str(component.get('description', ''))
                                location = str(component.get('location', ''))
                                
                                dtstart = component.get('dtstart').dt
                                dtend = component.get('dtend').dt if component.get('dtend') else dtstart

                                # Normalize to UTC naive for DB
                                if isinstance(dtstart, datetime.datetime):
                                    if dtstart.tzinfo:
                                        dtstart = dtstart.astimezone(pytz.UTC).replace(tzinfo=None)
                                elif isinstance(dtstart, datetime.date):
                                    dtstart = datetime.datetime.combine(dtstart, datetime.time.min)

                                if isinstance(dtend, datetime.datetime):
                                    if dtend.tzinfo:
                                        dtend = dtend.astimezone(pytz.UTC).replace(tzinfo=None)
                                elif isinstance(dtend, datetime.date):
                                    dtend = datetime.datetime.combine(dtend, datetime.time.min)

                                db_event = session.query(Event).filter(Event.uid == uid, Event.calendar_id == db_cal.id).first()
                                if db_event:
                                    # Update
                                    db_event.summary = summary
                                    db_event.description = description
                                    db_event.start = dtstart
                                    db_event.end = dtend
                                    db_event.location = location
                                else:
                                    # Create
                                    db_event = Event(
                                        calendar_id=db_cal.id,
                                        uid=uid,
                                        summary=summary,
                                        description=description,
                                        start=dtstart,
                                        end=dtend,
                                        location=location
                                    )
                                    session.add(db_event)
                    except Exception as e:
                        print(f"Error syncing event {event}: {e}")
                        continue
                
                # Remove events that no longer exist on server
                to_delete = existing_uids - fetched_uids
                if to_delete:
                    session.query(Event).filter(Event.uid.in_(to_delete), Event.calendar_id == db_cal.id).delete(synchronize_session=False)
                
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

    def list_events(self, start_date: datetime.datetime, end_date: datetime.datetime, calendar_name: Optional[str] = None) -> List[dict]:
        session = SessionLocal()
        try:
            query = session.query(Event).join(Calendar).filter(
                Event.start >= start_date,
                Event.start <= end_date
            )
            
            if calendar_name:
                query = query.filter(Calendar.name == calendar_name)
                
            events = query.all()
            return [{
                "uid": e.uid,
                "summary": e.summary,
                "description": e.description,
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
                "location": e.location,
                "calendar": e.calendar.name
            } for e in events]
        finally:
            session.close()

    def create_event(self, calendar_name: str, summary: str, start: datetime.datetime, end: datetime.datetime, description: str = "", location: str = ""):
        # Create on server first
        cal = self._get_dav_calendar(calendar_name)
        if not cal:
            raise ValueError(f"Calendar '{calendar_name}' not found on server")

        cal.save_event(
            dtstart=start,
            dtend=end,
            summary=summary,
            description=description,
            location=location
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
