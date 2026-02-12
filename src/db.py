import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

class Base(DeclarativeBase):
    pass

class Calendar(Base):
    __tablename__ = "calendars"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    
    events: Mapped[list["Event"]] = relationship(back_populates="calendar", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"Calendar(id={self.id!r}, name={self.name!r})"

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("calendars.id"))
    uid: Mapped[str] = mapped_column(String(255), index=True)
    summary: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    start: Mapped[datetime.datetime] = mapped_column(DateTime)
    end: Mapped[datetime.datetime] = mapped_column(DateTime)
    location: Mapped[Optional[str]] = mapped_column(String(255))

    calendar: Mapped["Calendar"] = relationship(back_populates="events")

    def __repr__(self) -> str:
        return f"Event(id={self.id!r}, summary={self.summary!r}, start={self.start!r})"

# Database setup
DATABASE_URL = "sqlite:///./calendar.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
