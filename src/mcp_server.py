import datetime
import asyncio
from typing import Optional
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
import mcp.types as types
from src.caldav_wrapper import CalDAVWrapper
from src.db import init_db
import logging

# Initialize DB
init_db()

# Initialize CalDAV Wrapper
try:
    caldav_wrapper = CalDAVWrapper()
except Exception as e:
    logging.error(f"Failed to initialize CalDAV wrapper: {e}")
    caldav_wrapper = None

server = Server("fast-calendar-mcp")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_calendars",
            description="List all available calendars",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="list_events",
            description="List events within a date range",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date (ISO 8601, e.g., 2023-01-01T00:00:00)"},
                    "end_date": {"type": "string", "description": "End date (ISO 8601)"},
                    "calendar_name": {"type": "string", "description": "Optional calendar name to filter by"},
                },
                "required": ["start_date", "end_date"],
            },
        ),
        types.Tool(
            name="create_event",
            description="Create a new event",
            inputSchema={
                "type": "object",
                "properties": {
                    "calendar_name": {"type": "string", "description": "Name of the calendar"},
                    "summary": {"type": "string", "description": "Event title"},
                    "start": {"type": "string", "description": "Start time (ISO 8601)"},
                    "end": {"type": "string", "description": "End time (ISO 8601)"},
                    "description": {"type": "string", "description": "Event description"},
                    "location": {"type": "string", "description": "Event location"},
                },
                "required": ["calendar_name", "summary", "start", "end"],
            },
        ),
        types.Tool(
            name="delete_event",
            description="Delete an event by UID",
            inputSchema={
                "type": "object",
                "properties": {
                    "calendar_name": {"type": "string", "description": "Name of the calendar"},
                    "uid": {"type": "string", "description": "UID of the event to delete"},
                },
                "required": ["calendar_name", "uid"],
            },
        ),
        types.Tool(
            name="sync_calendar",
            description="Force sync with CalDAV server",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if not caldav_wrapper:
        return [types.TextContent(type="text", text="CalDAV wrapper not initialized. Check credentials.")]

    if name == "list_calendars":
        calendars = await asyncio.to_thread(caldav_wrapper.list_calendars)
        return [types.TextContent(type="text", text=str(calendars))]

    elif name == "list_events":
        start_date = datetime.datetime.fromisoformat(arguments["start_date"])
        end_date = datetime.datetime.fromisoformat(arguments["end_date"])
        calendar_name = arguments.get("calendar_name")
        events = await asyncio.to_thread(caldav_wrapper.list_events, start_date, end_date, calendar_name)
        return [types.TextContent(type="text", text=str(events))]

    elif name == "create_event":
        start = datetime.datetime.fromisoformat(arguments["start"])
        end = datetime.datetime.fromisoformat(arguments["end"])
        await asyncio.to_thread(
            caldav_wrapper.create_event,
            arguments["calendar_name"],
            arguments["summary"],
            start,
            end,
            arguments.get("description", ""),
            arguments.get("location", "")
        )
        return [types.TextContent(type="text", text="Event created successfully")]

    elif name == "delete_event":
        await asyncio.to_thread(caldav_wrapper.delete_event, arguments["calendar_name"], arguments["uid"])
        return [types.TextContent(type="text", text="Event deleted successfully")]

    elif name == "sync_calendar":
        await asyncio.to_thread(caldav_wrapper.sync)
        return [types.TextContent(type="text", text="Calendar synced successfully")]

    else:
        raise ValueError(f"Unknown tool: {name}")

async def run():
    # Initial sync
    if caldav_wrapper:
        print("Performing initial sync...")
        try:
            await asyncio.to_thread(caldav_wrapper.sync)
            print("Initial sync complete.")
        except Exception as e:
            print(f"Initial sync failed: {e}")
