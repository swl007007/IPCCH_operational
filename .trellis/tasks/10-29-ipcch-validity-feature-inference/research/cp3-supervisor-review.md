# CP3 supervisor checkpoints — ongoing

## Stores and request unit checks

Reviewed stores/retained at 9270192. Required fixes: unique immutable content names so failed HEAD updates do not poison future commits; content and generation from one stable snapshot to avoid lost updates; enforce HEAD content stays within its own table namespace; validate required acceptance fields; refuse explicit failed/contradictory GPP probes.

Reviewed fix 557515f: the above mechanisms are corrected. Independently ran from cloud_pipeline with the operational exact-lock interpreter:
`PYTHONDONTWRITEBYTECODE=1 ~/.venvs/fewsnet-test-lock-20261022/bin/python -m pytest tests/cloud/test_ipcch_stores.py tests/cloud/test_delivery_request_v2.py -q -p no:cacheprovider`
Result: 24 passed in 0.95s, exit 0. This is scoped unit evidence, not final CP3 acceptance or full request integration verification.

## ACLED c65e43d

Read-only scout inspected converter/tests/parity evidence; Supervisor checked the relevant implementation lines. Confirmed issue: validate_export parses non-padded week strings but persisted original text; refresh compares stored week strings to ISO interval boundaries. An accepted `2026-5-2` row survives a refresh replacing `2026-05-02`, double counting. Scout reproduced 7+5 ->12 (non-lock environment); exact-lock regression requested from Executor, along with canonicalization before duplicate checks/persistence (or strict rejection). Existing parity covers 18 columns and 1,250,808 rows but cannot prove this input boundary.

Other scout observations: runtime uses delivered fixed mapping rather than rematching geometry; interval completeness uses overlapping Saturday weeks, including event-free coverage; d_m/7 allocation and no initial HEAD on coverage rejection have tests. Delivery-table override/nearest construction and full runtime integration remain to verify.

Follow-up: reviewed b3035ad canonicalization before duplicate detection/persistence and strict declared-date/month handling. Independently ran exact-lock `pytest tests/cloud/test_ipcch_acled.py -q -p no:cacheprovider`: 8 passed in 0.97s, exit 0. Executor also records two regression tests failing against c65e43d and unchanged full-history parity. Date double-counting finding resolved; full CP3 remains incomplete.

Request integration follow-up: standalone v2 validator defers FEWS delivery validation to its adapter and does not enumerate nested delivery refs. Required before any collection/mutation: adapter validates the full FEWS block and all model/asset/diagnostic refs, including a mixed IPCCH+invalid-FEWS zero-write test (R17). Executor acknowledged; pending integrated verification.

## Climate scope clarification

Executor found nine shared scripts are GEE Code Editor JS with private calendar/baseline assets; SPI/SPEI uses portable numpy/scipy after GEE input download. Supervisor ruling: ensemble persistence core and SPI/SPEI math proceed, but a SourceProvider protocol plus request-spec stubs alone does not satisfy R1/R40/R43. Executable real provider adapters invoking the delivered algorithms remain in this goal. Reuse existing execution or retained/transpiled JS where practical; no blanket requirement to rewrite everything into Python. Offline differential and boundary tests are required; actual live GEE extraction is deferred by the execution protocol, not an excuse to omit implementation.

User cloud-read preauthorization covers necessary private-asset metadata/access verification, including han-sandbox-505315. No renewed human approval is required. Actual EE compute/export requires a concrete Supervisor-reviewed packet before execution; no IAM changes. If assets are inaccessible, retain configurable references, explicit runtime failure and offline-tested adapters, and report the observed live limitation. Baseline placeholders are authorized; algorithm placeholders are not final deliverables.

## Climate dab5bc9 focused read-only check

Scout ran exact-lock climate/SPI suites: 11 passed in 1.05s, no skipped (monthly original differential executed). Monthly persistence/late-source/no-zero-fill tests support the intended core. Supervisor spot-checked reported lines and sent these fixes:

