# CP3d — feature assembly + R45 store initialisation (executed evidence; parity UNRESOLVED)

Code: `cloud/ipcch/assembly.py` (research recipe vendored verbatim: `vendor/ipcch_months.py` = months.py bytes, `vendor/ipcch_compact.py` = compact.py bytes except its one import line redirected, `vendor/ipcch_validity_feature_blocks.py` = AST-extracted history/IDP/local-IDP/ACLED-agg functions + constants of the trained features module e56ccf41 behind a labelled shim; generator `tools/vendor_ipcch_feature_formulas.py` checks the pinned shas), `cloud/ipcch/initial.py`, `retained.validate_snapshot/snapshot_record` (refactor shared by refresh and initialisation).
Operational-only differences (spec-required): fixed per-area lat/lon (R58 identity), 2027+ year dummies all zero (R58), history from the R62 snapshot without training-context family exclusions, GPP as retained (no R57 runtime filter), exact roster (R32).

Supervisor batch fixes (2026-10-30): empty optional sources -> all-NaN grid over the roster (features missing, not a block, R65); national IDP duplicate (iso3, report_month) rejected at the shared boundary `validate_idp_national` (assembly AND initialisation); integral admin/target/horizon (11.9 refused, horizon in 2/8/14); `initialise` preflights the WHOLE bundle (bytes, acceptance, full parse with per-path schemas, strict numerics, duplicate keys, snapshot/IDP validators, existing-HEAD conflicts) before any commit; history_snapshot HEAD carries the refresh validator's metadata (preparation_cutoff) so `snapshot_warning` works after initialisation; non-CSV accepted files (geometry) verified and reported.
Tests: `tests/cloud/test_ipcch_assembly.py` (3), `tests/cloud/test_ipcch_initial.py` (3: acceptance refusal + round trip bit-exact through the stores at H2/H8/H14 + byte tamper; malformed later file -> nothing committed; HEAD conflict -> nothing committed; init -> snapshot_warning). Receipt `cp3d-batch-tests-run1.log`: 92 passed (stores, request v2, ACLED incl. roster-exact test, assembly, initial, all climate suites).

## Assembly parity r1 — historical compatibility evidence (NOT the CP5 M2026-10/O2026-08 execution)
Harness `assembly-parity/` (run_r1.sh + stage2_operational_r1.py preserved; r1 log `run-r1.log`; hardened `run_v2.sh` + verdict exit for future runs into new dirs). Stage 1 rc=0 (18,317 rows per H incl. all 15,317 scored). Stage 2 H2: 435/527 columns exact; differing lat/lon and aggregated-ACLED columns; H8/H14 pending at the time of writing. UNRESOLVED until quantified per family (keyed NaN-mask mismatches, max abs, root cause: source/parser/dtype vs temporal semantics). No tolerance relaxation.

