# Recovery Workflow Fixture

This fixture is a synthetic browser workflow for the Solari R&D lab. It stores a
small local batch record in SQLite and demonstrates a lost confirmation: the
server can commit the record, close the connection before sending a response,
and let the caller recover by retrying the same operation key with the same
payload.

Run from `examples/rd-lab`:

```powershell
python -m rd_lab.recovery_app --db .tmp/recovery-workflow.sqlite3 --port 8765
```

Open `http://127.0.0.1:8765/`. Use a stable operation key, a harmless label and
a row count. Enabling the failure checkbox closes the first request after the
commit; `/state` shows the durable record. Retrying the same key and payload
returns the stored receipt. Retrying the same key with a changed payload returns
HTTP 409. Using a new key with the same payload creates another record, which
demonstrates duplicate risk rather than exactly-once behavior.

The app has no outbound network path, accepts only synthetic form data, and uses
the caller-provided SQLite path as runtime state. It is not a production service
and the deliberate connection close is a controlled demo flag.
