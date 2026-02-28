from contextlib import asynccontextmanager
from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from dotenv import load_dotenv

# Load env vars BEFORE importing mcp_server which initializes CalDAVWrapper
load_dotenv()

from src.mcp_server import server, run as mcp_run

session_manager = StreamableHTTPSessionManager(server)

async def handle_mcp(scope, receive, send):
    await session_manager.handle_request(scope, receive, send)

@asynccontextmanager
async def lifespan(app):
    import asyncio
    asyncio.create_task(mcp_run())
    async with session_manager.run():
        yield

app = Starlette(
    debug=True,
    routes=[Mount("/mcp", app=handle_mcp)],
    lifespan=lifespan,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
