import io
import json
import logging
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from steam_price_polisher import event_log
from steam_price_polisher.configuration import ComparisonConfig
from steam_price_polisher.http_client import HttpClientError
from steam_price_polisher.request_policy import RetryingJsonHttpClient, RetryPolicy
from steam_price_polisher.web_app import JobManager


class EventLogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.console = io.StringIO()
        self.enterContext(patch("sys.stderr", self.console))
        self.enterContext(patch.dict(os.environ, {"STEAM_PRICE_POLISHER_LOG_LEVEL": "INFO"}))
        self.path = event_log.configure_event_logging(self.directory.name)
        self.addCleanup(event_log.close_event_logging)

    def events(self):
        return [json.loads(line) for line in self.path.read_text().splitlines()]

    def test_allowlisted_json_drops_secrets_and_unstructured_messages(self):
        secret = "secret-cookie-key-profile-wishlist"
        event_log.emit("server_started", port=8765, url=secret, token=secret, profile=secret,
                       headers={"Cookie": secret}, exception=RuntimeError(secret), message=secret,
                       job_id="X" * 43, duration_ms=float("nan"), service=secret)
        event_log.LOGGER.error(secret, exc_info=RuntimeError(secret))
        data = self.events()
        self.assertEqual(data[0]["event"], "server_started")
        self.assertEqual(data[0]["port"], 8765)
        self.assertEqual(data[0]["pid"], os.getpid())
        self.assertEqual(datetime.fromisoformat(data[0]["timestamp"]).utcoffset().total_seconds(), 0)
        self.assertNotIn(secret, self.path.read_text() + self.console.getvalue())
        self.assertNotIn("job_id", data[0])
        self.assertNotIn("duration_ms", data[0])
        self.assertEqual(data[1]["event"], "unrecognized_event")

    def test_retry_events_have_safe_service_attempt_and_debug_success(self):
        os.environ["STEAM_PRICE_POLISHER_LOG_LEVEL"] = "DEBUG"
        event_log.configure_event_logging(self.directory.name)
        raw = Mock()
        raw.get_json.side_effect = [HttpClientError("secret", status_code=429, transient=True), {"secret": 1}]
        client = RetryingJsonHttpClient(raw, policy=RetryPolicy(max_attempts=2, base_delay=0))
        with event_log.job_context("A" * 32):
            client.get_json("https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key=secret&vanityurl=private",
                            {"Cookie": "secret"})
        data = self.events()
        self.assertEqual([row["event"] for row in data], ["request_failed", "request_completed"])
        self.assertEqual([row["attempt"] for row in data], [1, 2])
        self.assertEqual(data[0]["service"], "steam")
        self.assertEqual(data[0]["operation"], "vanity")
        self.assertEqual(data[0]["status_code"], 429)
        self.assertTrue(data[0]["will_retry"])
        self.assertTrue(all(row["job_id"] == "A" * 32 and row["duration_ms"] >= 0 for row in data))
        self.assertNotIn("secret", self.path.read_text() + self.console.getvalue())
        self.assertNotIn("private", self.path.read_text())
        self.assertNotIn("request_completed", self.console.getvalue())

    def test_normal_level_omits_success_and_cache_noise(self):
        raw = Mock()
        raw.get_json.return_value = {}
        RetryingJsonHttpClient(raw).get_json("https://api.nbp.pl/secret")
        event_log.emit("cache_access", cache_kind="price", source="cache")
        self.assertEqual(self.events(), [])
        os.environ["STEAM_PRICE_POLISHER_LOG_LEVEL"] = "DEBUG"
        event_log.configure_event_logging(self.directory.name)
        event_log.emit("cache_access", cache_kind="price", source="cache", app_id="secret")
        self.assertEqual(self.events()[0]["source"], "cache")
        self.assertNotIn("secret", self.path.read_text())

    def test_simultaneous_jobs_keep_request_correlation_isolated(self):
        barrier = threading.Barrier(2)
        def work(job):
            barrier.wait(timeout=3)
            raw = Mock()
            raw.get_json.side_effect = HttpClientError("secret-key-private-path", network_access_denied=True)
            RetryingJsonHttpClient(raw).get_json("https://store.steampowered.com/api/appdetails?appids=secret")
        manager = JobManager(self.directory.name, start_worker=False, runner=work)
        jobs = [manager.submit("secret-profile", ComparisonConfig(), "secret-owner-" + str(index)) for index in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(manager.execute, jobs))
        data = self.events()
        for job in jobs:
            related = [row for row in data if row.get("job_id") == job.id]
            self.assertEqual([row["event"] for row in related],
                             ["job_queued", "job_started", "request_failed", "job_failed"])
            self.assertEqual(related[-1]["category"], "network_access_denied")
            self.assertEqual(related[-1]["code_file"], "steam_price_polisher/request_policy.py")
            self.assertNotIn(job.token, self.path.read_text())
        event_log.emit("server_stopped", reason="normal")
        self.assertNotIn("job_id", self.events()[-1])
        self.assertNotIn("secret", self.path.read_text() + self.console.getvalue())

    def test_complete_cancel_and_controlled_failure_emit_terminal_events(self):
        manager = JobManager(self.directory.name, start_worker=False,
                             runner=lambda job: job.update(state="complete", total=7))
        complete = manager.submit("private", ComparisonConfig(), "a")
        manager.execute(complete)
        cancelled = manager.submit("private", ComparisonConfig(), "b")
        manager.cancel_job(cancelled)
        manager.execute(cancelled)
        manager.runner = lambda job: job.update(state="failed", error="secret", error_code="tls")
        failed = manager.submit("private", ComparisonConfig(), "c")
        manager.execute(failed)
        terminal = [row for row in self.events() if row["event"] in {"job_finished", "job_failed"}]
        self.assertEqual([row["state"] for row in terminal], ["complete", "cancelled", "failed"])
        self.assertEqual(terminal[0]["total"], 7)
        self.assertEqual(terminal[2]["category"], "tls")
        self.assertNotIn("secret", self.path.read_text())

    def test_rotating_files_are_bounded_and_parseable(self):
        handler = next(h for h in event_log.LOGGER.handlers if isinstance(h, event_log.ResilientFileHandler))
        handler.maxBytes, handler.backupCount = 600, 2
        for _ in range(30):
            event_log.emit("server_started", port=8765)
        files = list(self.path.parent.glob("events-*"))
        self.assertEqual(len(files), 3)
        for path in files:
            self.assertLessEqual(path.stat().st_size, 600)
            self.assertTrue(all(json.loads(line)["event"] == "server_started" for line in path.read_text().splitlines()))

    def test_reconfiguration_is_idempotent_and_leaves_root_logger_alone(self):
        handlers = list(event_log.LOGGER.handlers)
        root_handlers = list(logging.getLogger().handlers)
        event_log.configure_event_logging(self.directory.name)
        self.assertEqual(event_log.LOGGER.handlers, handlers)
        self.assertEqual(logging.getLogger().handlers, root_handlers)
        event_log.emit("server_started", port=8765)
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.console.getvalue().count("server_started"), 1)

    def test_unwritable_directory_falls_back_without_exposing_path(self):
        blocked = Path(self.directory.name) / "secret-path"
        blocked.write_text("not a directory")
        event_log.configure_event_logging(blocked)
        event_log.emit("server_started", port=8765)
        self.assertIn("event_log_unavailable", self.console.getvalue())
        self.assertIn("server_started", self.console.getvalue())
        self.assertNotIn("secret-path", self.console.getvalue())

    def test_write_failure_does_not_break_jobs_or_dump_exception(self):
        handler = next(h for h in event_log.LOGGER.handlers if isinstance(h, event_log.ResilientFileHandler))
        with patch.object(handler.stream, "write", side_effect=OSError("secret-path-disk-full")):
            event_log.emit("server_started", port=8765)
            event_log.emit("server_stopped", port=8765, reason="sigint")
        self.assertEqual(self.console.getvalue().count("event_log_unavailable"), 1)
        self.assertNotIn("secret-path-disk-full", self.console.getvalue())

    def test_preview_wsgi_exception_uses_safe_event_instead_of_raw_traceback(self):
        from serve_web import PreviewServer
        def failing_app(environ, start_response):
            raise RuntimeError("secret-cookie-request-path")
        with PreviewServer(("127.0.0.1", 0), lambda: True) as server:
            server.set_app(failing_app)
            with ThreadPoolExecutor(max_workers=1) as pool:
                handled = pool.submit(server.handle_request)
                http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    http.open(f"http://127.0.0.1:{server.server_port}/?key=secret", timeout=3)
                self.assertEqual(raised.exception.code, 500)
                raised.exception.close()
                handled.result(timeout=3)
        events = self.events()
        self.assertEqual(events[0]["event"], "server_request_failed")
        self.assertEqual(events[0]["exception_type"], "RuntimeError")
        self.assertNotIn("secret", self.console.getvalue() + self.path.read_text())

    def test_idle_client_timeout_is_debug_only_and_omits_client_address(self):
        from serve_web import PreviewServer
        with PreviewServer(("127.0.0.1", 0), lambda: True) as server:
            try:
                raise TimeoutError("private client details")
            except TimeoutError:
                server.handle_error(None, ("private address", 12))
            self.assertEqual(self.events(), [])
            os.environ["STEAM_PRICE_POLISHER_LOG_LEVEL"] = "DEBUG"
            event_log.configure_event_logging(self.directory.name)
            try:
                raise TimeoutError("private client details")
            except TimeoutError:
                server.handle_error(None, ("private address", 12))
        self.assertEqual(self.events()[0]["event"], "client_connection_closed")
        self.assertNotIn("private", self.path.read_text() + self.console.getvalue())


if __name__ == "__main__":
    unittest.main()