- spi_spei._check verifies each matrix's month count but not equal area dimension; P(2,430) and ET0(1,430) silently broadcast. Require equal shapes and caller key alignment.
- climate.completed_windows validates a date regex only; 2026-02-31 is accepted. Require actual calendar dates.
- Monthly differential is not seasonal fidelity. The seasonal original fit_glo_ubpwm at lines 3899/3904 uses unbiased weights r/(n-1), r(r-1)/((n-1)(n-2)); line 3960 uses k=-tau3. Current monthly port uses plotting positions and different beta formulas. Scout extracted seasonal pure functions without EE/IO and obtained 715 common finite values all differing (max 0.4392419183), 141 NaN-mask differences on seed41 (2,430) inputs. Retain separate seasonal original math and a seasonal differential; do not infer equality from the shared method string. Seasonal adapter is still in progress, so this is a required integration boundary rather than a claim about finished adapters.
- Latest-two completed season selection remains feature-assembly verification, not established by core storage tests.


## 2026-10-30: monthly/table/seasonal adapter checkpoint (4ebb7d0..b8ea796)

Independent read-only scouts plus Supervisor source spot checks; no Trellis Audit or live EE execution. Monthly raster tests 14 passed; table/run/numeric subset 24 passed; seasonal raster 10 passed in the pinned operational interpreter. These are offline graph/boundary checks, not raster numerical replay.

Open fixes dispatched to the bound Claude Executor:
- `climate_ee.publication`: GLDAS unique-hour count admits 248 consecutive hourly stamps in August despite <11 days coverage. Require the actual expected UTC 3-hour slots; daily duplicate/month-boundary checks passed. Complete-month publication policy approved for monthly providers only.
- `climate_tables` monthly and seasonal drought axes truncate before the complete 1991–2020 fit baseline for historical targets. Preserve fixed baseline and explicitly select target output. PATCH32-filled target columns must participate in availability.
- Reject malformed nonnumeric table values and absent required admins; do not convert them to published NaN. Preserve legitimate numeric missingness.
- `climate_run` failure reports must retain progress already saved within the failing base, not only previously completed bases.
- Seasonal rainfall must use full both-season calendar bounds consistent with full-admin painting and clamp actual data bounds to the run origin end-exclusive. Requested-subset bounds are insufficient; extended calendar bounds cannot read beyond the run cutoff.
- Seasonal temperature/soil must preserve delivered available-observation semantics, without a new full-month completeness gate. Missing dates outside a season must not invalidate that source.

Executor remains owner of fixes and regression tests; CP3 is not accepted. Private assets are unreadable, source-table producers and rainfall collision patch are not delivered; these limitations remain explicit.


### Initial-loader and assembly checks (uncommitted working snapshot)

Pinned operational interpreter: assembly tests 2 passed; initial/store tests 13 passed. Vendored months bytes, compact import-only adaptation, and validity AST slices match pinned research sources. O=T-H, ACLED O-1, completed-season boundary, and no GPP raw fill were checked. Full historical parity is still running, not accepted here.

Open fixes sent to Executor: empty optional local-IDP grid fails on int(NaN); duplicate national-IDP country/report month silently picks last row; fractional admin ids truncate before validation. Initial-loader parses after prior commits, so malformed later CSV leaves partial initialization; preflight parse/schema/head-conflicts before mutation. Initialized history_snapshot HEAD needs preparation_cutoff for retained.snapshot_warning. Numeric NaN, nextafter(0.1,1.0), and literal ISO3 NA round-trip were verified. CI identity-only ISO3 correction does not change current national-IDP features because the r4 national history contains no CIV or blank ISO3 rows; do not silently re-export that history.


### Repair verification c090c4e / ad931c2

Independent climate suites: 38 passed; assembly/initial suites: 6 passed. GLDAS expected slots, full drought baseline/target selection, PATCH32 availability, same-base failure progress, seasonal full-calendar/cutoff and available-sample semantics verified. Empty optional grids, duplicate national-IDP keys, fractional request identifiers, two-pass initialization/head conflict handling and snapshot cutoff metadata verified. Standalone operational imports work without research_cloud; exact float and literal ISO3 NA round trips pass.

Two residuals remain and were dispatched: VI joins retain baseline admins missing from current source tables, disguising missing rows as published NaN; validate each required current table before joining. Initialization preflight does not yet validate all schema fields: malformed snapshot area_id, season_windows season_year, or local-IDP month can be persisted before a later read/assembly fails. Validate all runtime keys/date fields before commits and retain zero-write regressions. No acceptance granted yet.


