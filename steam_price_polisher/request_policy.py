"""Shared request pacing and retry policies."""

from __future__ import annotations

from contextlib import contextmanager
import random
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .http_client import HttpClientError, JsonHttpClient
from .event_log import emit, elapsed_ms, error_metadata, request_metadata


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

    def wait(self, *, sleep=None) -> None:
        with self._lock:
            now = self._clock()
            delay = max(0.0, self._next_allowed - now)
            if delay:
                (sleep or self._sleep)(delay)
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
        self.attempts = 0
        self._attempt_deadline = None

    @contextmanager
    def limit_attempts(self, maximum):
        """Share a physical-attempt ceiling across batch recovery children."""
        previous = self._attempt_deadline
        self._attempt_deadline = min(previous, self.attempts + maximum) if previous is not None else self.attempts + maximum
        try:
            yield
        finally:
            self._attempt_deadline = previous

    def get_json(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        for attempt in range(self._policy.max_attempts):
            if self._attempt_deadline is not None and self.attempts >= self._attempt_deadline:
                raise HttpClientError("Batch attempt budget exhausted")
            if self._gate is not None:
                self._gate.wait(sleep=self._sleep if self._sleep is not time.sleep else None)
            self.attempts += 1
            started = time.monotonic()
            try:
                result = self._upstream.get_json(url, headers)
                emit("request_completed", **request_metadata(url), attempt=attempt + 1,
                     duration_ms=elapsed_ms(started))
                return result
            except HttpClientError as exc:
                is_last_attempt = attempt + 1 >= self._policy.max_attempts
                will_retry = exc.transient and not is_last_attempt
                delay = self._retry_delay(attempt, exc.retry_after) if will_retry else 0
                emit("request_failed", **request_metadata(url), **error_metadata(exc),
                     attempt=attempt + 1, duration_ms=elapsed_ms(started),
                     will_retry=will_retry, retry_in_ms=delay * 1000)
                if not will_retry:
                    if self._gate is not None and exc.status_code == 429:
                        self._gate.defer(self._retry_delay(attempt, exc.retry_after))
                    raise

                if self._gate is not None:
                    self._gate.defer(delay)
                else:
                    self._sleep(delay)

        raise AssertionError("retry loop completed without returning or raising")

    def _retry_delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return max(0, retry_after)
        base = min(
            self._policy.maximum_delay,
            self._policy.base_delay * (2**attempt),
        )
        jitter = self._uniform(0.0, base * self._policy.jitter_ratio)
        return min(self._policy.maximum_delay, base + jitter)
