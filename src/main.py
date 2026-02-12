from starlette.applications import Starlette
from starlette.routing import Mount, Route
from mcp.server.sse import SseServerTransport
from dotenv import load_dotenv

# Load env vars BEFORE importing mcp_server which initializes CalDAVWrapper
load_dotenv()

from src.mcp_server import server, run as mcp_run

sse = SseServerTransport("/messages")

from starlette.responses import Response

async def handle_sse(request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options()
        )
    return Response(status_code=200)

async def startup():
    import asyncio
    asyncio.create_task(mcp_run())

routes = [
    Route("/sse", endpoint=handle_sse),
    Mount("/messages", app=sse.handle_post_message),
]

app = Starlette(debug=True, routes=routes, on_startup=[startup])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
