import json
import threading
import unittest
from http.client import HTTPConnection

from api.main import Handler, HTTPServer, PORT


class MainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join(timeout=2)

    def _get(self, path: str) -> tuple[int, str]:
        conn = HTTPConnection("localhost", self.port, timeout=2)
        conn.request("GET", path)
        response = conn.getresponse()
        body = response.read().decode()
        conn.close()
        return response.status, body

    def test_healthz(self) -> None:
        status, body = self._get("/healthz")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("region", payload)
        self.assertIn("timestamp", payload)

    def test_readyz(self) -> None:
        status, body = self._get("/readyz")
        self.assertEqual(status, 200)
        self.assertEqual(body, "ready")

    def test_metrics(self) -> None:
        status, body = self._get("/metrics")
        self.assertEqual(status, 200)
        self.assertIn("up 1", body)

    def test_default_port(self) -> None:
        self.assertEqual(PORT, 8080)


if __name__ == "__main__":
    unittest.main()
