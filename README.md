# Fast Calendar MCP

A Model Context Protocol (MCP) server that provides calendar interactions using CalDAV. It syncs events from a CalDAV server (like Nextcloud, iCloud, or Google Calendar) to a local SQLite database for fast access and manipulation.

## Features

- **CalDAV Integration**: Syncs with any standard CalDAV server.
- **Local Caching**: Stores events in a local SQLite database (`calendar.db`) for low-latency queries.
- **HTTP/SSE Transport**: Implements the MCP HTTP with Server-Sent Events (SSE) transport standard.
- **Docker Support**: Multi-architecture Docker image (AMD64 & ARM64).
- **CRUD Operations**: Create, Read, and Delete events.

## Prerequisites

- Python 3.11+
- A CalDAV server (e.g., Nextcloud, Baikal, iCloud)

## Configuration

Create a `.env` file in the root directory with your CalDAV credentials:

```env
CALDAV_BASE_URL=https://your-caldav-server.com/remote.php/dav/
CALDAV_USERNAME=your-username
CALDAV_PASSWORD=your-password
```

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
   python src/main.py
   ```

The server will be available at `http://localhost:8000/sse`.

## MCP Tools

This server exposes the following tools to MCP clients:

| Tool | Description | Arguments |
|------|-------------|-----------|
| `list_calendars` | List available calendars. | None |
| `list_events` | List events within a date range. | `start_date` (ISO), `end_date` (ISO), `calendar_name` (optional) |
| `create_event` | Create a new event. | `calendar_name`, `summary`, `start`, `end`, `description` (opt), `location` (opt) |
| `delete_event` | Delete an event by UID. | `calendar_name`, `uid` |
| `sync_calendar` | Force a sync with the remote server. | None |

## API Endpoints

- **GET /sse**: Establishes the Server-Sent Events connection.
- **POST /messages**: Endpoint for sending JSON-RPC messages to the server.

## Testing

Run the end-to-end test script to verify functionality:

```bash
python test_e2e.py
```

## License

MIT
