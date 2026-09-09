"""Run the local web interface. For public deployment, use the WSGI factory."""
from wsgiref.simple_server import make_server, WSGIRequestHandler
from steam_price_polisher.web_app import create_app


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    app = create_app()
    print("Steam Prices Polisher: http://127.0.0.1:8765", flush=True)
    with make_server("127.0.0.1", 8765, app, handler_class=QuietHandler) as server:
        server.serve_forever()
