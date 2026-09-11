"""Run the local web interface. For public deployment, use the WSGI factory."""
import argparse
import os
import signal
import socket
import sys
from contextlib import contextmanager
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler

from steam_price_polisher.web_app import create_app


class QuietHandler(WSGIRequestHandler):
    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, format, *args):
        pass


class PreviewStopped(Exception):
    """Leave the serving loop without invoking shutdown() on its own thread."""


class PreviewServer(ThreadingMixIn, WSGIServer):
    # Windows SO_REUSEADDR permits a second listener to steal requests.
    allow_reuse_address = os.name != "nt"
    allow_reuse_port = False
    daemon_threads = True

    def __init__(self, address, parent_alive):
        self.parent_alive = parent_alive
        self.stop_requested = False
        super().__init__(address, QuietHandler)

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def service_actions(self):
        if self.stop_requested or not self.parent_alive():
            raise PreviewStopped()


@contextmanager
def watch_parent():
    """A terminal's shell may exit without forwarding Ctrl+C to Python."""
    parent_pid = os.getppid()
    if os.name != "nt":
        yield lambda: os.getppid() == parent_pid
        return

    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # Hold the original process handle so PID reuse cannot hide a dead parent.
    handle = kernel.OpenProcess(0x00100000, False, parent_pid)  # SYNCHRONIZE only
    if not handle:
        raise OSError("Cannot monitor the launching process; start from a persistent terminal.")
    try:
        yield lambda: kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT: still alive
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def stop_signals(server):
    def request_stop(signum, frame):
        server.stop_requested = True

    previous = {}
    try:
        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            signum = getattr(signal, name, None)
            if signum is not None:
                previous[signum] = signal.signal(signum, request_stop)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="Loopback port (default: 8765)")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    try:
        with watch_parent() as parent_alive:
            # Acquire the port before creating a worker or announcing success.
            with PreviewServer(("127.0.0.1", args.port), parent_alive) as server:
                origin = f"http://127.0.0.1:{server.server_port}"
                server.set_app(create_app(origin=origin))
                with stop_signals(server):
                    print(f"Steam Prices Polisher: {origin} (PID {os.getpid()})", flush=True)
                    try:
                        server.serve_forever(poll_interval=0.2)
                    except (PreviewStopped, KeyboardInterrupt):
                        pass
        print("Steam Prices Polisher stopped; listener closed.", flush=True)
        return 0
    except OSError as exc:
        print(f"Could not start the preview on port {args.port}: {exc}. "
              "Check for an existing listener and local socket permissions.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
