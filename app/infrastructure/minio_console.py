"""MinIO Console REST client.

The public Viettech host is the browser console, not the S3 API. S3 calls to it
are rejected with "S3 API Requests must be made to API port". The console login
+ object download endpoints speak HTTP Range, which is what clip seeking needs,
so media is fetched through those instead of the MinIO SDK.
"""

from __future__ import annotations

import json
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from minio.error import MinioException


class _ConsoleError(MinioException):
    """Raised when the console REST API cannot serve an object."""


class _Stream:
    """File-like wrapper around a urllib response, matching MinIO's handle."""

    def __init__(self, response: Any) -> None:
        self._response = response

    def read(self, amount: int | None = None) -> bytes:
        response = self._response
        if response is None:
            return b""
        if amount is None:
            return response.read()
        return response.read(amount)

    def close(self) -> None:
        if self._response is not None:
            self._response.close()
            self._response = None

    def release_conn(self) -> None:
        self.close()


class _Stat:
    def __init__(self, size: int) -> None:
        self.size = size


class MinIOConsoleStore:
    """Enough of the MinIO SDK surface for ``api.v1.media`` to proxy objects."""

    _USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )

    def __init__(self, endpoint: str, access_key: str, secret_key: str, *, secure: bool) -> None:
        scheme = "https" if secure else "http"
        self._base = f"{scheme}://{endpoint.rstrip('/')}"
        self._access_key = access_key
        self._secret_key = secret_key
        self._lock = threading.RLock()
        self._cookie_jar = urllib.request.HTTPCookieProcessor()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            self._cookie_jar,
        )
        self._opener.addheaders = [("User-Agent", self._USER_AGENT)]
        self._logged_in = False

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "*/*", "User-Agent": self._USER_AGENT}
        if extra:
            headers.update(extra)
        return headers

    def _login(self) -> None:
        body = json.dumps({"accessKey": self._access_key, "secretKey": self._secret_key}).encode()
        request = urllib.request.Request(
            f"{self._base}/api/v1/login",
            data=body,
            headers=self._headers(
                {"Content-Type": "application/json", "Accept": "application/json"}
            ),
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=20) as response:
                if response.status not in {200, 204}:
                    raise _ConsoleError(f"MinIO console login failed with {response.status}")
        except urllib.error.HTTPError as exc:
            raise _ConsoleError(f"MinIO console login failed: {exc}") from exc
        self._logged_in = True

    def _open(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        retry_login: bool = True,
    ) -> Any:
        request = urllib.request.Request(
            url,
            headers=self._headers(headers),
            method="GET",
        )
        # Cookie jar and opener are not thread-safe. Hold the lock for login
        # *and* the GET that uses the session; body reads happen after return.
        with self._lock:
            if not self._logged_in:
                self._login()
            try:
                return self._opener.open(request, timeout=60)
            except urllib.error.HTTPError as exc:
                if retry_login and exc.code in {401, 403}:
                    self._logged_in = False
                    self._login()
                    return self._open(url, headers=headers, retry_login=False)
                raise _ConsoleError(f"MinIO console request failed: {exc}") from exc
            except urllib.error.URLError as exc:
                raise _ConsoleError(f"MinIO console unreachable: {exc}") from exc

    def stat_object(self, bucket: str, object_key: str) -> _Stat:
        query = urllib.parse.urlencode({"prefix": object_key})
        url = f"{self._base}/api/v1/buckets/{urllib.parse.quote(bucket)}/objects?{query}"
        with self._open(url, headers={"Accept": "application/json"}) as response:
            payload = json.loads(response.read().decode() or "{}")
        for item in payload.get("objects") or []:
            name = item.get("name") or ""
            if name.rstrip("/") == object_key.rstrip("/"):
                return _Stat(int(item.get("size") or 0))
        raise _ConsoleError(f"Object not found: {bucket}/{object_key}")

    def get_object(self, bucket: str, object_key: str, offset: int = 0, length: int = 0) -> _Stream:
        query = urllib.parse.urlencode({"prefix": object_key})
        url = f"{self._base}/api/v1/buckets/{urllib.parse.quote(bucket)}/objects/download?{query}"
        headers: dict[str, str] = {}
        if offset or length:
            end = offset + length - 1 if length else ""
            headers["Range"] = f"bytes={offset}-{end}"
        response = self._open(url, headers=headers)
        return _Stream(response)


__all__ = ["MinIOConsoleStore"]
