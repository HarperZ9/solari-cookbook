# Solari adapter findings

Observed September 4, 2026. Installed only in the isolated clone's ignored virtual environment: solari-browser 0.1.2, solari-sandbox 0.2.0, solari-core 0.2.0. `pip check` reports no broken requirements. No API session was created; the current process has no SOLARI_API_KEY.

## Verified interface and integration consequences

- `SandboxClient(api_key=..., base_url="https://api.getsolari.com", call_timeout_ms=...)`; `create(template="base", cpu=1, mem_mb=2048, timeout_ms=..., lifecycle={"onTimeout":"kill"})` supports explicit idle cleanup. Idle is not a wall-clock budget.
- `Sandbox.commands.start(cmd, args=[...], cwd=..., env=...)` returns a handle with `on_data(callback)`, `stdin(data)`, `wait()` and `kill(signal=None)`. Use this for bounded streaming; `commands.run` accumulates output without a cap.
- In installed solari-core 0.2.0, `commands.run` accepts `timeout_ms` but does not reference it in the method body. The adapter needs its own deadline and explicit process/session cleanup. Do not rely on the parameter alone. This is a source observation, not a cloud reproduction.
- `CommandResult` uses `exitCode`, while the current docs' Python example uses `exit_code`. Use the installed source contract, pinned dependencies and a characterization check before a cloud run.
- `files.write(path, bytes_or_text)` and `files.read_text(path)` require the connected control channel. Upload only allowlisted synthetic program files and case inputs; expected results remain with the independent evaluator.
- `preview_url(port)` returns a mapping. Official docs describe a signed `pt_token` in the URL; treat it as transient access material. Never place it in a public report. Clean screenshots and sanitized origin/path references may be published after inspection.
- Browser `Solari.launch(recording=True, stealth=False, captcha=False, proxy=None, retries=0)` is supported. The owned test app does not need evasion features. Release with `browser.close()` and close the client driver. Replay is asynchronous DOM NDJSON, not a video or server-side completion proof.

## Cloud execution prerequisites

Validate the adapter against the pinned package; confirm account and credit budget before creating resources. Official pricing currently advertises a free plan with monthly credits, but the user's enrollment and balance are unknown. No purchase, subscription, credit redemption or provider session has been performed.

Sources: [sandbox docs](https://docs.getsolari.com/sandboxes), [Python SDK docs](https://docs.getsolari.com/languages), [recording](https://docs.getsolari.com/recording), [pricing](https://docs.getsolari.com/pricing), installed `solari_core/handle.py` methods `_Commands.start` and `_Commands.run`, `solari_core/types.py:CommandResult`, `solari_sandbox/sandbox_client.py:SandboxClient.create`, `solari_browser/client.py:Solari.launch`.

## Existing tool seams

Read-only component audit identified Index `index_graph.symbols.build_symbol_navigator`, `find_definitions` and `find_references` for owned-source inspection; Flywheel `harness.proposer.Proposer` and `ProposerOutput` for text-only model proposals; Crucible `verdict_for` for typed measurement verdicts. Those tools use FSL-1.1-MIT, whereas the upstream cookbook is MIT. Keep dependencies external and preserve their licenses; do not copy their code under the cookbook's MIT notice. Static symbol results and typed verdicts have limited scope and do not prove a repair correct.

The installed distribution metadata is index-graph 2.9.0, flywheel-verify 0.3.5, crucible-bench 1.2.0, while the Index CLI's fresh map identified tool_version 2.10.0. Resolve import paths and pins before claiming a reproducible integration. Flywheel's `ServeProposer` is text-only but its default loopback endpoint 127.0.0.1:8765 refused a read-only health connection. No local model inference was run. Avoid the default CLI proposer for a strict no-generated-host-execution boundary; use a text-only proposer explicitly.

## Account reconciliation

Personal Google onboarding completed by 2026-09-05T01:30:22Z. The console shows Free plan, zero credit, zero API keys and no compute. The public hiring thread offers a builder promo code in Harry Chow's reply https://x.com/harrychow_/status/2094518228076679300. Redemption terms and possible subscription effects have not been confirmed; no code redeemed. Account receipt is in the private outreach controls, not this public-safe adapter note.
