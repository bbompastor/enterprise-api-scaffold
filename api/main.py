import json
import logging
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "local")
PORT = int(os.environ.get("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._respond_json(
                200,
                {
                    "status": "ok",
                    "region": REGION,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        elif self.path == "/readyz":
            self._respond_text(200, "ready")
        elif self.path == "/metrics":
            self._respond_text(200, "# HELP up Service is up\nup 1\n", "text/plain")
        else:
            self._respond_text(404, "not found")

    def _respond_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _respond_text(self, status: int, body: str, content_type: str = "text/plain") -> None:
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)


def run() -> None:
    server = HTTPServer(("", PORT), Handler)
    logger.info("listening on :%s (region=%s)", PORT, REGION)
    server.serve_forever()


if __name__ == "__main__":
    run()
