"""Real subprocess lifecycle checks; loopback only, no Steam requests or user cache."""
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from serve_web import PreviewServer, PreviewStopped, stop_signals
from steam_price_polisher.version import __version__

ROOT = Path(__file__).resolve().parents[1]


class ServerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log_path = Path(self.directory.name) / "server.log"
        self.log = self.log_path.open("w")
        self.addCleanup(self.log.close)
        self.env = {**os.environ, "STEAM_PRICE_POLISHER_DATA_DIR": self.directory.name}
        self.env.pop("WEB_ORIGIN", None)
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def launch(self, port=0, parent=False):
        command = [sys.executable, str(ROOT / "serve_web.py"), "--port", str(port)]
        if parent:
            command = [sys.executable, "-c",
                       "import subprocess,sys; p=subprocess.Popen(sys.argv[1:], "
                       "stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr); input()", *command]
        process = subprocess.Popen(command, cwd=ROOT, env=self.env, stdin=subprocess.PIPE,
                                   stdout=self.log, stderr=self.log,
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        self.addCleanup(self.stop_process, process)
        return process

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if process.stdin:
            process.stdin.close()

    def wait_until(self, condition):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.05)
        self.fail("Lifecycle check timed out: " + self.log_path.read_text())

    def ready(self):
        self.wait_until(lambda: re.search(r"http://127.0.0.1:(\d+) \(PID (\d+)\)", self.log_path.read_text()))
        matches = re.findall(r"http://127.0.0.1:(\d+) \(PID (\d+)\)", self.log_path.read_text())
        port, pid = map(int, matches[-1])
        with self.http.open(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response), {"status": "ok", "version": __version__})
        return port, pid

    def assert_port_clear(self, port):
        with PreviewServer(("127.0.0.1", port), lambda: True):
            pass

    def events_for(self, pid):
        path = Path(self.directory.name) / "logs" / f"events-{pid}.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_duplicate_rejected_signal_shutdown_and_immediate_restart(self):
        process = self.launch()
        port, _ = self.ready()
        duplicate = self.launch(port)
        self.assertEqual(duplicate.wait(timeout=5), 1)
        self.assertEqual(self.events_for(duplicate.pid)[-1]["event"], "server_start_failed")
        self.assertIn("existing listener", self.log_path.read_text())
        # A partially sent HTTP request must not block health or shutdown.
        with socket.create_connection(("127.0.0.1", port), timeout=2) as slow:
            slow.sendall(b"GET /api/health HTTP/1.1\r\n")
            self.ready()
            process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
            self.assertEqual(process.wait(timeout=5), 0)
        events = self.events_for(process.pid)
        self.assertEqual([row["event"] for row in events], ["server_started", "server_stopped"])
        self.assertIn(events[-1]["reason"], {"sigint", "sigbreak"})
        self.assert_port_clear(port)
        self.log_path.write_text("")
        replacement = self.launch(port)
        self.ready()
        replacement.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
        self.assertEqual(replacement.wait(timeout=5), 0)
        self.assert_port_clear(port)

    def test_parent_exit_closes_child_listener(self):
        parent = self.launch(parent=True)
        port, child_pid = self.ready()
        def cleanup_child():
            if "listener closed" not in self.log_path.read_text():
                try:
                    os.kill(child_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        self.addCleanup(cleanup_child)
        parent.terminate()
        parent.wait(timeout=5)
        self.wait_until(lambda: "listener closed" in self.log_path.read_text())
        self.assert_port_clear(port)
        # The listener closes before interpreter teardown releases inherited log handles.
        self.assertEqual(self.events_for(child_pid)[-1]["reason"], "parent_exited")
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x00100000, False, child_pid)
            if handle:
                try:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
                finally:
                    kernel.CloseHandle(handle)

    def test_sigint_handler_restores_previous_handler_and_stops_loop(self):
        previous = signal.getsignal(signal.SIGINT)
        with PreviewServer(("127.0.0.1", 0), lambda: True) as server:
            with stop_signals(server):
                signal.raise_signal(signal.SIGINT)
                with self.assertRaises(PreviewStopped):
                    server.service_actions()
            self.assertEqual(signal.getsignal(signal.SIGINT), previous)

    @unittest.skipUnless(os.name == "nt", "Windows socket sharing regression")
    def test_exclusive_socket_rejects_legacy_reuseaddr_listener(self):
        with PreviewServer(("127.0.0.1", 0), lambda: True) as server:
            with socket.socket() as legacy:
                legacy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                with self.assertRaises(OSError):
                    legacy.bind(server.server_address)
        with socket.socket() as legacy:
            legacy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            legacy.bind(("127.0.0.1", 0))
            legacy.listen()
            with self.assertRaises(OSError):
                PreviewServer(legacy.getsockname(), lambda: True)


if __name__ == "__main__":
    unittest.main()
