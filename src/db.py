import datetime
from typing import Optional
from sqlalchemy import Boolean, String, DateTime, ForeignKey, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Calendar(Base):
    __tablename__ = "calendars"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1024), unique=True)

    objects: Mapped[list["CalendarObject"]] = relationship(back_populates="calendar", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"Calendar(id={self.id!r}, name={self.name!r})"


class CalendarObject(Base):
    __tablename__ = "calendar_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("calendars.id"))
    uid: Mapped[str] = mapped_column(String(255), index=True)
    ics: Mapped[str] = mapped_column(Text)
    recurring: Mapped[bool] = mapped_column(Boolean)
    first_start: Mapped[datetime.datetime] = mapped_column(DateTime, index=True)
    last_end: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    calendar: Mapped["Calendar"] = relationship(back_populates="objects")

    def __repr__(self) -> str:
        return f"CalendarObject(id={self.id!r}, uid={self.uid!r})"


# Database setup
import os

os.makedirs("data", exist_ok=True)
DATABASE_URL = "sqlite:///./data/calendar.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    # The former "events" table cached flattened occurrences; it is a pure cache, so drop it and let sync refill.
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS events"))
    Base.metadata.create_all(bind=engine)
