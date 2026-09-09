"""Small injectable JSON HTTP client built on the Python standard library."""

from __future__ import annotations

import http.cookiejar
import json
import socket
import ssl

import truststore
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol


class JsonHttpClient(Protocol):
    def get_json(self, url: str, headers: Mapping[str, str] | None = None) -> Any:
        """Return a decoded JSON response."""


class HttpClientError(RuntimeError):
    """Structured HTTP or transport failure used by retry policies."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
        transient: bool = False,
        invalid_response: bool = False,
        tls_error: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.transient = transient
        self.invalid_response = invalid_response
        self.tls_error = tls_error


class UrllibJsonHttpClient:
    def __init__(self, cookie_string: str = "", timeout: float = 15.0) -> None:
        cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar),
            urllib.request.HTTPSHandler(context=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)),
        )
        self._cookie_string = cookie_string
        self._timeout = timeout

    def get_json(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        request_headers = dict(headers or {})
        request_headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36",
        )
        if self._cookie_string:
            request_headers["Cookie"] = self._cookie_string

        request = urllib.request.Request(url, headers=request_headers)
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            retry_after = _parse_retry_after(exc.headers.get("Retry-After"))
            transient = exc.code == 429 or 500 <= exc.code <= 599
            raise HttpClientError(
                f"HTTP {exc.code} for {url}",
                status_code=exc.code,
                retry_after=retry_after,
                transient=transient,
            ) from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as exc:
            if isinstance(getattr(exc, "reason", exc), ssl.SSLError):
                raise HttpClientError(
                    "The server could not verify the secure connection to the upstream service.",
                    tls_error=True,
                ) from exc
            raise HttpClientError(
                f"Temporary network failure for {url}: {exc}",
                transient=True,
            ) from exc

        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise HttpClientError(
                f"Invalid JSON response from {url}",
                invalid_response=True,
            ) from exc


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
