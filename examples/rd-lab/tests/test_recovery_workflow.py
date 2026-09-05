import http.client
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

from rd_lab.recovery_app import create_app


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RunningRecoveryApp:
    def __init__(self, db_path):
        self.db_path = db_path
        self.port = free_port()
        self.server = create_app(db_path, host="127.0.0.1", port=self.port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.port}"

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            payload = None if body is None else urlencode(body)
            request_headers = {"Host": f"127.0.0.1:{self.port}"}
            if payload is not None:
                request_headers["Content-Type"] = "application/x-www-form-urlencoded"
            if headers:
                request_headers.update(headers)
            conn.request(method, path, body=payload, headers=request_headers)
            response = conn.getresponse()
            data = response.read()
            return response.status, dict(response.getheaders()), data
        finally:
            conn.close()

    def post_batch(self, key, label, rows, *, fail_once=False, origin=None):
        body = {"operation_key": key, "label": label, "rows": str(rows)}
        if fail_once:
            body["fail_after_commit_once"] = "1"
        headers = {"Origin": self.origin if origin is None else origin}
        return self.request("POST", "/batches", body, headers)


class RecoveryWorkflowTests(unittest.TestCase):
    def test_lost_confirmation_retry_returns_same_durable_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "recovery.sqlite3"
            with RunningRecoveryApp(db_path) as app:
                with self.assertRaises(http.client.RemoteDisconnected):
                    app.post_batch("stable-1", "nightly", 3, fail_once=True)

                status, headers, data = app.post_batch("stable-1", "nightly", 3)

                self.assertEqual(status, 200)
                receipt = json.loads(data)
                self.assertEqual(receipt["status"], "replayed")
                self.assertEqual(receipt["batch"]["operation_key"], "stable-1")
                self.assertEqual(receipt["batch"]["label"], "nightly")
                self.assertEqual(receipt["batch"]["rows"], 3)
                self.assertEqual(headers["Content-Type"], "application/json")

                status, _, data = app.request("GET", "/state")
                self.assertEqual(status, 200)
                state = json.loads(data)
                self.assertEqual(len(state["batches"]), 1)
                self.assertEqual(state["batches"][0]["operation_key"], "stable-1")

    def test_same_operation_key_with_changed_payload_is_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "recovery.sqlite3"
            with RunningRecoveryApp(db_path) as app:
                first_status, _, _ = app.post_batch("stable-2", "daily", 2)
                second_status, _, data = app.post_batch("stable-2", "daily", 4)

                self.assertEqual(first_status, 201)
                self.assertEqual(second_status, 409)
                error = json.loads(data)
                self.assertEqual(error["error"], "operation_key_payload_mismatch")

    def test_new_operation_key_with_duplicate_payload_creates_naive_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "recovery.sqlite3"
            with RunningRecoveryApp(db_path) as app:
                self.assertEqual(app.post_batch("new-1", "duplicate", 2)[0], 201)
                self.assertEqual(app.post_batch("new-2", "duplicate", 2)[0], 201)

                status, _, data = app.request("GET", "/batches")

                self.assertEqual(status, 200)
                state = json.loads(data)
                self.assertEqual([b["operation_key"] for b in state["batches"]], ["new-1", "new-2"])
                self.assertEqual([b["rows"] for b in state["batches"]], [2, 2])

    def test_records_survive_server_restart_with_same_db_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "recovery.sqlite3"
            with RunningRecoveryApp(db_path) as app:
                self.assertEqual(app.post_batch("persist-1", "kept", 5)[0], 201)

            with RunningRecoveryApp(db_path) as app:
                status, _, data = app.request("GET", "/state")

                self.assertEqual(status, 200)
                state = json.loads(data)
                self.assertEqual(len(state["batches"]), 1)
                self.assertEqual(state["batches"][0]["operation_key"], "persist-1")

    def test_malformed_input_is_rejected_without_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "recovery.sqlite3"
            with RunningRecoveryApp(db_path) as app:
                status, _, data = app.post_batch("bad rows", "", 0)

                self.assertEqual(status, 400)
                self.assertEqual(json.loads(data)["error"], "invalid_request")
                state = json.loads(app.request("GET", "/state")[2])
                self.assertEqual(state["batches"], [])

    def test_cross_origin_write_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "recovery.sqlite3"
            with RunningRecoveryApp(db_path) as app:
                status, _, data = app.post_batch("origin-1", "blocked", 1, origin="http://example.test")

                self.assertEqual(status, 403)
                self.assertEqual(json.loads(data)["error"], "forbidden_origin")
                state = json.loads(app.request("GET", "/state")[2])
                self.assertEqual(state["batches"], [])


if __name__ == "__main__":
    unittest.main()
