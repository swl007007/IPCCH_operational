# CP3 IPCCH generation orchestration (Executor, 2026-10-30)

`cloud/ipcch/generation.py` `Generation(...).run()` for one validated v2 request:
pre-checks (request/binding/store mode agree, R48; store paired with the binding; bundle = the store's initialised bundle:
real `verify_handoff`, smoke `verify_fixture_bundle`); then steps, each saved as it succeeds (R29/R41), failures raise
`GenerationFailure(step, cause, report)` with everything already saved:
1. `acled_tables` (bundle fixed/acled files re-hashed vs the bound manifest; smoke: admitted fixture files) ->
   `acled` keep/refresh (pinned file, parse_export, refresh; keep without saved coverage refused R44; coverage end vs O
   warning R53) -> `research_inputs` (series families via retained.refresh_interval; idp_national interval replacement
   with validate_idp_national) -> `history_snapshot` (replace_snapshot; snapshot_warning R62) -> `wfp` (wfp.apply).
2. `climate` climate_run.update_all on `history__climate_*` tables (fixed in 669d2c1), declared_extra from the bundle.
3. geometry `geography.roster_geometries` -> `remote_sources.native_geometries`; `gpp` update_gpp; `nightlight`.
4. `assembly`: read_assembly_inputs(binding) + ACLED monthly_series from the weekly store (months from the first saved
   week or O-24 through O) + per-horizon assemble at T = O + H on the full roster + read_population(O).
5. `batch`: write_batch with methods, coverage ends (acled, GPP, nightlight, WFP, research families, snapshot), gaps
   (climate monthly/seasonal, GPP unpublished, nightlight), warnings, population/geometry reports, input choices,
   acceptance records consumed (store acceptance manifest) and retained-input HEAD refs.

Smoke fixture `tests/cloud/ipcch_smoke_fixture.py` (fixture: true bundle for areas 11/12/13 with population,
delivered-format ACLED tables, shapefile with declared 1315, fake climate providers, 404 GPP, unpublished VIIRS, pinned
refresh refs, validated v2 smoke request M=2027-03/O=2027-01).
Tests `tests/cloud/test_ipcch_generation.py` (3): full generation -> batch -> load_batch -> score_batch through the
runtime (manifest coverage/gaps/warnings/methods/retained refs; climate O month saved for roster only; GPP/nightlight O
NaN not blocking; ACLED A=O-1 present; population LOCF); O without climate source blocks at `climate` with the ACLED
refresh saved and no batch; ACLED keep without history refused. Regression `generation-tests-run1.log`: 211 passed.
Not yet: the real-mode provider factory (EE transport + table providers + calendar) and CP4 publication.

## Real provider factory (climate_run.real_providers)
`real_providers(transport, origin, roster, calendar_windows, asset_root=None)` builds every base's providers over ONE
concrete `EETransport`: MonthlyEEProvider, SeasonalEEProvider(data_end = first day after O, full calendar windows),
VegetationProvider/SeasonalVegetationProvider (S2E3, roster admins), DroughtProvider/SeasonalDroughtProvider (S2C3,
roster admins); `asset_root` overrides the shared scripts' han-sandbox root. Test (test_ipcch_ee_transport.py): every
base routed; raster base with no listed images -> unavailable (receipt image_times); S2E3 and S2C3 bases with
definitively absent private assets -> blocking failures through the transport. Live EE remains deferred (private assets
unreadable; any EE compute needs a Supervisor packet).

## Supervisor decision (envelope selection) + generation findings on f90e97b - repairs
- Request contract: `ipcch.model_combination = {combination_id, envelope: ObjectRef}` (old package_manifest shape and
  extra fields refused); `iter_object_refs` yields `ipcch.model_combination.envelope`. `binding.require_selection`
  compares the request's combination id + pinned envelope sha256 with the verified Binding; Generation calls it before
  any store access (test: other envelope of the same package, other combination id -> refused, zero store files changed).
- (1) Season windows: delivered windows end with 2026 (accepted handoff); `Generation._season_windows` derives
  completed later windows from the delivered calendar with the seasonal script's `windows_from_calendar`, after
  checking the calendar reproduces the last delivered year exactly; the SAME frame feeds the climate update and
  assembly. Fixture no longer pre-seeds future windows/seasons. Tests: O = 2027-07 -> derived 2027 (6 valid rows),
  2027-s1 saved for 11/12/13 (2027-s2 not complete), gs_last1 feature == the derived season's value; a tampered
  calendar that does not reproduce 2026 is refused.
- (2) R45 runtime acceptance: every step's saved table changes append `kind=runtime` records (name = table, sha256 =
  new HEAD content, acceptor `ipcch-runtime:<run_id>`), also after a failure (saved progress); a rerun that saves
  nothing appends nothing. Tests: success records incl. climate/ACLED/GPP ledger bound to HEAD sha; climate-block
  failure records the saved ACLED refresh; rerun adds no duplicates.
- (3) research_inputs report is written per family as it completes (failure report keeps the committed nino34 refresh).
- (4) Optional-family coverage warnings (WFP_Price, GPP_mean, nightlight_mean, research series families) when coverage
  ends before O; never blocking.
- (5) R39 future-M rule and the M-2 derivation apply to IPCCH operations only; FEWS NET origin recorded separately
  (`derived.fewsnet_origin_month`: the prepared snapshot's own origin for inference-only, the run month for generation
  as in the legacy CLI). Tests: FEWS-only real M later than the UTC month admitted; IPCCH future M refused.
- Factory integration (Supervisor request): `real_providers -> SeasonalEEProvider -> EETransport -> update_seasonal`
  saves 2026-s1 (receipts image_times/missing_assets/export/read; per-feature temperature graph).
Receipt: `generation-findings-full-suite-run1.log`: `pytest tests` 816 passed, rc 0 (locked interpreter).

## Seasonal provider windows (Supervisor residual MAJOR on 3e97139)
`Generation.climate_providers` is now a factory `(windows, origin) -> ClimateProviders`, called with the derived
(delivered + calendar-extended) windows inside the climate step; `climate_run.real_provider_factory(transport, roster)`
builds `real_providers` from exactly that frame, so SeasonalEEProvider's rainfall bounds, the climate scheduling and the
assembly share one windows frame. Test: Generation passes `g.windows` (identity) with 2027 rows and O = 2027-07 to the
factory; a real provider built from it publishes 2027-s1 rainfall through a fake backend, while one built from the
delivered windows alone raises "no calendar windows for season year 2027" (the reproduced failure).
`provider-windows-tests-run1.log`: test_ipcch_*.py + request_v2 = 208 passed, rc 0.
