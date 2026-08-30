"""Small injectable JSON HTTP client built on the Python standard library."""

from __future__ import annotations

import http.cookiejar
import json
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol


class JsonHttpClient(Protocol):
    def get_json(self, url: str, headers: Mapping[str, str] | None = None) -> Any:
        """Return a decoded JSON response."""


class UrllibJsonHttpClient:
    def __init__(self, cookie_string: str = "", timeout: float = 15.0) -> None:
        cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar)
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
        with self._opener.open(request, timeout=self._timeout) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload)
