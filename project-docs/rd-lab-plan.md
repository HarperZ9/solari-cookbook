# Solari R&D Lab Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development task by task.

**Goal:** Deliver an inspectable investigation-to-repair application for the build-first hiring challenge.
**Architecture:** Mission bundles, isolated experiment execution, independent result evaluation, optional Solari execution, existing harness integration, and an accessible run room share a versioned result contract.
**Tech Stack:** Python 3.11+, standard library core; documented Solari SDKs for cloud execution.
**Spec:** project-docs/specs/SPEC-rd-lab.md

## Global Constraints
No paid API calls without a budget. No secret values, private sessions, protected projects, customer data, CAPTCHA solving or external writes in experiments. Do not modify Canon, Flywheel, Forum, Index or Crucible repositories. Cloud previews contain synthetic data only. Do not claim novelty, exactly-once behavior, adoption or general autonomous repair from fixture results.

## Task 1: Working local experiment engine and owned data-repair mission

Own examples/rd-lab only. Preserve existing cookbook examples. Create a Python standard-library package rd_lab, tests and fixtures under that directory. Separate modules by mission validation, execution, evaluation and CLI. Keep modules below 300 lines and functions below 50. No frontend in this task.

Interface: `python -m rd_lab run PATH --out PATH` consumes a mission JSON and emits report.json and a runnable winner bundle if one passes all oracle cases. Local execution is trusted-code-only and labeled `execution_mode: local_trusted_subprocess`. Mission JSON schema `rd-lab.mission/v1` identifies name, relative baseline program, list of candidate {id, program}, list of cases {id, input, expected}, and timeout_seconds. Every program consumes JSON stdin and produces JSON stdout. Runner passes only input to the candidate, never expected. Keep oracle expected values outside each copied program directory. Source paths must resolve within mission root; reject traversal, symlinks and duplicate IDs. Copy only the named program into each fresh work directory. Do not execute arbitrary command strings. Invoke sys.executable, program path with argv, bounded timeout and bounded output handling. Mark timeout, invalid JSON, nonzero exit, wrong output distinctly. A candidate passes only if every case matches the independent literal expected JSON. Missing cases cannot pass. Preserve original source; include SHA256 and unified diff for chosen repair. Evidence includes actual duration, command exit, case outcomes and limitations. No model or cloud claims.

The result schema `rd-lab.run/v1` has mission, execution_mode, started_at, finished_at, experiments (candidate_id, source_sha256, cases, passed), selected_candidate or null, and limitations. Baseline participates in the comparison but cannot be chosen as a repair. Each case contains id, status, expected, actual, exit_code, duration_ms. The engine must work for a second arbitrary mission, not contain CSV-specific branching.

Create an owned CSV importer mission with broken baseline and at least two contrasting candidate programs, including false success. Inputs are JSON objects with csv text; outputs are arrays of normalized rows. Hand-derived cases include comma and semicolon delimiters, decimal comma numeric strings and empty/malformed input; define one explicit error output contract. Include a README that labels supplied repair candidates as fixture-defined, not autonomous model discovery.

- [ ] Write behavioral tests first and observe expected failures. Cover wrong output with exit zero, timeout, missing cases, invalid bundle paths, input-only candidate visibility, and a second simple mission.
- [ ] Implement validation and runner, then rerun the focused tests.
- [ ] Run the full owned mission through CLI, inspect actual report and winner program. Source originals remain byte-identical.
- [ ] Self-review public boundary and commit only examples/rd-lab changes. Report RED/GREEN commands, actual outcomes and limitations to .superpowers/sdd/rd-lab-plan/task-1-report.md.

## Task 2: Existing-tool and Solari execution adapters

After interface audit, connect supported public-safe Index/harness calls and verified Solari SDKs. Implement bounded lifecycle and allowlisted synthetic upload. Add candidate generation from an existing model route, keeping untrusted execution cloud-only. Read actual interfaces before finalizing this task's callable contracts. Do not mark complete based on mock API tests; a budget-authorized cloud run is required.

## Task 3: Browser demonstration and run room

Render the shared result contract as a responsive accessible experiment workspace, then add live progress and browser observations. Show source differences, actual experiment results, artifacts and uncertainty. Exercise a real owned browser service and lost-confirmation failure. Independent review and runtime checks precede publication.

## Progress
Task 1 implemented in 71a8239 and under independent review. Initial offline run room and Index adapter passed scoped independent review. CLI/view integration and bounded adapter/recovery components are being checkpointed.

September 4 user direction: preserve this as a Flywheel product idea for native integration and licensing. Stop expansion after the current component checkpoints. Do not push the original prototype, publish a challenge submission, or select a product license implicitly through the surrounding cookbook. Full Task 2/3 goals remain future work, not completed claims.
