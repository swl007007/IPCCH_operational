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
