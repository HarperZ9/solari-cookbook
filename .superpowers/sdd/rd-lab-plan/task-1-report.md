# Task 1 Report: Local R&D Lab Engine

## Scope

Implemented the local trusted-subprocess engine under `examples/rd-lab` only.
The public API is:

```powershell
python -m rd_lab run PATH --out PATH
```

The callable Python API for later adapters/UI is `rd_lab.run_mission(mission_path,
out_path)`, which writes `report.json` and returns the same `rd-lab.run/v1`
report dictionary.

## RED Evidence

- Command: `python -m unittest tests.test_rd_lab_cli.RdLabCliTests.test_wrong_output_with_zero_exit_is_failed_without_selecting_candidate`
  - Result: failed with `No module named rd_lab`.
  - Expected reason: desired CLI/package did not exist yet.
- Command: `python -m unittest tests.test_rd_lab_cli`
  - Result: 6 failures, all from the missing `rd_lab` package.
  - Covered behaviors: wrong output with zero exit, timeout, invalid JSON,
    nonzero exit, empty cases, traversal/duplicate IDs, oracle visibility, and a
    second non-CSV mission.
- Command: `python -m unittest tests.test_execution_contract.ExecutionContractTests.test_large_input_to_nonreading_candidate_respects_case_timeout tests.test_execution_contract.ExecutionContractTests.test_output_preview_reads_only_the_configured_bound tests.test_execution_contract.ExecutionContractTests.test_preexisting_output_directory_is_rejected_before_running_candidates`
  - Result before fix: 3 failures.
  - Expected reasons: large stdin blocked before the deadline loop, output preview
    used an unbounded read, and pre-existing output directories were accepted.
- Command: `python -m unittest tests.test_execution_contract.ExecutionContractTests.test_bool_and_number_are_not_equal_in_oracle_comparison tests.test_execution_contract.ExecutionContractTests.test_candidate_stdout_rejects_nonstandard_nan tests.test_validation_contract.ValidationContractTests.test_rejects_nonstandard_nan_in_mission_oracle`
  - Result before fix: 3 failures.
  - Expected reasons: Python equality accepted `true` and `1`, candidate stdout
    `NaN` parsed as a number, and mission oracle `NaN` was accepted.

## GREEN Evidence

- Command: `python -m unittest tests.test_execution_contract tests.test_validation_contract`
  - Result: `Ran 12 tests in 9.101s`, `OK`.
- Command: `python -m unittest discover`
  - Result: `Ran 19 tests in 9.402s`, `OK`.
- Command: `python -m rd_lab run fixtures/csv-importer/mission.json --out .tmp/csv-run-final-strict`
  - Result: exit 0, report written.
  - Report outcome:
    - `baseline`: failed, statuses `passed,nonzero_exit,wrong_output,nonzero_exit`.
    - `false_success`: failed, statuses `passed,wrong_output,wrong_output,wrong_output`.
    - `repair`: passed, statuses `passed,passed,passed,passed`.
    - `selected_candidate.id`: `repair`.
- Winner probe:
  - Command input: `{"csv":"name;amount\nNia;3,50\n"}` piped to `.tmp/csv-run-final-strict/winner/program.py`.
  - Output: `[{"name": "Nia", "amount": "3.50"}]`.
- Source preservation:
  - Re-ran the CSV mission and compared SHA256 before/after for all fixture
    source programs.
  - `baseline.py`, `false_success.py`, and `repair.py` all reported `same=True`.
- Size gate:
  - All owned Python files are below 300 lines.
  - AST function-length check reported `function length violations: []`.

## Implemented Behavior

- Validates `rd-lab.mission/v1` mission JSON.
- Rejects traversal paths, symlinked program paths, duplicate candidate IDs,
  duplicate case IDs, missing cases, and invalid program references.
- Executes only `sys.executable` plus a copied single program file in a fresh temp
  working directory per case.
- Passes only the case `input` JSON to candidates.
- Uses a minimal subprocess environment and does not pass API keys or ambient
  cloud credentials.
- Feeds candidate stdin through a temporary file handle so a non-reading
  candidate cannot block the parent before the deadline loop.
- Rejects pre-existing output directories before execution; the engine no longer
  deletes stale winner directories.
- Reads output previews with `read(MAX_OUTPUT_BYTES)` rather than loading the
  full file before slicing.
- Distinguishes `timeout`, `output_too_large`, `invalid_json`, `nonzero_exit`,
  `wrong_output`, and `passed`.
- Compares actual JSON output against independent literal expected JSON using a
  canonical representation, so booleans and numbers are not conflated.
- Rejects nonstandard JSON constants such as `NaN` and `Infinity` in both mission
  JSON and candidate stdout.
- Includes source SHA256 for every experiment and a unified baseline-to-winner
  diff for the selected repair.
- Never selects the baseline as a repair.

## Files

- Engine/package: `examples/rd-lab/rd_lab/`
- Tests: `examples/rd-lab/tests/test_execution_contract.py`,
  `examples/rd-lab/tests/test_validation_contract.py`
- Mission fixture: `examples/rd-lab/fixtures/csv-importer/`
- Usage README: `examples/rd-lab/README.md`

## Boundaries and Concerns

- Execution mode is `local_trusted_subprocess`; this is not a security sandbox.
- No Solari cloud calls, public uploads, model calls, or paid APIs were used.
- Candidates are supplied fixtures. The report and README avoid claiming
  autonomous discovery from these candidates.
- Root owns `rd_lab/run_room.py` and `tests/test_run_room.py` in a separate
  path-limited commit. This report covers only the local engine, fixture mission,
  CLI, and execution/validation tests.
