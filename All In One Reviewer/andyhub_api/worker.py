"""Dedicated single generation worker with an internal health endpoint."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import signal
import threading
import time

from generator import default_generation_dependencies

from .persistence import ApiRepository
from .services import GenerationService
from .settings import Settings
from .structured_logging import configure_logging, log_event


LOGGER = logging.getLogger("andyhub.worker")


def main() -> int:
    configure_logging()
    settings = Settings.defaults()
    repository = ApiRepository(settings.database_path)
    service = GenerationService(settings, repository, default_generation_dependencies)
    stop = threading.Event()

    def request_stop(*_: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    service.start()
    server = ThreadingHTTPServer(
        ("0.0.0.0", int(os.environ.get("ANDYHUB_WORKER_HEALTH_PORT", "8001"))),
        _health_handler(service, repository),
    )
    health_thread = threading.Thread(target=server.serve_forever, daemon=True)
    health_thread.start()
    log_event(LOGGER, "worker_started", service="worker", health_port=server.server_port)
    try:
        while not stop.wait(0.5):
            pass
    finally:
        server.shutdown()
        service.stop()
        server.server_close()
        log_event(LOGGER, "worker_stopped", service="worker")
    return 0


def _health_handler(service: GenerationService, repository: ApiRepository):
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/health":
                self.send_error(404)
                return
            worker_alive = service.is_running
            database_ok = repository.ping()
            status = "ok" if worker_alive and database_ok else "degraded"
            body = json.dumps(
                {
                    "status": status,
                    "service": "worker",
                    "worker": "ok" if worker_alive else "unavailable",
                    "database": "ok" if database_ok else "unavailable",
                },
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(200 if status == "ok" else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            log_event(LOGGER, "worker_health_request", service="worker", client=self.client_address[0])

    return HealthHandler


if __name__ == "__main__":
    raise SystemExit(main())
