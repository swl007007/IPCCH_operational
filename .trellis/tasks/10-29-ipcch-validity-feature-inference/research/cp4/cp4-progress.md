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

## Phase B review fixes (supervisor-review 8972e10) + Phase C core (this commit)
- Member: one `is_member_file` predicate for writer and verifier (mixed assemblies verify); `verify_member` enforces,
  independent of the inventory, exact H2/H8/H14 with leads 0/6/12, O = M - 2, T = M + lead and REQUIRED_FILES; copied
  envelope sha == provenance digest + identity (accepted in real mode); package identity vs expected.package; geometry
  = exact unique roster, valid non-empty EPSG:4326 polygons.
- Provenance: per-base seasonal sections `gs_<base>` report the latest completed season WITH a value (concrete
  `history__climate_gs_<base>` refs); `growing_season_calendar` reports the calendar selection separately
  (fixed__season_windows ref); generation refs include season windows/calendar.
- Phase C core: cloud/ipcch/delivery_v2.py (byte-for-byte inheritance from the source tree vs its inventory, legacy
  member own-origin checks, explicit shared-report merge with member months, manifest, upload, verify_delivery = the
  actual publication verifier) and cloud/ipcch/release_v2.py (publish_ipcch_run bound to the expected snapshot);
  publication: legacy members carry their delivery ref; inheritance marker replaced not stacked.
- Tests: review regressions (mixed assembly, horizons [], missing scope artifact, envelope {}, empty geometry,
  expected.package mismatch, all-13 seasonal NaN vs calendar selection); test_ipcch_release_v2.py (4): first real IPCCH
  publication inherits a legacy FEWS member byte-for-byte under its own 2026-09 months and activates; inherit-of-inherit;
  tampered source member refuses; moved pointer -> publication_failed; candidate never moves pointer; smoke root only.
  Full suite `phase-bc-full-suite-run1.log`: 851 passed.
EXPLICITLY UNFINISHED (callbacks/seams are not complete routes): CP4 entrypoint dispatch (v2 request route in the
deployed job/workflow + run_v2 locks through publication + smoke separate root), legacy v1 wiring (post-activation IPCCH
rejection at request+publish time, v1 FEWS-only inheritance of the v2 IPCCH member with activation carried, v1 locks),
promote/resume rejection of new-contract candidates, the FEWS v2 adapter (R60), and the real provider route
(EETransport.from_environment + real_provider_factory wired into an operator/deploy entrypoint). Then CP5 with the
actual accepted package and CP6.

## Supervisor review of 6e57972: Phase B six findings CLOSED; Phase C MAJOR BLOCKER (inherited artifacts) - fix
Finding: `verify_delivery` checked inherited files only against the newly assembled delivery manifest, then compared
member metadata and own-month columns; it did not compare the inherited artifact set/bytes with the snapshot-bound
source inventory. Scout repro: inherited FEWS probability .4 -> .99 or package/geometry/sidecars removed, destination
inventory regenerated, `publication.publish` with the actual verifier published and moved current.
Fix (delivery_v2): `source_member` reads the snapshot-bound member's PINNED source inventory and selects its exact member
files with the same rules as `inherit` (`member_paths`; v2 IPCCH = provenance files + system_provenance.json, legacy =
the legacy member pattern incl. model_package/geometry/sidecars); `verify_delivery` requires, independent of the new
delivery's own inventory, the member file set in this delivery == the source member set (no missing, no extra) and
each sha256 == the source inventory's (stored bytes == this manifest is checked first, so stored bytes == source).
Mixed deliveries and inherit-of-inherit unchanged (the member record keeps the original source delivery ref).
Regression (test_ipcch_release_v2.py, through `release_v2.publish_ipcch_run` -> `publication.publish` with the actual
verifier, current AND candidate): edited inherited value and missing supporting files (package, geometry, sidecar) with
a self-consistently regenerated destination inventory -> `DeliveryError` before any current/candidate mutation (pointer
generation and record unchanged, no candidate record). Mutation check: the 4 new cases FAIL against the 6e57972
`delivery_v2.py` and pass with the fix. Receipts: `inherited-verifier-focused-run1.log` (release/member/publication
25 passed), `inherited-verifier-full-suite-run1.log` (855 passed). CP4 remains unaccepted.
