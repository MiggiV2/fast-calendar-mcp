import asyncio

import mcp.types as types
import pytest

import src.mcp_server as mcp_server
from src.webdav_storage import WebDAVStorageError


class RecordingStorage:
    def __init__(self):
        self.files: dict[str, str] = {"todo.md": "- [ ] Milch"}
        self.deleted: list[str] = []

    def list(self, path: str) -> list[str]:
        return sorted(self.files)

    def read(self, path: str) -> str:
        if path not in self.files:
            raise WebDAVStorageError(f"not found: {path}")
        return self.files[path]

    def write(self, path: str, content: str) -> None:
        self.files[path] = content

    def delete(self, path: str) -> None:
        self.deleted.append(path)


@pytest.fixture
def storages(monkeypatch):
    notes, drafts = RecordingStorage(), RecordingStorage()
    monkeypatch.setattr(mcp_server, "notes_storage", notes)
    monkeypatch.setattr(mcp_server, "drafts_storage", drafts)
    return notes, drafts


def call(name: str, arguments: dict) -> str:
    [content] = asyncio.run(mcp_server.handle_call_tool(name, arguments))
    return content.text


def tool_names() -> set[str]:
    return {tool.name for tool in asyncio.run(mcp_server.handle_list_tools())}


def test_file_tools_are_listed_when_storages_are_configured(storages):
    assert {"notes_list", "notes_read", "drafts_list", "drafts_read", "drafts_write", "drafts_delete"} <= tool_names()


def test_file_tools_are_hidden_when_storages_are_not_configured(monkeypatch):
    monkeypatch.setattr(mcp_server, "notes_storage", None)
    monkeypatch.setattr(mcp_server, "drafts_storage", None)

    assert not any(name.startswith(("notes_", "drafts_")) for name in tool_names())


def test_notes_read_returns_file_content(storages):
    assert call("notes_read", {"path": "todo.md"}) == "- [ ] Milch"


def test_notes_list_returns_one_path_per_line(storages):
    notes, _ = storages
    notes.files["b.md"] = ""

    assert call("notes_list", {"path": ""}) == "b.md\ntodo.md"


def test_notes_list_defaults_to_root(storages):
    assert call("notes_list", {}) == "todo.md"


def test_drafts_write_stores_content(storages):
    _, drafts = storages

    call("drafts_write", {"path": "new.md", "content": "Hallo"})

    assert drafts.files["new.md"] == "Hallo"


def test_drafts_delete_removes_file(storages):
    _, drafts = storages

    call("drafts_delete", {"path": "todo.md"})

    assert drafts.deleted == ["todo.md"]


def test_storage_errors_are_returned_as_tool_errors(storages):
    request = types.CallToolRequest(
        method="tools/call", params=types.CallToolRequestParams(name="notes_read", arguments={"path": "missing.md"})
    )

    result = asyncio.run(mcp_server.server.request_handlers[types.CallToolRequest](request)).root

    assert result.isError
    assert result.content[0].text == "not found: missing.md"


@pytest.fixture
def no_credentials_in_env(monkeypatch):
    for name in ("WEBDAV_USERNAME", "CALDAV_USERNAME", "WEBDAV_NOTES_PASSWORD", "CALDAV_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WEBDAV_NOTES_URL", "https://cloud.example/remote.php/dav/files/alice/Notes/")


def test_storage_with_url_but_without_credentials_is_disabled_with_an_error(no_credentials_in_env, caplog):
    assert mcp_server._storage_from_env("WEBDAV_NOTES", writable=False) is None
    assert "WEBDAV_NOTES" in caplog.text
    assert "credentials" in caplog.text


def test_storage_falls_back_to_caldav_credentials(no_credentials_in_env, monkeypatch):
    monkeypatch.setenv("CALDAV_USERNAME", "alice")
    monkeypatch.setenv("CALDAV_PASSWORD", "secret")

    assert mcp_server._storage_from_env("WEBDAV_NOTES", writable=False) is not None


def test_file_tools_work_without_caldav(storages, monkeypatch):
    monkeypatch.setattr(mcp_server, "caldav_wrapper", None)

    assert call("notes_read", {"path": "todo.md"}) == "- [ ] Milch"
