import httpx
import pytest

from src.webdav_storage import ReadOnlyStorageError, StoragePathError, WebDAVStorage, WebDAVStorageError

BASE_URL = "https://cloud.example/remote.php/dav/files/alice/Notes/"


def multistatus(*responses: str) -> str:
    return (
        '<?xml version="1.0"?>\n<d:multistatus xmlns:d="DAV:" xmlns:s="http://sabredav.org/ns" '
        'xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns">'
        + "".join(responses)
        + "</d:multistatus>"
    )


def entry(href: str, collection: bool) -> str:
    resourcetype = "<d:resourcetype><d:collection/></d:resourcetype>" if collection else "<d:resourcetype/>"
    return (
        f"<d:response><d:href>{href}</d:href><d:propstat><d:prop>{resourcetype}</d:prop>"
        "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
    )


class RecordingServer:
    def __init__(self, handler):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def storage_with(handler, writable: bool = True) -> tuple[WebDAVStorage, RecordingServer]:
    server = RecordingServer(handler)
    client = httpx.Client(transport=httpx.MockTransport(server))
    return WebDAVStorage(BASE_URL, "alice", "secret", writable=writable, client=client), server


def test_list_returns_paths_relative_to_base_without_the_listed_directory():
    body = multistatus(
        entry("/remote.php/dav/files/alice/Notes/Rezepte/", collection=True),
        entry("/remote.php/dav/files/alice/Notes/Rezepte/Pizza%20Teig.md", collection=False),
        entry("/remote.php/dav/files/alice/Notes/Rezepte/Kuchen/", collection=True),
    )
    storage, server = storage_with(lambda request: httpx.Response(207, text=body))

    assert storage.list("Rezepte") == ["Rezepte/Kuchen/", "Rezepte/Pizza Teig.md"]
    assert server.requests[0].method == "PROPFIND"
    assert server.requests[0].headers["Depth"] == "1"


def test_listed_file_path_can_be_read_back():
    body = multistatus(
        entry("/remote.php/dav/files/alice/Notes/", collection=True),
        entry("/remote.php/dav/files/alice/Notes/Pizza%20Teig.md", collection=False),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PROPFIND":
            return httpx.Response(207, text=body)
        return httpx.Response(200, content="Mehl, Wasser".encode())

    storage, server = storage_with(handler)

    [listed] = storage.list("")
    assert storage.read(listed) == "Mehl, Wasser"
    assert str(server.requests[1].url) == BASE_URL + "Pizza%20Teig.md"


def test_paths_with_special_characters_are_url_encoded():
    storage, server = storage_with(lambda request: httpx.Response(200, content=b""))

    storage.read("Über uns/#1 Ideen.md")

    assert server.requests[0].url.raw_path.decode() == (
        "/remote.php/dav/files/alice/Notes/%C3%9Cber%20uns/%231%20Ideen.md"
    )


@pytest.mark.parametrize("path", ["../secret.md", "a/../../secret.md", "/etc/passwd", "..", "a/./../.."])
def test_paths_escaping_the_base_directory_are_rejected(path):
    storage, server = storage_with(lambda request: httpx.Response(200, content=b""))

    with pytest.raises(StoragePathError):
        storage.read(path)
    with pytest.raises(StoragePathError):
        storage.delete(path)
    assert server.requests == []


def test_path_inside_the_base_directory_is_normalized():
    storage, server = storage_with(lambda request: httpx.Response(200, content=b""))

    storage.read("a/../b/./c.md")

    assert str(server.requests[0].url) == BASE_URL + "b/c.md"


def test_base_url_without_trailing_slash_still_targets_its_children():
    server = RecordingServer(lambda request: httpx.Response(200, content=b""))
    client = httpx.Client(transport=httpx.MockTransport(server))
    storage = WebDAVStorage(BASE_URL.rstrip("/"), "alice", "secret", writable=False, client=client)

    storage.read("note.md")

    assert str(server.requests[0].url) == BASE_URL + "note.md"


def test_missing_file_raises_readable_error():
    storage, _ = storage_with(lambda request: httpx.Response(404))

    with pytest.raises(WebDAVStorageError, match="not found: missing.md"):
        storage.read("missing.md")


def test_write_puts_utf8_content():
    storage, server = storage_with(lambda request: httpx.Response(201))

    storage.write("draft.md", "Grüße")

    assert server.requests[0].method == "PUT"
    assert server.requests[0].content == "Grüße".encode()


def test_write_rejects_the_base_directory_itself():
    storage, server = storage_with(lambda request: httpx.Response(201))

    with pytest.raises(StoragePathError):
        storage.write("", "content")
    assert server.requests == []


def test_delete_sends_delete():
    storage, server = storage_with(lambda request: httpx.Response(204))

    storage.delete("draft.md")

    assert server.requests[0].method == "DELETE"
    assert str(server.requests[0].url) == BASE_URL + "draft.md"


def test_read_only_storage_refuses_writes_and_deletes():
    storage, server = storage_with(lambda request: httpx.Response(201), writable=False)

    with pytest.raises(ReadOnlyStorageError):
        storage.write("draft.md", "content")
    with pytest.raises(ReadOnlyStorageError):
        storage.delete("draft.md")
    assert server.requests == []


def test_requests_use_basic_auth():
    storage, server = storage_with(lambda request: httpx.Response(200, content=b""))

    storage.read("note.md")

    assert server.requests[0].headers["Authorization"].startswith("Basic ")
