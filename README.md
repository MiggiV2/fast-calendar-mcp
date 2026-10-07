# Fast Calendar MCP

A Model Context Protocol (MCP) server that provides calendar interactions using CalDAV. It syncs events from a CalDAV server (like Nextcloud, iCloud, or Google Calendar) to a local SQLite database for fast access and manipulation.

## Features

- **CalDAV Integration**: Syncs with any standard CalDAV server.
- **Local Caching**: Stores each raw iCalendar object in a local SQLite database (`calendar.db`) for low-latency queries.
- **Recurring Events**: Series are expanded at query time via `recurring-ical-events` (moved/cancelled occurrences, EXDATE, RDATE, UNTIL/COUNT, all-day series, DST-correct wall-clock times).
- **Streamable HTTP Transport**: Implements the MCP Streamable HTTP transport at `/mcp`.
- **Docker Support**: Multi-architecture Docker image (AMD64 & ARM64).
- **CRUD Operations**: Create, Read, and Delete events.

## Prerequisites

- Python 3.11+
- A CalDAV server (e.g., Nextcloud, Baikal, iCloud)

## Configuration

Create a `.env` file in the root directory with your CalDAV credentials:

```env
CALDAV_BASE_URL=https://<host>/remote.php/dav/
CALDAV_USERNAME=your-username
CALDAV_PASSWORD=your-password
```

The base URL above is the Nextcloud form. Nextcloud users with 2FA enabled must use an app password as `CALDAV_PASSWORD`.

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

Times: naive input datetimes (list and create) are interpreted as UTC. Returned `start`/`end` are UTC, naive ISO. Each event includes `uid`, `summary`, `description`, `start`, `end`, `all_day`, `recurring`, `location` and `calendar`.

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
