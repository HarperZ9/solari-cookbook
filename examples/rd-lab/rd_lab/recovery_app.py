import argparse
import html
import json
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .recovery_store import PayloadConflict, RecoveryStore


KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{3,80}$")
MAX_FORM_BYTES = 4096


class RecoveryServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, db_path):
        self.store = RecoveryStore(db_path)
        super().__init__(address, handler)


def create_app(db_path, host="127.0.0.1", port=8765):
    return RecoveryServer((host, port), RecoveryHandler, db_path)


class RecoveryHandler(BaseHTTPRequestHandler):
    server_version = "RecoveryApp/1.0"

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            return self._send_html(200, self._index_html())
        if path in {"/batches", "/state"}:
            state = self.server.store.state()
            if self._wants_html():
                return self._send_html(200, self._state_html(state))
            return self._send_json(200, state)
        return self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path != "/batches":
            return self._send_json(404, {"error": "not_found"})
        if not self._write_origin_allowed():
            return self._send_json(403, {"error": "forbidden_origin"})

        form, error = self._read_form()
        if error:
            return self._send_json(400, {"error": "invalid_request", "details": [error]})
        values, errors = _validate_form(form)
        if errors:
            return self._send_json(400, {"error": "invalid_request", "details": errors})

        try:
            batch, created = self.server.store.record_batch(
                values["operation_key"], values["label"], values["rows"]
            )
        except PayloadConflict:
            return self._send_json(409, {"error": "operation_key_payload_mismatch"})

        if created and values["fail_after_commit_once"]:
            return self._close_without_response()

        body = {"status": "created" if created else "replayed", "batch": batch.as_dict()}
        if self._wants_html():
            return self._send_html(201 if created else 200, self._receipt_html(body))
        return self._send_json(201 if created else 200, body)

    def log_message(self, format, *args):
        return

    def _read_form(self):
        length_text = self.headers.get("Content-Length", "0")
        try:
            length = int(length_text)
        except ValueError:
            return None, "content length must be an integer"
        if length <= 0 or length > MAX_FORM_BYTES:
            return None, "form body must be between 1 and 4096 bytes"
        content_type = self.headers.get("Content-Type", "")
        if "application/x-www-form-urlencoded" not in content_type:
            return None, "content type must be application/x-www-form-urlencoded"
        raw = self.rfile.read(length).decode("utf-8", errors="strict")
        return parse_qs(raw, keep_blank_values=True), None

    def _write_origin_allowed(self):
        host = self.headers.get("Host", "")
        if not _loopback_host(host):
            return False
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            return parsed.scheme == "http" and _same_origin(parsed.netloc, host)
        fetch_site = self.headers.get("Sec-Fetch-Site")
        return fetch_site in {None, "none", "same-origin"}

    def _wants_html(self):
        accept = self.headers.get("Accept", "")
        return "text/html" in accept

    def _send_json(self, status, payload):
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._send_common_headers()
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, status, markup):
        data = markup.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._send_common_headers()
        self.end_headers()
        self.wfile.write(data)

    def _send_common_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")

    def _close_without_response(self):
        self.close_connection = True
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()

    def _index_html(self):
        state = self.server.store.state()
        return _page(
            "Recovery workflow",
            """
            <section aria-labelledby="submit-heading">
              <h2 id="submit-heading">Synthetic batch</h2>
              <form method="post" action="/batches">
                <label>Operation key
                  <input name="operation_key" required pattern="[A-Za-z0-9._:-]{3,80}" autocomplete="off">
                </label>
                <label>Batch label
                  <input name="label" required maxlength="80" autocomplete="off">
                </label>
                <label>Rows
                  <input name="rows" required type="number" min="1" max="1000" value="3">
                </label>
                <label class="inline">
                  <input name="fail_after_commit_once" type="checkbox" value="1">
                  Close connection after the first commit
                </label>
                <button type="submit">Create batch</button>
              </form>
              <p><a href="/state">View stored records and receipts</a></p>
            </section>
            """
            + _table_html(state),
        )

    def _state_html(self, state):
        return _page("Stored recovery state", _table_html(state) + '<p><a href="/">Back to form</a></p>')

    def _receipt_html(self, receipt):
        return _page(
            "Batch receipt",
            f"""
            <section aria-labelledby="receipt-heading">
              <h2 id="receipt-heading">{html.escape(receipt["status"].title())}</h2>
              <pre>{html.escape(json.dumps(receipt, indent=2))}</pre>
              <p><a href="/state">View stored records and receipts</a></p>
            </section>
            """,
        )


