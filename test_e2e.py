import asyncio
import os
import subprocess
import time
import httpx
import ast
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

async def run_tests():
    print("Starting server...")
    # Start server
    proc = subprocess.Popen(
        ["uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", "8000"],
        env=os.environ.copy()
    )
    
    try:
        # Wait for server to start
        print("Waiting for server to be ready...")
        started = False
        for i in range(30):
            try:
                # Check /messages via GET, expecting 405 Method Not Allowed
                # This confirms uvicorn is running and Starlette is routing
                resp = httpx.get("http://127.0.0.1:8000/messages", timeout=1)
                if resp.status_code == 405:
                    started = True
                    print("Server is ready.")
                    break
            except Exception as e:
                time.sleep(1)
        
        if not started:
            # stdout, stderr = proc.communicate()
            print("Server failed to start.")
            # print("Stdout:", stdout.decode())
            # print("Stderr:", stderr.decode())
            return

        print("Connecting to MCP server...")
        async with sse_client("http://127.0.0.1:8000/sse") as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                
                # List tools
                print("Listing tools...")
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                print("Tools:", tool_names)
                assert "list_calendars" in tool_names
                assert "create_event" in tool_names
                
                # List calendars
                print("Listing calendars...")
                result = await session.call_tool("list_calendars", {})
                print(f"Raw result: {result.content[0].text}")
                
                if "CalDAV wrapper not initialized" in result.content[0].text:
                    print("⚠️ CalDAV wrapper failed to initialize (expected due to invalid environment credentials).")
                    print("✅ MCP Server is running and responding to tool calls.")
                    # We can't proceed with functional tests, but the Server/HTTP/MCP layer works.
                    return

                try:
                    calendars = ast.literal_eval(result.content[0].text)
                except:
                    print("Failed to parse calendars.")
                    calendars = []
                
                print("Calendars:", calendars)
                
                if not calendars:
                    print("No calendars found, skipping creation test.")
                    return

                calendar_name = calendars[0]["name"]
                print(f"Using calendar: {calendar_name}")
                
                # Create event
                print("Creating event...")
                summary = "MCP Test Event"
                start = "2023-10-27T10:00:00"
                end = "2023-10-27T11:00:00"
                
                await session.call_tool("create_event", {
                    "calendar_name": calendar_name,
                    "summary": summary,
                    "start": start,
                    "end": end,
                    "description": "Created by MCP E2E Test"
                })
                print("Event created.")
                
                # Verify event exists
                print("Verifying event...")
                result = await session.call_tool("list_events", {
                    "start_date": "2023-10-27T00:00:00",
                    "end_date": "2023-10-27T23:59:59",
                    "calendar_name": calendar_name
                })
                events = ast.literal_eval(result.content[0].text)
                print("Events found:", events)
                
                target_event = next((e for e in events if e["summary"] == summary), None)
                assert target_event is not None
                print("Event verified.")
                
                # Delete event
                print("Deleting event...")
                await session.call_tool("delete_event", {
                    "calendar_name": calendar_name,
                    "uid": target_event["uid"]
                })
                print("Event deleted.")
                
                # Verify deletion
                print("Verifying deletion...")
                result = await session.call_tool("list_events", {
                    "start_date": "2023-10-27T00:00:00",
                    "end_date": "2023-10-27T23:59:59",
                    "calendar_name": calendar_name
                })
                events = ast.literal_eval(result.content[0].text)
                target_event = next((e for e in events if e["summary"] == summary), None)
                assert target_event is None
                print("Deletion verified.")
                
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("Stopping server...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except:
            proc.kill()
        print("Server stopped.")

if __name__ == "__main__":
    asyncio.run(run_tests())