Residual repair direct Supervisor check: exact-lock `python -B -m pytest -q -p no:cacheprovider tests/cloud/test_ipcch_initial.py tests/cloud/test_ipcch_climate_tables.py` from cloud_pipeline: 18 passed in 9.28s, exit 0. Reviewed current-table validation before joins and initial identifier/month/date field preflight plus zero-write tests. Both residual findings resolved for snapshot {'cloud_pipeline/cloud/ipcch/climate_tables.py': '34ccdc4652be88f955768c31952b07cae5fe70335bd53f9aa0534afd0910bdaa', 'cloud_pipeline/cloud/ipcch/initial.py': '93aba7d16d1c3013df89e07da23e5e1cabaa0a858aa69b12f82eeb75c6c0ef72'}. Complete checkpoint remains open pending handoff, parity and runtime integration.


### Historical assembled-input compatibility result

Supervisor inspected `assembly-parity/stage3_effective.py`, `R/scratch/h2h8h14-final/assembly-parity/r2_exact_effective.json` and run-r2.log. All H2/H8/H14 have18,317 probes: effective float32 input differences0; raw q2/q3/q4/q5 score differences0 through the operational runtime; feature-contract reports both passed; verdict EFFECTIVE_IDENTICAL,exit0. Original float64 differences and zero NaN-mask mismatches remain recorded, not rounded away. Research-parser comparison continues to isolate the CSV-parser cause; coordinate differences affect historical fit probes only. This establishes historical numerical compatibility, not CP5 current-month/date/publication behavior; scorer probe metadata is fixed illustrative dates.

Current integration gap confirmed by targeted source inspection: real EEBackend/TableBackend transport implementations and production provider construction still need CP3 generation wiring. Reuse existing acquisition/task-polling/GCS read patterns; auth/permission/ambiguous-not-found must remain processing failures. Protocols/mocks alone do not satisfy executable collection. Executor notified; no new live EE work required.


### Transport and GPP integration review (8d031db /72f8cd8 /f1af645)

Concrete EE/GCS transport is implemented, with installed EE1.7.36 API/pagination checks and41 focused tests. Main initial findings (submit-before-record and unbounded wait/no cancel) repaired in72f8cd8; independent13-test check confirms reserve-before-submit, no duplicate submission afterfailed/completed record, bounded sleeps and normal timeout/persistence-failure cancellation. Remaining faults dispatched: immediately recheck budget before submission after reservation; ambiguous task.start failure must retain known task ID and best-effort cancel; combined ID-persistence/cancel failure must expose task ID in durable recovery/error evidence, without automatic resubmission. Existing FEWS wait helper unchanged.

GPP f1af645: independent50 tests; synthetic uint16 formula agrees with research (mask65534/65535 before float64 sum/count,scale0.01,truezero preserved,allfillNaN), legacy shared extraction unchanged. One reproduced persistence flaw remains: successful history commit with legitimate pixel NaN followed by published-ledger commit failure leaves stale unpublished status; retry filters only nonmissing savedvalues and overwrites legitimateNaN. Preserve saved published rows includingNaN across this interruption; add fault-injected retry regression. Runtime entrypoint wiring remains pending.

Parityr2 final run exit0: stage2 exact DIFFERS/rc2, stage3 EFFECTIVE_IDENTICAL/rc0; research-parser stage2 differs onlylat/lon (525/527 exact), stage3 EFFECTIVE_IDENTICAL/rc0. All horizons18,317 probes; effective inputs and q2..q5 numerical outputs identical. Float64 discrepancies remain explicitly characterized, not redefined as bit-exact equality. This closes the historical numerical compatibility check only.


## 2026-10-30 focused batch/WFP review (ced8e52 / 8e00c8a)

CP3 remains pending. Read-only scouts reproduced the following; Supervisor spot-checked the implicated source and sent the repair packet to verified executor session 6a490ae1 in w1A:p2.

