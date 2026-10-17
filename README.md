# Fast Calendar MCP

A Model Context Protocol (MCP) server that provides calendar interactions using CalDAV, plus optional WebDAV file tools for notes and drafts. It syncs events from a CalDAV server (like Nextcloud, iCloud, or Google Calendar) to a local SQLite database for fast access and manipulation.

## Features

- **CalDAV Integration**: Syncs with any standard CalDAV server.
- **Local Caching**: Stores each raw iCalendar object in a local SQLite database (`calendar.db`) for low-latency queries.
- **Recurring Events**: Series are expanded at query time via `recurring-ical-events` (moved/cancelled occurrences, EXDATE, RDATE, UNTIL/COUNT, all-day series, DST-correct wall-clock times).
- **Streamable HTTP Transport**: Implements the MCP Streamable HTTP transport at `/mcp`.
- **Docker Support**: Multi-architecture Docker image (AMD64 & ARM64).
- **CRUD Operations**: Create, Read, and Delete events.
- **WebDAV File Tools**: Optional read-only notes storage and read-write drafts storage.

## Prerequisites

- Python 3.11+
- A CalDAV server (e.g., Nextcloud, Baikal, iCloud)

## Configuration

Create a `.env` file in the root directory with your CalDAV credentials:

```env
CALDAV_BASE_URL=https://<host>/remote.php/dav/
CALDAV_USERNAME=your-username
CALDAV_PASSWORD=your-password

# Optional WebDAV file tools (each storage is enabled only when its URL is set)
# WEBDAV_NOTES_URL=https://<host>/remote.php/dav/files/<user>/<folder>/
# WEBDAV_DRAFTS_URL=https://<host>/remote.php/dav/files/<user>/<folder>/
# WEBDAV_USERNAME=your-username
# WEBDAV_NOTES_PASSWORD=your-password
# WEBDAV_DRAFTS_PASSWORD=your-password
```

The base URL above is the Nextcloud form. Nextcloud users with 2FA enabled must use an app password as `CALDAV_PASSWORD`.

`CALENDAR_TIMEZONE` (IANA name, default `Europe/Berlin`) sets the local time of the tools: event times are returned in it with their UTC offset (e.g. `2026-10-08T14:00:00+02:00`), and tool arguments without an offset are read in it. All-day events are returned as plain dates.

`WEBDAV_NOTES_URL` enables the read-only notes tools, `WEBDAV_DRAFTS_URL` the read-write drafts tools; tools of an unset storage are not listed. `WEBDAV_USERNAME` falls back to `CALDAV_USERNAME`, and `WEBDAV_NOTES_PASSWORD` / `WEBDAV_DRAFTS_PASSWORD` fall back to `CALDAV_PASSWORD`. The URL above is the Nextcloud form.

## Running the Server

### Docker Compose (Recommended)

```bash
docker-compose up -d
```

### Docker

Build and run manually:

```bash
docker build -t fast-calendar-mcp .
docker run -p 8000:8000 --env-file .env fast-calendar-mcp
```

### Local Development

1. **Install dependencies**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Run the server**:
   ```bash
   uvicorn src.main:app --host 0.0.0.0 --port 8000
   ```

The MCP endpoint will be available at `http://localhost:8000/mcp` (Streamable HTTP).

## MCP Tools

This server exposes the following tools to MCP clients:

| Tool | Description | Arguments |
|------|-------------|-----------|
| `calendar_list` | List available calendars. | None |
| `calendar_list_events` | List events overlapping a date range (including events that started before it), sorted by start. | `start_date` (ISO), `end_date` (ISO, date-only values include the full day), `calendar_name` (optional) |
| `calendar_create_event` | Create a new event. | `calendar_name`, `summary`, `start`, `end`, `description` (opt), `location` (opt) |
| `calendar_delete_event` | Delete an event by UID. For a recurring UID this deletes the whole series. | `calendar_name`, `uid` |
| `calendar_sync` | Force a sync with the remote server. | None |
| `notes_list` | List files and folders in the read-only notes storage (needs `WEBDAV_NOTES_URL`). | `path` (opt, '' = root) |
| `notes_read` | Read a file from the notes storage. | `path` |
| `drafts_list` | List files and folders in the drafts storage (needs `WEBDAV_DRAFTS_URL`). | `path` (opt, '' = root) |
| `drafts_read` | Read a file from the drafts storage. | `path` |
| `drafts_write` | Create or overwrite a file in the drafts storage. | `path`, `content` |
| `drafts_delete` | Delete a file from the drafts storage. | `path` |

Times: datetimes without an offset (list and create) are read in `CALENDAR_TIMEZONE`. Returned `start`/`end` are in that timezone with UTC offset; all-day events are plain dates. Each event includes `uid`, `summary`, `description`, `start`, `end`, `all_day`, `recurring`, `location` and `calendar`.

Files: `path` is relative to the storage root. List tools return one path per line, relative to the storage root, with folders ending in `/`; these paths can be passed directly to the read tools. Paths that leave the storage directory (`..`, absolute paths) are rejected. The notes storage refuses writes and deletes client-side. Requests time out after 30 seconds.

## API Endpoints

- **/mcp**: MCP Streamable HTTP endpoint (JSON-RPC over HTTP).

## Testing

Unit tests (no CalDAV server needed):

```bash
python -m pytest tests
```

Run the end-to-end test script to verify functionality against a real CalDAV server:

```bash
python test_e2e.py
```

## License

MIT
