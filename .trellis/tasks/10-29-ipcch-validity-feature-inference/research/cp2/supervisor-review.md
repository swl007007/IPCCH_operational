# CP2 supervisor review — ongoing

Training release and image/spec pins: ../cp1/supervisor-review.md. CP2 is not accepted yet.

## Package review at f6822b5

Read `control-plane-h2h8h14-pkg/research_cloud/packages/operational_ipcch.py` in full.

- Blocking portability issue: main lines 225–242 wrote evidence to OUT/evidence while the package manifest in OUT/package referenced evidence/name. write_combination hashed only package files. A standalone relocated package therefore omitted its runtime diagnostics. Requested evidence inside package/evidence with manifest hashes, plus a relocation test without siblings and tamper rejection.
- Weight integrity gap: load_boosters lines 56–68 accepted missing weight hash entries. Requested mandatory weight hash verification and binding caller-supplied run identities to harvested publication records.
- Positive checks: exact fitted matrix/key/label digests and backbone membership checked; all actual fit rows retained; raw quartet used for threshold errors and residuals; JSON/UBJ comparison uses the full fit matrix; NaN passthrough and default 0.20/cummax metadata retained. These observations do not substitute for actual new-weight replay.

Executor was notified; fixes and tests pending independent review. Frozen training worktree must remain unchanged.

Follow-up: reviewed fix `3c8c4d6` diff and `c6c7-tests-run4-ok.log` (9 tests, OK). Runtime area/residual CSVs now reside under package/evidence and are hashed; row-level audit sidecars remain outside. Relocation/tamper/missing/unlisted tests cover the path fix. Weight loading requires whole-source package verification and each weight hash; supplied run identity binds to publication/package identity. These code findings are resolved, subject to actual three-model package replay. Minor test-layout note sent: move unittest.main guard below the added Portability class so direct script invocation includes it.

## Harvest

Reviewed read-only `staging/ipcch-h2h8h14-20261030/job-packet/harvest_final.py`, SHA256 `eb329e17b1ba3ee504cb2c73029151ab80910680a2ed66cc2fa46fa5a05f2caf`. Released after successful job termination: generation-pinned GCS download into new local destinations, pinned old transport helper, package/config/source/fitting identity checks. Local publication records are not independent live MLflow readback; that remains required.

## Actual package intermediate verification

All three cloud jobs succeeded and harvest receipts have all 11 checks true. H2 run f55ddf45198f427eade6d68c2a3a04f2; H8 0f7e584fccc549a28cf6fe9519b94da2; H14 a4bf0a5d2bef4418b31503d679ac3194. Executor performed GET-only MLflow run/version/LoggedModel/DatasetInput readback (research/cp2/mlflow-readback).

Actual model combination at `R/scratch/h2h8h14-final/package-build/out-r1/package` has manifest SHA256 `18b91d454163ac9ff9833d8127108e731b2f9d95069fb26fd5e7e8877a115f22`, candidate status. Supervisor independently hashed all 28 listed files and verified all evidence paths/hash bindings and per-scope H/cutoff/run identities. Rebuilt fit matrices/evidence have 128090/121096/110762 rows.

Reviewed relocated raw-score check script and required correction of missing package ID and identical hardcoded target dates. Corrected `package-check/runtime_check_real_r2.json` inspected: combination_id ipcch-validity-h2h8h14-final-20261030, ok=true, all identity/date assertions true for H2/H8/H14. This is historical fit/scored feature-probe scoring compatibility, not complete current-month feature generation E2E. Full handoff assets/history/acceptance records and integrated CP5 remain pending; candidate is not silently accepted by these checks.


## 2026-10-30: r4 initial-input handoff review

Independent scan verified all 52 payload SHA256/bytes/row counts (2,202,444,303 bytes), 51 draft R45 entries, exact 6,226 feature roster, unique history keys and 149,424 season windows. Manifest SHA256 2c7dd2c026932dc87adcb558ed7a582069bbce893541f34fafd337a20216acbd; acceptance draft SHA256 27d6f744f77d5c3fe3c935bd31001ab1c05e39a0eb019f40717decda10481f1f. Acceptance fields correctly remain null.

Acceptance withheld pending modeled-area geometry/population references required by design.md:27, and 31 blank ISO3 values (all CI) in area_identity. Validate complete country identities against authoritative mapping. Delivered byte-preserved ACLED unit tables include excluded admin 1315: document this fixed-source exception and enforce/test exact roster in computed outputs. Do not describe all fixed inputs as filtered. Historical seasonal single-source SD=0 occurs in 103 rows (CDD44, rainy_days44, prcp_z15); preserve delivered historical values/provenance and explicitly record this imported metadata exception, separate from R34 new computed-output rules. Upstream QA remains excluded; this is not permission to alter training ensemble means. These bounded fixes were dispatched to the existing Executor. CP2 remains open.


