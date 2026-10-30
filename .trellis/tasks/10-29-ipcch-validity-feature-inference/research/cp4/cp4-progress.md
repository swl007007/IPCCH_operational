# CP4 progress / checkpoint ledger (Executor)

## Closed by Supervisor review (preserve)
- 08c7a2b locks -> findings fixed in 34362d8 (partial-acquire rollback on conflict AND transport failure with cause +
  cleanup failures; attempt-all release; `delete` in ObjectStore protocol; explicit bounded GCS delete retry; generation
  conditioning protects replacements) - CLOSED (lock+objectstore+request 35 passed).
- d7c3636 `ipcch.country_reference` ObjectRef (inference-only, trusted namespace, preflight) - reviewed.
- 47d7c4c publication core -> b684e90 stable release-record read (race test) and member mode check - CLOSED; required
  verifier seam correct (actual verifier = Phase B acceptance item).
- 016d90d receipt-failure reporting - CLOSED; b257908 utf-8-sig after raw-byte sha - correct.

## Phase B (this commit): new-contract IPCCH member + actual verifier
- `cloud/ipcch/delivery_member.py`: `write_member` (scopes/{0,6,12}m/ipcch tables via the shared builders; prediction
  header = legacy IPCCH header + `mode`; per-scope model_package_id = `<combination>/scope_<lead>m` (== evidence
  identity); diagnostics from the envelope-bound package evidence through unchanged `scope_diagnostics`; country
  reference = pinned census bytes, areas joined by accepted `iso3_reference` for delivery fields only; geometry =
  deterministic GeoJSON of the accepted roster geometry; model package files + envelope copied (portable/inheritable);
  `reports/ipcch_feature_fill_audit.csv` = the batch's row/section provenance; `ipcch/system_provenance.json` =
  own M/O/targets/leads/mode/package/batch/roster identity + sha256 of every member file) and `verify_member` (all
  files re-hashed, no unlisted member file, package re-verified, per horizon roster-exact unique polygons, finite
  q2..q5, O, targets, mode, package id; optional expected identity + provenance sha).
- `cloud/ipcch/provenance.py` + batch `feature_provenance.csv` (hash-covered in the manifest; canonical-path pinned
  read `batch_inference.read_feature_provenance`): one row per (polygon, section) with dependency window, latest actual
  observation (month / season / report month), per-horizon missing counts, source table version/sha,
  fill_method none, nan_passthrough_no_imputation.
- Tests: test_ipcch_delivery_member.py (6): tables/provenance/verification on the smoke batch; tamper (changed,
  unlisted, missing) refused; R18 and census coverage and expected-mode mismatch refused; sidecar semantics (GPP latest
  2026-12 < O 2027-01 with missing counts, ACLED A = O-1, static sections, 527 features per polygon). Synthetic package
  now carries real-format evidence. Full suite `phase-b-full-suite-run1.log`: 845 passed, rc 0.
Next: Phase C/D (delivery assembly incl. inherited FEWS member + shared report merge, publication verifier wiring to
verify_member/inherited hashes, v1 legacy guards, smoke root), then CP5 with the ACTUAL package.