- batch_inference.py:104-107,132-137: smoke reads real-namespace manifest before rejection and permits real horizon refs. Require pre-read namespace admission and zero-touch spies.
- batch_inference.py:149-154: package_root only checked for order/cutoff, not bound package identity/member hashes. Require existing package verification against Binding; wrong-package regression.
- batch.py:98-124 / batch_inference.py:128-137: caller roster is not bound to accepted real roster; three-row real batch accepted despite handoff size6226. Preserve deliberate smoke subsets only.
- batch_inference.py:132-137,167-171: horizon metadata not validated; target1999-01 accepted for M2026-10. Derive/validate all dates and leads.
- batch.py:71-77 / batch_inference.py:89-99: area_id consistency/uniqueness omitted relative to existing runtime adapter.
- wfp.py:35-37: ragged CSV row9999,1,2026-08,123.5 under three-column header silently loses first field via pandas implicit index. Reject malformed widths before writes; inspect batch parser for same mechanism.
- wfp.py:59-61: empty initialized history misclassified as absent; successful empty replacement prevents subsequent keep/refresh. Use persisted initialization state and test clear/keep/repopulate.

Existing targeted tests alone do not cover these reproductions. Generation coverage warnings and retained keep provenance remain integration checks. WFP centred ±6-month filtering may embed later observations in historical inputs; compatibility evidence is not a no-leakage/as-of proof. No algorithm change or retraining is authorized by this finding.


## 2026-10-30 generation/preflight review (f90e97b / 3e7c470)

CP3 remains pending. Pinned-source reproductions and Supervisor source spot-check identify: generation ignores requested model selection; fixed season_windows ends2026 and needs calendar-derived future windows in both climate and assembly; saved runtime versions receive no R45 runtime acceptance entries; a later research-family error omits earlier saved refreshes from failure reports; WFP coverage<O has no warning. Repair packet delivered to verified Executor.

Preflight shared validators and nested references passed 15 explicit tampered-reference cases; locked delivery regressions249+frozen diagnostics5 passed in independent scout. Actual runner admission-before-write spy remains pending integration. Existing future-M validation also incorrectly applies R39 to FEWS-only; preserve FEWS own origin semantics when wiring runner. Climate history table-name correction669d2c1 matches initialization.

Approved bounded selection clarification: request uses combination_id plus immutable envelope ref, not redundant package_manifest ref. Canonical acceptance remains CP2 envelope; verify selected identity and package before mutation. No training or scientific algorithm change.

Repair verification 2d978d4: Supervisor inspected source diff plus targeted regression assertions for all seven batch/WFP findings. Locked Python -B pytest -q -p no:cacheprovider tests/cloud/test_ipcch_batch.py tests/cloud/test_ipcch_wfp.py tests/cloud/test_ipcch_generation.py: 29 passed in38.82s. Closes the seven specific reproductions; does not accept CP3 or prove pending runner/generation integration.


## 2026-10-30 concrete climate factory check (b52387c)

Independent read-only check plus Supervisor spot-check climate_run.py:81-101: six provider classes receive compatible constructor args and one concrete EETransport; all26 deferred monthly/seasonal bindings select correct base/class/asset roots. Locked transport/factory/monthly-raster/seasonal-raster/table suites57passed. No blocking factory defect found. New factory test directly invokes three monthly failure paths and checks seasonal callability; successful seasonal factory-to-transport flow remains a generation integration assertion. No live EE, asset permission or full-area claim.


## 2026-10-30 d0d7567 / 4db4fd5 follow-up

Pinned runner review30passed: namespace admission precedes resolution/context; trusted configuration is outside request; failed inference retains generated batch. Receipt review12store tests plus pinned regressions: intermediate committed versions recorded, failed-CAS orphan excluded, retry repairs missing receipts without resave. Remaining medium finding: successful operation followed by receipt append failure escapes without GenerationFailure report; initial reconcile likewise. Executor assigned reporting fix.

4db4fd5 source/test diff inspected: provider factory called with exact extended windows frame; regression exercises2027 real rainfall provider and demonstrates old frame failure. Supervisor locked generation+transport run28passed17.86s (working tree was concurrently receiving reporting edits; exact seasonal fix pinned in reviewed diff, do not call whole tree frozen). Prior full executor log independently inspected820passed122.02s.

Supervisor releases LOCAL CP4 implementation/tests after reporting fix, while CP3 acceptance remains pending complete runtime/FEWS adapters and evidence. This is parallel work authorization, not checkpoint acceptance. No production deployment/current mutation or Audit. CP5 must use actual accepted model combination.
