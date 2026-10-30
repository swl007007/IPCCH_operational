# CP3 integrated preflight: complete FEWS NET delivery + all nested refs before any IPCCH mutation (Supervisor 6ebfb63)

- v2 `_fewsnet` now validates the WHOLE `fewsnet.delivery` block (exact keys models/assets/diagnostics/contracts) with
  the existing v1 rules restricted to FEWS NET: `delivery_manifest._models/_assets/_diagnostics(..., systems=("fewsnet",))`
  and `_contracts`. The v1 helpers gained a `systems` parameter defaulting to `SYSTEMS` (diff: 7 lines, behaviour for
  v1 callers unchanged). GitNexus impact for `_models/_assets/_diagnostics` = HIGH (legacy `delivery_job.main`,
  `pipeline.main`, `submit_intent`); mitigated by the full-suite regression below.
- v2 `iter_object_refs` yields every nested FEWS delivery reference (3 models x package_manifest + acceptance_report,
  5 assets, available/frozen diagnostic evidence and frozen source parts).
- `delivery_request_v2.admit(...)`: structural validation of the whole request + `verify_reference_identities` over
  EVERY reference (IPCCH, FEWS NET incl. nested delivery, runtime) -> `validation_level = "admitted"`; the v2 runner must
  call it before any lock/collection/store mutation/inference (runner + zero-write store/provider spy test come with the
  CP4 v2 run wiring).
- Tests (test_delivery_request_v2.py, 22 passed): 7 FEWS delivery refusals (missing model, relabeled package, missing
  asset, undeclared diagnostic, evidence of another package, wrong fill contract, IPCCH model in the FEWS block);
  nested refs enumerated (12); mixed IPCCH generation + FEWS inference: one wrong nested diagnostic evidence hash
  rejects the whole request; a malformed nested ref is refused structurally with zero reference lookups.
- Full suite `full-suite-run1.log`: `pytest tests` 796 passed, rc 0 (v1/FEWS/legacy included).

## Runner R48 admission + inference-failure outcome (Supervisor runner spot-check; repro supervisor-smoke-admission-repro.md)
- `delivery_request_v2.admit_namespaces` (called by `admit` BEFORE `verify_reference_identities`): decided lexically on
  the URIs; the explicit shared allowlist is `ipcch.model_combination.envelope` and `runtime.environment_manifest`;
  every other reference (refresh files, FEWS refs) must lie under the request mode's configured trusted prefixes and a
  named feature batch manifest under that mode's `<batch root>/feature_batches/`; `..` segments refused; no configured
  namespace -> nothing resolved. `admit` now requires `trusted_prefixes` and `batch_roots`.
- `run_v2.run_ipcch` raises `IpcchRunFailure(operation, cause, partial)`; `run_request` keeps `failed_operation` and the
  partial result, so a successful generation's batch id/ref (`result.generation`, `result.batch`) survives an inference
  failure for reporting and reuse.
- Tests (test_ipcch_run_v2.py): smoke inference-only naming a real batch manifest and a smoke generation with an ACLED
  refresh file in the real input bucket -> refused by admit; resolver spy records no real URI; IPCCH context never
  built. Failed inference keeps generation status + batch id/manifest ref.
- R45 per-version receipts (Supervisor residual on _record_runtime): `VersionedTable.commit` records a HEAD `lineage`
  (version, content path, sha256, action) [GitNexus CRITICAL by fan-in: every IPCCH store writer; additive key];
  Generation reconciles at run start and after every step: one runtime record per saved version (name = immutable
  version content path), idempotent by (path, sha256), initialise versions excluded. Tests: two saved months then a
  later base failure -> both versions recorded; injected acceptance-write failure -> retry (keep ACLED) repairs each
  missing climate record exactly once via `reconcile`, no re-save, no duplicates.
Receipt `runner-r48-full-suite-run1.log`: `pytest tests` 820 passed, rc 0.
