"""Local structured diagnostics. Only explicitly selected metadata reaches a sink."""
from __future__ import annotations

import logging
import math
import os
import re
import sys
import ssl
import threading
import time
import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit

from .http_client import HttpClientError

LOGGER = logging.getLogger("steam_price_polisher.events")
LOGGER.addHandler(logging.NullHandler())
LOGGER.propagate = False
_job_id = ContextVar("diagnostic_job_id", default=None)
_configuration_lock = threading.Lock()
_configuration = None

EVENTS = {
    "server_started": logging.INFO, "server_stopped": logging.INFO,
    "server_start_failed": logging.ERROR, "server_request_failed": logging.ERROR,
    "job_queued": logging.INFO, "job_started": logging.INFO,
    "job_cancel_requested": logging.INFO, "job_finished": logging.INFO,
    "job_failed": logging.ERROR, "request_failed": logging.WARNING,
    "request_completed": logging.DEBUG, "cache_access": logging.DEBUG,
    "client_connection_closed": logging.DEBUG,
}
ENUM_FIELDS = {
    "service": {"steam", "nbp", "other"},
    "operation": {"wishlist", "library", "legacy_wishlist", "vanity", "prices", "rates", "other"},
    "state": {"queued", "loading", "running", "cancelling", "cancelled", "complete", "partial", "failed"},
    "reason": {"sigint", "sigterm", "sigbreak", "parent_exited", "keyboard_interrupt", "normal"},
    "category": {"network_access_denied", "tls", "invalid_response", "http_error", "network_failure",
                 "unexpected_error", "request", "vanity", "comparison_failed", "socket_error",
                 "api_key_missing", "api_key_rejected", "library_unavailable", "library_limit"},
    "cache_kind": {"price", "exchange_rate"},
    "source": {"cache", "stale cache", "live", "identity"},
}
NUMBER_FIELDS = {"port", "duration_ms", "attempt", "retry_in_ms", "status_code", "os_error",
                 "total", "checked", "queue_wait_ms", "line"}


def runtime_data_directory():
    return Path(os.environ.get("STEAM_PRICE_POLISHER_DATA_DIR",
                               Path(__file__).resolve().parent.parent / ".steam-price-polisher"))


def _safe_fields(fields):
    result = {}
    for key, value in fields.items():
        if key in ENUM_FIELDS and isinstance(value, str) and value in ENUM_FIELDS[key]:
            result[key] = value
        elif key in NUMBER_FIELDS and type(value) in {int, float} and math.isfinite(value) and value >= 0:
            result[key] = round(value, 3)
        elif key == "will_retry" and type(value) is bool:
            result[key] = value
        elif key == "job_id" and isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{32}", value):
            result[key] = value
        elif key == "exception_type" and isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", value):
            result[key] = value
        elif key == "code_file" and isinstance(value, str) and value in _CODE_FILES:
            result[key] = value
    return result


# Trace locations are limited to this project's known Python modules. Never log
# exception text, absolute paths, source lines, locals, request URLs or headers.
_ROOT = Path(__file__).resolve().parent.parent
_CODE_FILES = {"serve_web.py", "steam_wishlist_compare.py"} | {
    "steam_price_polisher/" + name for name in (
        "event_log.py", "web_app.py", "http_client.py", "request_policy.py", "steam_access.py",
        "exchange_rates.py", "cache.py", "price_service.py", "analysis.py", "comparison.py",
        "configuration.py", "models.py", "owned_library.py",
    )
}


def error_metadata(error):
    """Preserve classification and a code location, never exception messages."""
    result = {"category": "unexpected_error", "exception_type": type(error).__name__}
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, HttpClientError):
            result["category"] = (
                "network_access_denied" if current.network_access_denied else
                "tls" if current.tls_error else "invalid_response" if current.invalid_response else
                "http_error" if current.status_code is not None else "network_failure"
            )
            result["status_code"] = current.status_code
        elif isinstance(current, OSError) and not isinstance(current, ssl.SSLError):
            result["os_error"] = getattr(current, "winerror", None) or current.errno
        pending.extend(value for value in (
            getattr(current, "reason", None), current.__cause__, current.__context__
        ) if isinstance(value, BaseException))
    trace = error.__traceback__
    while trace:
        try:
            filename = Path(trace.tb_frame.f_code.co_filename).resolve().relative_to(_ROOT).as_posix()
        except (OSError, ValueError):
            filename = None
        if filename in _CODE_FILES:
            result.update(code_file=filename, line=trace.tb_lineno)
        trace = trace.tb_next
    return _safe_fields(result)