def _validate_form(form):
    errors = []
    operation_key = _one(form, "operation_key").strip()
    label = _one(form, "label").strip()
    rows_text = _one(form, "rows").strip()
    if not KEY_RE.fullmatch(operation_key):
        errors.append("operation key must be 3-80 URL-safe characters")
    if not label or len(label) > 80:
        errors.append("label must be 1-80 characters")
    try:
        rows = int(rows_text)
    except ValueError:
        rows = 0
    if rows < 1 or rows > 1000:
        errors.append("rows must be an integer from 1 to 1000")
    return {
        "operation_key": operation_key,
        "label": label,
        "rows": rows,
        "fail_after_commit_once": _one(form, "fail_after_commit_once") == "1",
    }, errors


def _one(form, name):
    values = form.get(name, [""])
    return values[0] if values else ""


def _loopback_host(host):
    name = _host_name(host)
    return name == "localhost" or name.startswith("127.") or name == "::1"


def _same_origin(origin_netloc, host):
    return origin_netloc.lower() == host.lower() and _loopback_host(host)


def _host_name(netloc):
    if netloc.startswith("["):
        return netloc.split("]", 1)[0].strip("[]").lower()
    return netloc.rsplit(":", 1)[0].lower()


def _table_html(state):
    rows = []
    for batch in state["batches"]:
        rows.append(
            "<tr>"
            f"<td>{batch['id']}</td>"
            f"<td>{html.escape(batch['operation_key'])}</td>"
            f"<td>{html.escape(batch['label'])}</td>"
            f"<td>{batch['rows']}</td>"
            f"<td><code>{html.escape(batch['payload_digest'][:16])}</code></td>"
            "</tr>"
        )
    body = "".join(rows) or '<tr><td colspan="5">No records stored.</td></tr>'
    return f"""
    <section aria-labelledby="state-heading">
      <h2 id="state-heading">Stored records</h2>
      <table>
        <thead><tr><th>ID</th><th>Operation key</th><th>Label</th><th>Rows</th><th>Payload digest</th></tr></thead>
        <tbody>{body}</tbody>
      </table>
      <p class="note">SQLite path: <code>{html.escape(state["db_path"])}</code></p>
    </section>
    """


def _page(title, body):
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0; background: Canvas; color: CanvasText; }}
    main {{ max-width: 780px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 1.7rem; margin: 0 0 20px; }}
    h2 {{ font-size: 1.1rem; margin: 20px 0 12px; }}
    form {{ display: grid; gap: 12px; max-width: 420px; }}
    label {{ display: grid; gap: 4px; font-weight: 600; }}
    input {{ font: inherit; padding: 8px; border: 1px solid ButtonBorder; background: Field; color: FieldText; }}
    button {{ width: fit-content; padding: 9px 14px; font: inherit; font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
    th, td {{ border-top: 1px solid ButtonBorder; padding: 8px; text-align: left; vertical-align: top; }}
    code, pre {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
    .inline {{ display: flex; align-items: center; gap: 8px; font-weight: 500; }}
    .note {{ font-size: .9rem; }}
    :focus-visible {{ outline: 3px solid Highlight; outline-offset: 2px; }}
  </style>
</head>
<body><main><h1>{html.escape(title)}</h1>{body}</main></body>
</html>"""


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m rd_lab.recovery_app")
    parser.add_argument("--db", required=True, help="caller-owned SQLite runtime path")
    parser.add_argument("--host", default="127.0.0.1", help="bind host, defaults to 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="bind port")
    args = parser.parse_args(argv)
    server = create_app(args.db, host=args.host, port=args.port)
    print(f"serving recovery workflow at http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
