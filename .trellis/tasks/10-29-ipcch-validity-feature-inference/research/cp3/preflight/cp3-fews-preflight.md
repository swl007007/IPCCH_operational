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