def request_metadata(url):
    try:
        parsed = urlsplit(url)
        if parsed.hostname == "api.nbp.pl":
            return {"service": "nbp", "operation": "rates"}
        if parsed.hostname in {"api.steampowered.com", "store.steampowered.com"}:
            operation = ("vanity" if parsed.path == "/ISteamUser/ResolveVanityURL/v1/" else
                         "wishlist" if parsed.path == "/IWishlistService/GetWishlist/v1/" else
                         "library" if parsed.path == "/IPlayerService/GetOwnedGames/v1/" else
                         "prices" if parsed.path == "/api/appdetails" else
                         "legacy_wishlist" if parsed.path.startswith("/wishlist/") else "other")
            return {"service": "steam", "operation": operation}
    except ValueError:
        pass
    return {"service": "other", "operation": "other"}


@contextmanager
def job_context(job_id):
    token = _job_id.set(job_id)
    try:
        yield
    finally:
        _job_id.reset(token)


def elapsed_ms(start):
    return (time.monotonic() - start) * 1000


def emit(event, **fields):
    level = EVENTS.get(event)
    if level is None or not LOGGER.isEnabledFor(level):
        return
    fields = {"job_id": _job_id.get(), **fields}
    LOGGER.log(level, event, extra={"event_fields": _safe_fields(fields)})


class JsonEventFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname, "pid": record.process,
            "event": record.msg if isinstance(record.msg, str) and record.msg in EVENTS else "unrecognized_event",
            **_safe_fields(getattr(record, "event_fields", {})),
        }, ensure_ascii=True, allow_nan=False)


class ConsoleEventFormatter(JsonEventFormatter):
    def format(self, record):
        data = json.loads(super().format(record))
        details = " ".join(f"{key}={value}" for key, value in data.items()
                           if key not in {"timestamp", "level", "event"})
        return f"{data['level']} {data['event']} {details}"


class ResilientFileHandler(RotatingFileHandler):
    """A full disk or a blocked log file must not break a comparison."""
    warned = False

    def handleError(self, record):
        if not self.warned:
            self.warned = True
            _warn_unavailable()


class ResilientConsoleHandler(logging.StreamHandler):
    def handleError(self, record):
        # Don't let logging's default error handler dump a record or exception.
        pass


def _warn_unavailable():
    try:
        sys.stderr.write("WARNING event_log_unavailable: continuing with console diagnostics.\n")
    except (OSError, ValueError):
        pass


def configure_event_logging(data_directory=None):
    """One configuration per process; factory calls don't duplicate handlers."""
    global _configuration
    directory = Path(data_directory) if data_directory is not None else runtime_data_directory()
    level = logging.DEBUG if os.environ.get("STEAM_PRICE_POLISHER_LOG_LEVEL", "INFO").upper() == "DEBUG" else logging.INFO
    path = directory / "logs" / f"events-{os.getpid()}.jsonl"
    key = (str(path.absolute()), level)
    with _configuration_lock:
        if _configuration == key:
            return path
        close_event_logging()
        console = ResilientConsoleHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(ConsoleEventFormatter())
        LOGGER.addHandler(console)
        LOGGER.setLevel(level)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = ResilientFileHandler(path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        except OSError:
            _warn_unavailable()
        else:
            handler.setFormatter(JsonEventFormatter())
            LOGGER.addHandler(handler)
        _configuration = key
    return path


def close_event_logging():
    global _configuration
    for handler in LOGGER.handlers[:]:
        LOGGER.removeHandler(handler)
        handler.close()
    LOGGER.addHandler(logging.NullHandler())
    _configuration = None
