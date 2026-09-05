import hashlib
import json
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Batch:
    id: int
    operation_key: str
    payload_digest: str
    label: str
    rows: int
    created_at: str

    def as_dict(self):
        return {
            "id": self.id,
            "operation_key": self.operation_key,
            "payload_digest": self.payload_digest,
            "label": self.label,
            "rows": self.rows,
            "created_at": self.created_at,
        }


class PayloadConflict(ValueError):
    pass


def digest_payload(label, rows):
    payload = {"label": label, "rows": rows}
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


class RecoveryStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def record_batch(self, operation_key, label, rows):
        digest = digest_payload(label, rows)
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        created = False
        with closing(self._connect()) as conn:
            with conn:
                try:
                    conn.execute(
                        """
                        INSERT INTO batches(operation_key, payload_digest, label, rows, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (operation_key, digest, label, rows, created_at),
                    )
                    created = True
                except sqlite3.IntegrityError:
                    created = False
                row = conn.execute(
                    "SELECT * FROM batches WHERE operation_key = ?",
                    (operation_key,),
                ).fetchone()
        batch = _batch_from_row(row)
        if batch.payload_digest != digest:
            raise PayloadConflict("operation key already belongs to a different payload")
        return batch, created

    def list_batches(self):
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM batches ORDER BY id").fetchall()
        return [_batch_from_row(row) for row in rows]

    def state(self):
        batches = [batch.as_dict() for batch in self.list_batches()]
        return {
            "schema": "rd-lab.recovery-state/v1",
            "db_path": str(self.db_path),
            "batches": batches,
            "limitations": [
                "Synthetic local workflow only; no external destinations are called.",
                "Stable keys make same-payload retry recoverable, not exactly-once overall.",
            ],
        }

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS batches (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        operation_key TEXT NOT NULL UNIQUE,
                        payload_digest TEXT NOT NULL,
                        label TEXT NOT NULL,
                        rows INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )


def _batch_from_row(row):
    return Batch(
        id=row["id"],
        operation_key=row["operation_key"],
        payload_digest=row["payload_digest"],
        label=row["label"],
        rows=row["rows"],
        created_at=row["created_at"],
    )
