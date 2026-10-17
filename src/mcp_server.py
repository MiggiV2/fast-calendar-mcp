import datetime
import asyncio
from typing import Optional
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
import mcp.types as types
from src.caldav_wrapper import CalDAVWrapper
from src.calendar_time import calendar_timezone, to_naive_utc
from src.db import init_db
from src.webdav_storage import WebDAVStorage
import logging
import os

# Initialize DB
init_db()

# Initialize CalDAV Wrapper
try:
    caldav_wrapper = CalDAVWrapper()
except Exception as e:
    logging.error(f"Failed to initialize CalDAV wrapper: {e}")
    caldav_wrapper = None


def _storage_from_env(prefix: str, writable: bool) -> Optional[WebDAVStorage]:
    url = os.getenv(f"{prefix}_URL")
    if not url:
        return None
    username = os.getenv("WEBDAV_USERNAME") or os.getenv("CALDAV_USERNAME")
    password = os.getenv(f"{prefix}_PASSWORD") or os.getenv("CALDAV_PASSWORD")
    try:
        return WebDAVStorage(url, username, password, writable=writable)
    except ValueError as e:
        logging.error(f"{prefix} storage disabled: {e}")
        return None


notes_storage = _storage_from_env("WEBDAV_NOTES", writable=False)
drafts_storage = _storage_from_env("WEBDAV_DRAFTS", writable=True)

server = Server("fast-calendar-mcp")

def _time_description(label: str) -> str:
    return f"{label} (ISO 8601). Without an offset it is read as {calendar_timezone().key} local time"


def _path_schema(description: str, required: bool = True, **extra_properties) -> dict:
    return {
        "type": "object",
        "properties": {"path": {"type": "string", "description": description}, **extra_properties},
        "required": ["path", *extra_properties] if required else list(extra_properties),
    }


def _file_tools() -> list[types.Tool]:
    file_path = "File path relative to the storage root, as returned by the list tool, e.g. 'Rezepte/Pizza.md'"
    directory = "Directory relative to the storage root, '' or omitted for the root. Folders end with '/'"
    tools = []
    if notes_storage:
        tools += [
            types.Tool(
                name="notes_list",
                description="List files and folders in the read-only notes storage",
                inputSchema=_path_schema(directory, required=False),
            ),
            types.Tool(
                name="notes_read",
                description="Read a file from the read-only notes storage",
                inputSchema=_path_schema(file_path),
            ),
        ]
    if drafts_storage:
        tools += [
            types.Tool(
                name="drafts_list",
                description="List files and folders in the writable drafts storage",
                inputSchema=_path_schema(directory, required=False),
            ),
            types.Tool(
                name="drafts_read",
                description="Read a file from the writable drafts storage",
                inputSchema=_path_schema(file_path),
            ),
            types.Tool(
                name="drafts_write",
                description="Create or overwrite a file in the writable drafts storage",
                inputSchema=_path_schema(
                    file_path, content={"type": "string", "description": "Text content to write"}
                ),
            ),
            types.Tool(
                name="drafts_delete",
                description="Delete a file from the writable drafts storage",
                inputSchema=_path_schema(file_path),
            ),
        ]
    return tools


async def _call_file_tool(name: str, arguments: dict) -> str:
    area, action = name.split("_", 1)
    storage = notes_storage if area == "notes" else drafts_storage
    if storage is None:
        raise ValueError(f"{area} storage is not configured")
    path = arguments.get("path", "")
    if action == "list":
        return "\n".join(await asyncio.to_thread(storage.list, path))
    if action == "read":
        return await asyncio.to_thread(storage.read, path)
    if action == "write":
        await asyncio.to_thread(storage.write, path, arguments["content"])
        return f"Wrote {path}"
    await asyncio.to_thread(storage.delete, path)
    return f"Deleted {path}"


FILE_TOOL_NAMES = {"notes_list", "notes_read", "drafts_list", "drafts_read", "drafts_write", "drafts_delete"}

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return _file_tools() + [
        types.Tool(
            name="calendar_list",
            description="List all available calendars",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="calendar_list_events",
            description="List events within a date range. Event times are returned in local time with UTC offset",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": _time_description("Start date, e.g. 2023-01-01T00:00:00")},
                    "end_date": {"type": "string", "description": _time_description("End date")},
                    "calendar_name": {"type": "string", "description": "Optional calendar name to filter by"},
                },
                "required": ["start_date", "end_date"],
            },
        ),
        types.Tool(
            name="calendar_create_event",
            description="Create a new event",
            inputSchema={
                "type": "object",
                "properties": {
                    "calendar_name": {"type": "string", "description": "Name of the calendar"},
                    "summary": {"type": "string", "description": "Event title"},
                    "start": {"type": "string", "description": _time_description("Start time")},
                    "end": {"type": "string", "description": _time_description("End time")},
                    "description": {"type": "string", "description": "Event description"},
                    "location": {"type": "string", "description": "Event location"},
                },
                "required": ["calendar_name", "summary", "start", "end"],
            },
        ),
        types.Tool(
            name="calendar_delete_event",
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
            name="calendar_sync",
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
    if name in FILE_TOOL_NAMES:
        return [types.TextContent(type="text", text=await _call_file_tool(name, arguments or {}))]

    if not caldav_wrapper:
        return [types.TextContent(type="text", text="CalDAV wrapper not initialized. Check credentials.")]

    if name in ("calendar_list", "list_calendars"):
        calendars = await asyncio.to_thread(caldav_wrapper.list_calendars)
        return [types.TextContent(type="text", text=str(calendars))]

    elif name in ("calendar_list_events", "list_events"):
        start_date_raw = arguments["start_date"]
        end_date_raw = arguments["end_date"]
        start_date = to_naive_utc(datetime.datetime.fromisoformat(start_date_raw))
        end_date = to_naive_utc(datetime.datetime.fromisoformat(end_date_raw))
        if "T" not in end_date_raw:
            end_date += datetime.timedelta(days=1)
        calendar_name = arguments.get("calendar_name")
        events = await asyncio.to_thread(caldav_wrapper.list_events, start_date, end_date, calendar_name)
        return [types.TextContent(type="text", text=str(events))]

    elif name in ("calendar_create_event", "calendar_create", "create_event"):
        start = to_naive_utc(datetime.datetime.fromisoformat(arguments["start"]))
        end = to_naive_utc(datetime.datetime.fromisoformat(arguments["end"]))
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

    elif name in ("calendar_delete_event", "calendar_delete", "delete_event"):
        await asyncio.to_thread(caldav_wrapper.delete_event, arguments["calendar_name"], arguments["uid"])
        return [types.TextContent(type="text", text="Event deleted successfully")]

    elif name in ("calendar_sync", "sync_calendar"):
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