## Residual fixes after the c090c4e/ad931c2 review
- (A) climate_tables: required admin coverage is validated on the baseline and on EACH relevant current-year S2E3 table BEFORE the left join (roster when configured, else every baseline admin; seasonal: the requested windows' admins); a current table lacking an admin present in the baseline now fails instead of yielding a published NaN (test `test_current_table_missing_an_admin_fails_before_the_join`: monthly with/without roster, seasonal).
- (B) initial preflight: shared strict field validators for every runtime identifier/month/date/key column (`FIELD_KINDS`: integral admin_code/area_id/season_year/n_sources/phase, canonical YYYY-MM months, real calendar dates, s1/s2 season, ISO2/ISO3 shapes; training-lineage iso3 may be blank only in area_identity) plus the shared `climate.completed_windows` validator for season windows, all before any commit (byte-preserved ACLED tables are validated by `acled.AcledTables`). Parametrised test: area_id 'broken', season_year 'broken', month '2020-13', end date 2026-02-31, admin_code '11.0', iso3 'aa1' -> StoreError with zero table writes.
- Receipt `cp3d-residual-fixes-tests-run1.log`: 99 passed (stores, request v2, ACLED, assembly, initial, all climate suites). First run of the new block FAILED 3 existing tests: my sentinel origin 9999-12 overflowed year 10000 in completed_windows; changed to 9998-12.

## Assembly parity r1 — quantified differences and root causes (original r1 diffs preserved in `assembly-parity/r1/`)
r1 (exact-parse ACLED input, old harness without a verdict key; its exit 0 is NOT a pass): order == package; 435/527 columns bit-exact at every horizon; ZERO NaN-mask mismatches in every family. Differing columns (all horizons):
| family | columns | rows differing (max of H) | max abs | scored rows differing | root cause |
|---|---|---|---|---|---|
| lat/lon | 2 | 2,468 / 2,637 / 2,859 | 5.0e-11 | 0 | raw panel repeats each area's coordinate with float-text noise across months (per-area spread asserted <= 1e-9, max 5.0e-11, `cp2/handoff-inputs/coordinate_spread.csv`); research reads lat/lon at the target key, operational uses the latest-month constant (R58 identity) |
| ACLED-agg value_at_origin | 18 | 10,048 / 10,069 / 9,488 | 4.66e-10 (= 2^-31, 1 ulp at exposures of 2-4 million) | 8,505 / 8,553 / 8,110 | input TEXT parse: research `load_sources` parsed the interim CSV with pandas 3.0.3's default float parser; the harness parsed the same series with float_precision=round_trip (exact). Source values are otherwise identical (`diag/acled_src.py`: 1,250,808 keys, 0 differences, same NaN masks; `diag/parser.py`: default vs round_trip differ by <= 1 ulp in up to 448,605 cells/column, NaN masks equal) |
| ACLED-agg windows/stress | 72 | 15,672 / 15,487 / 15,277 | 4.66e-10 | 13,250 / 13,148 / 12,984 | the same 1-ulp input differences propagated through trailing means/SDs (a research-shaped grid with area 1315 and the blank 2026-10 rows changed nothing: layout is NOT the cause) |
Proof of the ACLED cause (`diag/h2_research_parse.py`): on 400 H2 rows, feeding the interim series parsed exactly as research parsed it -> 0 of 45,600 ACLED cells differ (vs 2,902 with the exact parse). Operational ACLED comes from the weekly-store port (its own exact parity, cp3c2-acled.md), not from this CSV; the training data are not changed and no tolerance is introduced.
r2 (running, `run_r2_effective.sh` -> `run-r2.log`): stage 2 without research rerun for the ORIGINAL exact-parse configuration and the research-parse diagnostic, each saving assembled arrays, then stage 3 comparing the float32 inputs XGBoost consumes bitwise and the raw q2..q5 scores of the package through the operational runtime bitwise; machine verdicts EFFECTIVE_IDENTICAL/EFFECTIVE_DIFFERS with rc.

## Assembly parity r2 - FINAL machine verdicts (historical compatibility evidence; not CP5 / target-date proof)
Run `research/cp3/assembly-parity/run_r2_effective.sh` (set -uo pipefail, each rc judged), log `run-r2.log`:
`SUMMARY stage2_exact=2 stage3_exact=0 stage2_research_parse=2 stage3_research_parse=0`, `exit=0`.
Outputs (new files; r1 evidence untouched) in R/scratch/h2h8h14-final/assembly-parity/: r2_exact.json,
r2_exact_effective.json, r2_research_parse.json, r2_research_parse_effective.json (+ assembled_hHH.npy).

| config | horizon | rows | float64 columns exact / 527 | float64 cells differing | NaN-mask mismatches | float32 effective cells differing | raw q2..q5 differing | contract | verdict |
|---|---|---|---|---|---|---|---|---|---|
| exact (ORIGINAL harness) | H2 | 18,317 | 435 | 318,461 | 0 | 0 | 0/0/0/0 | passed x2 | stage2 DIFFERS rc2; stage3 EFFECTIVE_IDENTICAL rc0 |
| exact | H8 | 18,317 | 435 | 322,412 | 0 | 0 | 0/0/0/0 | passed x2 | same |
| exact | H14 | 18,317 | 435 | 317,391 | 0 | 0 | 0/0/0/0 | passed x2 | same |
| research-parse | H2 | 18,317 | 525 | 4,933 | 0 | 0 | 0/0/0/0 | passed x2 | stage2 DIFFERS rc2; stage3 EFFECTIVE_IDENTICAL rc0 |
| research-parse | H8 | 18,317 | 525 | 5,271 | 0 | 0 | 0/0/0/0 | passed x2 | same |
| research-parse | H14 | 18,317 | 525 | 5,707 | 0 | 0 | 0/0/0/0 | passed x2 | same |

Per-family causes with ORIGINAL diffs (exact configuration):
- lat/lon (2 columns; H2 2,468/2,465 rows, H8 2,637/2,634, H14 2,859/2,848; max |diff| 5.0e-11; scored rows 0): the
  research panel repeats each area's coordinate per month with text-level noise; operational uses the handoff's fixed
  per-area coordinate (R58, latest month, spread bound 1e-9 recorded per area). Only historical fit rows differ.
- ACLED aggregated (90 of 114 columns; max |diff| 4.66e-10, ulp-level on large values; NaN mismatches 0): the research
  build parsed its ACLED CSV with the pandas default float parser, the original harness with exact round-trip parsing.
  Feeding the research-parsed input (research-parse configuration) removes ALL 90 ACLED differences (525/527 exact);
  only lat/lon remain.
- All other 435 columns bit-exact in both configurations.
Effective model input: after the runtime contract's float32 cast, 0 cells differ and raw q2..q5 scores through the
operational runtime are identical for all three horizons in both configurations. No tolerance was relaxed.
Supervisor accepted r2_exact_effective as historical feature/model compatibility evidence (stage3 metadata uses fixed
probe dates; not CP5 or target-date proof).