### r5 delta verified (research package builder dac4a0a)

r5 manifest SHA256 `e6e3ebc60ad816bda4580cf3cef65258ba1cb708a4766d9f4d76fbd13f5c97b4`; draft acceptance `3621c350d3a8c22f45562368ce30b2041019b74acaa8f17deeb80f9fc887c372`. Seven changed/new payloads independently rehashed; 51 records unchanged from verified r4, including every historical input. 57 draft acceptance entries match and remain null. Geometry five source files are byte-identical to pinned repaired geometry; DBF6227 contains exact6226 modeled roster plus excluded1315. Consumers must explicitly filter. Population43889 unique area/reference-month keys covers exact6226, dates2014-01..2026-04, no1315. CI iso3_reference=CIV derives from pinned ISO table while original training iso3 and national history remain unchanged. Imported103 seasonal SD=0 exceptions are explicitly recorded. ACLED roster filtering plus existing no-future population tests:7 passed.

Data-reference delivery checks accepted as evidence; CP2/package status remains unaccepted pending immutable binding of the selected model combination to the exact handoff manifest, runtime geometry roster enforcement, and integration of the new population reference with existing PopulationSnapshotBuilder. Preserve original candidate18b91d45 as evidence; explicit accepted envelope may bind its manifest hash to the completed handoff. No status fields populated yet; no live current mutation.


### e3a438b binding checkpoint review

Independent focused suites: binding/initial19 passed, geography/climate/population51 passed, climate_run4 passed. Actual96,651,293-byte model package rehashed; package18b91d45, envelopee0ad66a2, handoffe6e3ebc6 and draft3621c350 identities agree. Per-scope H/public-lead/cutoff and shared527 order verified. Geometry6226/drop1315 and no-future population at three origins reproduce recorded results. Main Supervisor then rehashed ALL r5 payloads:58 files,2,271,631,220bytes,zero mismatches,6.67s,exit0. No cloud calls.

GitNexus CRITICAL flow-count signal inspected against actual14-file commit: changes confined to IPCCH binding/geography/initial/climate modules, tests and evidence; no FEWS scientific or shared model implementation change. A real R48 defect remains: verify_fixture_bundle opens real manifest/roster/acceptance before rejecting a misrouted nonfixture bundle. Require fixture-root admission before filesystem access plus marker validation before payload access, with wrong-real-path forbidden-read spy regression. Explicit acceptance withheld until this is repaired; original candidate/drafts remain preserved.


### Explicit research handoff acceptance — 2026-10-30

R48 repairs89b0e02/ec5bd53 inspected; main Supervisor independently ran binding+initial suites:21 passed in8.29s,exit0. Wrong-root/nonfixture/symlink-root paths now reject before real reads. The original model payload manifest `18b91d454163ac9ff9833d8127108e731b2f9d95069fb26fd5e7e8877a115f22` and r5 handoff manifest `e6e3ebc60ad816bda4580cf3cef65258ba1cb708a4766d9f4d76fbd13f5c97b4` are explicitly accepted by Codex Supervisor with the documented historical metadata, source-availability and method limitations. Finalize tool d3130e7 reviewed; Executor authorized to create out-r5-accepted-v1 and envelope-v2-accepted with acceptor Codex Supervisor/date2026-10-30, preserving originals. Acceptance binds finalized57 entries, not the original draft digest. CP2 final closure awaits successful final hash/real-mode verification and isolated local-store readback. No production retained-store/current writes or live-data-readiness claim is authorized by this act.


## CP2 ACCEPTED — final readback verified 2026-10-30

Executor receipt c9c080a reviewed (`binding/acceptance-readback.json` and executable readback script). Main Supervisor independently rehashed final small metadata and ran `verify_combination(mode=real, expected_envelope_sha256=...)` plus `verify_handoff` against actual accepted paths: PASS,57 finalized entries,6226 roster,527 columns. Accepted envelope SHA256 `03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596`; finalized entries SHA256 `cb14a956f67df03d5f3479d129a432d606017a533d0c80a9930d549d9aa95ed6`. Envelope at `R/scratch/h2h8h14-final/envelope/ipcch-combination-envelope-v2-accepted.json`; accepted bundle at `R/scratch/h2h8h14-final/handoff-build/out-r5-accepted-v1`.

Readback validates58 payload hashes (2,271,631,220 bytes), installs57 records into a LOCAL temporary real-mode store, initializes52 tables plus5 geometry files, reinitializes52 unchanged, reads fixed roster/order and all source families, and population6226 at O2026-08 with latest reference2026-04. Original candidate package/r5 manifest/draft hashes unchanged; original draft cannot initialize the accepted binding. No production store/current/cloud writes. This closes CP2 only; CP3 runtime integration/repair and CP4–CP6 remain open, including deferred live/full-area limits.
