"""Shared request pacing and retry policies."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .http_client import HttpClientError, JsonHttpClient


class RequestGate:
    """Thread-safe gate enforcing one global request schedule."""

    def __init__(
        self,
        minimum_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if minimum_interval < 0:
            raise ValueError("minimum_interval cannot be negative")
        self._minimum_interval = minimum_interval
        self._clock = clock
        self._sleep = sleep
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            delay = max(0.0, self._next_allowed - now)
            if delay:
                self._sleep(delay)
                now = self._clock()
            self._next_allowed = max(self._next_allowed, now) + self._minimum_interval

    def defer(self, seconds: float) -> None:
        with self._lock:
            self._next_allowed = max(
                self._next_allowed,
                self._clock() + max(0.0, seconds),
            )


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay: float = 2.0
    maximum_delay: float = 60.0
    jitter_ratio: float = 0.25

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.base_delay < 0 or self.maximum_delay < 0:
            raise ValueError("retry delays cannot be negative")
        if self.jitter_ratio < 0:
            raise ValueError("jitter_ratio cannot be negative")


class RetryingJsonHttpClient:
    """JSON client decorator with transient-failure retries and backoff."""

    def __init__(
        self,
        upstream: JsonHttpClient,
        *,
        policy: RetryPolicy = RetryPolicy(),
        gate: RequestGate | None = None,
        sleep: Callable[[float], None] = time.sleep,
        uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._upstream = upstream
        self._policy = policy
        self._gate = gate
        self._sleep = sleep
        self._uniform = uniform

    def get_json(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        for attempt in range(self._policy.max_attempts):
            if self._gate is not None:
                self._gate.wait()
            try:
                return self._upstream.get_json(url, headers)
            except HttpClientError as exc:
                is_last_attempt = attempt + 1 >= self._policy.max_attempts
                if not exc.transient or is_last_attempt:
                    raise

                delay = self._retry_delay(attempt, exc.retry_after)
                if self._gate is not None:
                    self._gate.defer(delay)
                else:
                    self._sleep(delay)

        raise AssertionError("retry loop completed without returning or raising")

    def _retry_delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(self._policy.maximum_delay, retry_after)
        base = min(
            self._policy.maximum_delay,
            self._policy.base_delay * (2**attempt),
        )
        jitter = self._uniform(0.0, base * self._policy.jitter_ratio)
        return min(self._policy.maximum_delay, base + jitter)
