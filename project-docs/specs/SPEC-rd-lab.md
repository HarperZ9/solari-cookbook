# Solari R&D Lab

## Objective
Build a Flywheel application that takes a broken owned workflow from investigation through isolated experiments to an inspectable candidate repair. Solari provides remote execution and browser observation. The hiring showcase must demonstrate useful work and expose false success.

## Requirements
- [ ] Accept a mission directory containing owned source, an independent oracle, and candidate repairs. Preserve originals.
- [ ] Execute baseline and competing candidates in separate working directories, capture real output, enforce a deadline, and evaluate expected behavior independently of exit code.
- [ ] Support a real Solari sandbox and browser path using documented SDK interfaces. Default local runs must be labeled local, never cloud evidence.
- [ ] Investigate source with Index and integrate verified Flywheel or Forum execution/evidence interfaces without changing their repositories.
- [ ] Show a live run room with experiment progress, source changes, failure evidence and the resulting application. Readable keyboard-accessible and responsive output must remain available without JavaScript.
- [ ] Demonstrate recovery from a lost confirmation and rejection of a false-success candidate. Unknown evidence remains unresolved.
- [ ] Produce a runnable chosen candidate, source diff, machine-readable results and concise human explanation. Selection is a tested candidate, not proof of general correctness.
- [ ] Add model-assisted hypothesis/repair generation through an existing verified harness interface; record where the model contributed. Fixture-defined candidate runs alone do not satisfy this requirement.
- [ ] Complete independent review, real browser checks, public-boundary inspection and a budget-authorized Solari run before publishing or presenting this as the finished challenge submission.

## Approach
Build inside the Solari cookbook clone on codex/rd-lab, under examples/rd-lab. Python standard-library execution core accepts task-specific program and oracle files; optional Solari adapters remain separate. A source-bundle allowlist excludes credentials and private data from every remote upload. Candidate execution in local subprocesses is only appropriate for trusted code; it is not a security sandbox. Actual untrusted model-generated programs require Solari isolation.

The first experiment repairs a synthetic CSV-to-JSON data importer. Its held-out checks exercise locale-specific delimiters/decimal units, dropped records, and a false-success program. A subsequent browser workflow demonstrates repeated-action risk and a candidate repair against an owned service. The general runner must accept new missions without edits to its engine. This is one application with progressively connected stages, not a replacement flagship.

## Boundaries
No paid API calls without a budget. No secret values, private sessions, protected projects, customer data, CAPTCHA solving or external writes in experiments. Do not modify Canon, Flywheel, Forum, Index or Crucible repositories. Cloud previews contain synthetic data only. Do not claim novelty, exactly-once behavior, adoption or general autonomous repair from fixture results.

## Status
Build authorized by the user; expanded R&D direction requested. Implementation in progress. Remote run and publication not performed.
