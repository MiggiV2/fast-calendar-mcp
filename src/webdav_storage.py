import posixpath
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote, urlsplit

import httpx

DAV = "{DAV:}"
PROPFIND_BODY = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'


class WebDAVStorageError(Exception):
    pass


class StoragePathError(WebDAVStorageError):
    pass


class ReadOnlyStorageError(WebDAVStorageError):
    pass


class WebDAVStorage:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        writable: bool,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ):
        if not username or not password:
            raise ValueError("WebDAV credentials not set")
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.base_path = unquote(urlsplit(self.base_url).path)
        self.writable = writable
        self.auth = httpx.BasicAuth(username, password)
        self.client = client or httpx.Client(timeout=timeout)

    def list(self, path: str = "") -> list[str]:
        directory = self._relative(path, allow_root=True)
        url = self._url(directory + "/" if directory else "")
        response = self._request(
            "PROPFIND", path, url, headers={"Depth": "1", "Content-Type": "application/xml"}, content=PROPFIND_BODY
        )
        entries = []
        for item in ET.fromstring(response.content).iter(f"{DAV}response"):
            href = unquote(urlsplit(item.findtext(f"{DAV}href", "")).path)
            if not href.startswith(self.base_path):
                continue
            relative = href[len(self.base_path) :].rstrip("/")
            if relative == directory:
                continue
            is_collection = item.find(f".//{DAV}resourcetype/{DAV}collection") is not None
            entries.append(relative + "/" if is_collection else relative)
        return sorted(entries)

    def read(self, path: str) -> str:
        response = self._request("GET", path, self._url(self._relative(path)))
        return response.content.decode("utf-8", errors="replace")

    def write(self, path: str, content: str) -> None:
        self._require_writable()
        self._request("PUT", path, self._url(self._relative(path)), content=content.encode("utf-8"))

    def delete(self, path: str) -> None:
        self._require_writable()
        self._request("DELETE", path, self._url(self._relative(path)))

    def _require_writable(self) -> None:
        if not self.writable:
            raise ReadOnlyStorageError("storage is read-only")

    @staticmethod
    def _relative(path: str, allow_root: bool = False) -> str:
        if path.startswith("/"):
            raise StoragePathError(f"path must be relative: {path}")
        normalized = posixpath.normpath(path or ".")
        if normalized == ".." or normalized.startswith("../"):
            raise StoragePathError(f"path leaves the storage directory: {path}")
        if normalized == ".":
            if not allow_root:
                raise StoragePathError("path must name a file")
            return ""
        return normalized

    def _url(self, relative: str) -> str:
        return self.base_url + quote(relative, safe="/")

    def _request(self, method: str, path: str, url: str, **kwargs) -> httpx.Response:
        try:
            response = self.client.request(method, url, auth=self.auth, **kwargs)
        except httpx.HTTPError as error:
            raise WebDAVStorageError(f"{method} {path} failed: {error}") from error
        if response.status_code == 404:
            raise WebDAVStorageError(f"not found: {path}")
        if response.is_error:
            raise WebDAVStorageError(f"{method} {path} failed: HTTP {response.status_code}")
        return response
