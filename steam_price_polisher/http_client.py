"""Small injectable JSON HTTP client built on the Python standard library."""

from __future__ import annotations

import http.cookiejar
import errno
import json
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
        network_access_denied: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.transient = transient
        self.invalid_response = invalid_response
        self.tls_error = tls_error
        self.network_access_denied = network_access_denied


NETWORK_ACCESS_MESSAGE = (
    "This server's network access is blocked by local permissions "
    "(such as a sandbox or firewall). Restart the server with outbound network "
    "access to Steam and the exchange-rate service, then retry."
)


def is_network_access_denied(error: BaseException, *, include_os_errors: bool = False) -> bool:
    """Follow classified transport failures; inspect OS codes only at the HTTP boundary."""
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, HttpClientError) and current.network_access_denied:
            return True
        # SSL error numbers use a different namespace (SSL_ERROR_SSL is also 1).
        if include_os_errors and isinstance(current, OSError) and not isinstance(current, ssl.SSLError) and (
            current.errno in {errno.EACCES, errno.EPERM, 10013}
            or getattr(current, "winerror", None) == 10013
        ):
            return True
        pending.extend(value for value in (
            getattr(current, "reason", None), current.__cause__, current.__context__
        ) if isinstance(value, BaseException))
    return False


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
        except OSError as exc:
            if is_network_access_denied(exc, include_os_errors=True):
                raise HttpClientError(
                    NETWORK_ACCESS_MESSAGE, network_access_denied=True,
                ) from exc
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
