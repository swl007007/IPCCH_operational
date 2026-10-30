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
