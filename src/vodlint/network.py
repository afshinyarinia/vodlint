from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import url2pathname

import requests

from . import __version__

MAX_RESOURCE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_REQUESTS = 1000


class ResourceError(OSError):
    """An expected resource failure safe to include in a report."""


class _BoundedSession(requests.Session):
    def resolve_redirects(self, *args, **kwargs):
        # Session.send prepares a next request even with allow_redirects=False,
        # consuming the redirect body first. Handle redirects ourselves so every
        # response body passes through the same bounded reader.
        return iter(())


@dataclass(frozen=True)
class Resource:
    data: bytes
    location: str


@dataclass
class HttpClient:
    """One analysis session for bounded local and HTTP resource reads.

    timeout_seconds is a connect/read inactivity timeout, not a total
    analysis deadline. Request budgets count resource fetches, excluding
    redirects and configured transport retries.
    """

    timeout_seconds: float = 10.0
    retries: int = 2
    user_agent: str = f"vodlint/{__version__}"
    max_resource_bytes: int = MAX_RESOURCE_BYTES
    max_total_bytes: int = MAX_TOTAL_BYTES
    max_requests: int = MAX_REQUESTS
    bytes_read: int = field(default=0, init=False)
    requests_made: int = field(default=0, init=False)
    _http: requests.Session | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout must be finite and greater than zero")
        for name in ("retries", "max_resource_bytes", "max_total_bytes", "max_requests"):
            value = getattr(self, name)
            minimum = 0 if name == "retries" else 1
            if not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")

    def __enter__(self):
        self._http = _BoundedSession()
        self._http.headers.update({"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
        return self

    def __exit__(self, *args):
        if self._http is not None:
            self._http.close()
            self._http = None

    def get_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        return self.fetch(url, headers=headers).data

    def fetch(
        self,
        location: str,
        *,
        byte_range: tuple[int, int] | None = None,
        max_bytes: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> Resource:
        if self.requests_made >= self.max_requests:
            raise ResourceError("Resource request limit exceeded.")
        self.requests_made += 1
        limit = min(
            self.max_resource_bytes,
            self.max_total_bytes - self.bytes_read,
            max_bytes if max_bytes is not None else self.max_resource_bytes,
        )
        if limit <= 0:
            raise ResourceError("Total byte limit exceeded.")
        if byte_range is not None:
            start, length = byte_range
            if start < 0 or length <= 0:
                raise ResourceError("Invalid byte range.")
            if length > limit:
                raise ResourceError("Byte range exceeds byte limit.")

        # Windows drive letters are paths, never URI schemes.
        try:
            scheme = "" if re.match(r"^[A-Za-z]:[\\/]", location) else urlsplit(location).scheme
            if scheme in ("http", "https"):
                return self._fetch_http(location, byte_range, limit, headers)
            if scheme not in ("", "file"):
                raise ResourceError("Unsupported resource scheme; use HTTP(S) or a local file.")
            if scheme == "file":
                parsed = urlsplit(location)
                if parsed.netloc not in ("", "localhost"):
                    raise ResourceError("Remote file authorities are unsupported.")
                path = Path(url2pathname(parsed.path))
            else:
                path = Path(location)
            with path.open("rb") as stream:
                if byte_range:
                    stream.seek(byte_range[0])
                    data = stream.read(byte_range[1])
                else:
                    data = stream.read(limit + 1)
            self._account(len(data), limit)
            if byte_range and len(data) != byte_range[1]:
                raise ResourceError("Byte range is shorter than the declared length.")
            return Resource(data, path.resolve().as_uri())
        except ResourceError:
            raise
        except (OSError, requests.RequestException, ValueError) as error:
            # Do not leak signed URLs, credentials or response bodies via exception text.
            raise ResourceError(f"Resource fetch failed ({type(error).__name__}).") from error

    def _account(self, size: int, limit: int):
        self.bytes_read += size
        if size > limit:
            raise ResourceError("Resource or total byte limit exceeded.")

    def _fetch_http(self, location, byte_range, limit, headers):
        # Standalone get_bytes owns a session; orchestration explicitly shares one.
        if self._http is None:
            with self:
                return self._fetch_http(location, byte_range, limit, headers)
        request_headers = requests.structures.CaseInsensitiveDict(headers or {})
        if byte_range:
            start, length = byte_range
            request_headers["Range"] = f"bytes={start}-{start + length - 1}"
        initial_bytes = self.bytes_read
        retries = 0
        redirects = 0
        while True:
            remaining = limit - (self.bytes_read - initial_bytes)
            if remaining <= 0:
                raise ResourceError("Resource or total byte limit exceeded.")
            try:
                response = self._http.get(
                    location,
                    headers=request_headers,
                    timeout=self.timeout_seconds,
                    stream=True,
                    allow_redirects=False,
                )
            except (requests.ConnectionError, requests.Timeout):
                if retries >= self.retries:
                    raise
                retries += 1
                self._retry_pause(retries)
                continue
            with response:
                if response.is_redirect:
                    self._read_response(response, remaining)
                    redirects += 1
                    if redirects > self._http.max_redirects:
                        raise ResourceError("HTTP redirect limit exceeded.")
                    target = urljoin(response.url, response.headers["Location"])
                    if self._http.should_strip_auth(location, target):
                        request_headers.pop("Authorization", None)
                    request_headers.pop("Cookie", None)
                    location = target
                    continue
                if response.status_code in (502, 503, 504) and retries < self.retries:
                    self._read_response(response, remaining)
                    retries += 1
                    self._retry_pause(retries)
                    continue
                response.raise_for_status()
                if byte_range:
                    start, length = byte_range
                    match = re.fullmatch(
                        r"bytes (\d+)-(\d+)/(\d+|\*)",
                        response.headers.get("Content-Range", ""),
                    )
                    if (
                        response.status_code != 206
                        or match is None
                        or int(match[1]) != start
                        or int(match[2]) != start + length - 1
                        or (match[3] != "*" and int(match[3]) <= int(match[2]))
                        or response.headers.get("Content-Encoding", "identity") != "identity"
                    ):
                        raise ResourceError("Server returned an invalid or ignored byte range.")
                elif response.status_code == 206:
                    raise ResourceError("Unexpected partial response to a full-resource request.")
                data = self._read_response(response, remaining)
                if byte_range and len(data) != byte_range[1]:
                    raise ResourceError("Byte range is shorter than the declared length.")
                return Resource(data, response.url)

    def _read_response(self, response, limit):
        content_length = response.headers.get("Content-Length", "")
        if content_length.isdigit() and int(content_length) > limit:
            raise ResourceError("Resource exceeds byte limit.")
        data = bytearray()
        for chunk in response.iter_content(chunk_size=min(65536, limit + 1)):
            self._account(len(chunk), limit - len(data))
            data.extend(chunk)
        return bytes(data)

    @staticmethod
    def _retry_pause(attempt):
        if attempt > 1:
            time.sleep(min(0.3 * 2 ** min(attempt - 1, 5), 5.0))
