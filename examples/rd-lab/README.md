# R&D Lab Local Engine

This example is the local, trusted-subprocess stage of the Solari R&D lab. It
runs a mission JSON against a baseline program and fixture-defined candidate
repairs, evaluates outputs against an independent literal oracle, and writes a
machine-readable report plus a runnable winner bundle when a non-baseline
candidate passes every case.

Run from this directory:

```powershell
python -m rd_lab run fixtures/csv-importer/mission.json --out .tmp/csv-run-1
```

The output directory must not already exist. The report is written to
`.tmp/csv-run-1/report.json`. A selected repair is copied to
`.tmp/csv-run-1/winner/program.py` with a small manifest. Candidate execution is
`local_trusted_subprocess`; it is not a sandbox and is only for trusted synthetic
programs. The supplied candidates are fixtures for demonstrating evaluation and
false success rejection, not autonomous model discovery.

Mission files use `rd-lab.mission/v1`:

- `baseline`: a relative path to the baseline program.
- `candidates`: repair candidates with unique `id` and relative `program`.
- `cases`: literal `{id, input, expected}` oracle cases.
- `timeout_seconds`: per-case execution deadline.

Every program reads JSON from stdin and writes one JSON value to stdout. The
runner passes only each case's `input` to the program.
