# CP2 combination/handoff binding, exact-roster geography and population (Executor, 2026-10-30)

Supervisor requirements: design.md:27/R32/R55 binding; R48 smoke boundary (smoke never resolves/reads the real handoff
assets just to validate an envelope); accepted envelope binds FINALIZED acceptance entries, never a stale draft digest;
candidate originals preserved; geometry filtered to the exact roster at every provider, without filtering the delivered
algorithms' calendar/paint context; population_reference -> existing PopulationSnapshotBuilder (no future period).

## Code (cloud_pipeline)
- `cloud/ipcch/binding.py` (new). Envelope schema `ipcch-combination-envelope-v1`, create-only, versioned
  (`<combination_id>/envelope-v<n>`). Binds package_manifest sha256 + combination id + contract version + per-scope
  horizon/lead/cutoff/feature-contract sha + feature-order sha (527 names, identical in the three scopes) and the handoff
  manifest sha + schema + roster size/sha; `acceptance_entries_sha256` only when status=accepted (finalized entries:
  acceptor + YYYY-MM-DD for exactly every runtime file at its manifest sha); a candidate records the draft digest as
  information only.
  - `verify_combination(envelope, package, mode)`: envelope + package only (all listed package files re-hashed, no
    unlisted/escaping file); real requires status accepted; smoke accepts candidate. No handoff asset is read.
  - `verify_handoff` (real only): bundle manifest, roster and finalized-entries digests must equal the envelope; a fixture
    bundle is refused. `verify_fixture_bundle` (smoke only): the fixture bundle (`fixture: true`) by its own manifest and
    declared roster subset.
  - Store pairing table `combination_binding` (mode, combination id, package manifest sha, feature order sha, bundle
    manifest sha, roster sha/size): written last by `initialise`; `read_assembly_inputs`/`read_population` require it;
    a store paired with another package/bundle is refused even with the same 527 order.
- `cloud/ipcch/initial.py`: `initialise(store, root, bundle, *, binding)` (mode must match the store root; real ->
  verify_handoff + each store acceptance record must equal the bound finalized entry; smoke -> fixture bundle only;
  roster size from the binding/declared subset; whole-bundle preflight then commits then pairing);
  `install_acceptance` (real: append the bound finalized entries to the store acceptance manifest);
  `read_assembly_inputs(store, root, binding)` (feature order = bound package order); `read_population(..., origin)`.
- `cloud/ipcch/geography.py` (new): `roster_geometries` (bundle shapefile, every component re-hashed, CRS EPSG:4326,
  filtered to the roster in roster order; only DECLARED extras (`roster_policy[...].out_of_roster_admins`) dropped,
  unknown/missing/duplicate fail) -> feeds the existing `remote_sources.native_geometries`/`zonal_statistics` path
  (GPP, VIIRS); `restrict_to_roster` for provider output tables; `population_snapshot` (existing
  `PopulationSnapshotBuilder` + `validate_population_contract`; later reference periods ignored and counted).
- `cloud/ipcch/climate.py` / `climate_run.py`: output-boundary filter is now strict: rows outside the requested areas
  are dropped only for known areas (other roster areas of a season, `declared_extra`), any other identifier fails (R32).
  The EE graphs are unchanged: the seasonal rainfall script still PAINTS the full unfiltered admin calendar (paint order,
  overlaps, declared 1315 included); only the reduction collection is filtered to the requested window areas.

## Distinction recorded (roster nuance)
- Fixed-source archives keep the declared 1315 exception (geometry, byte-preserved ACLED tables, the shared GEE admin
  assets). Algorithm context (rainfall calendar painting) uses the full delivered calendar.
- Exact modeled roster is enforced at: requested aggregation (EE seasonal reduceRegions collection = requested window
  areas; zonal geometry = roster), provider output/save (`roster_values`, `restrict_to_roster`), runtime inputs
  (initialised bundle roster, population, assembly roster) and emitted IDs (tests).

## Tests
`binding-tests-run1.log`: `tests/cloud/test_ipcch_*.py tests/cloud/test_delivery_request_v2.py
tests/test_population_output.py` 127 passed, rc 0 (exact-lock interpreter). New: `test_ipcch_binding.py` (10):
package re-hash/unlisted; real requires accepted + refuses another package with the same 527 schema; finalized vs draft
entries and stale re-finalized entries; real store initialises only the bound bundle (identical-bytes copy = same
bundle; consistent different bundle refused with zero writes; another combination refused for read/initialise; smoke
binding cannot read the real store); fixture/real bundle refusals and mismatched store acceptance records; R48
forbidden-read spy (builtins/io/os open, stat, listdir, scandir) over smoke envelope/package verification, fixture
initialisation, assembly-input and population reads: zero touches of the real bundle; population no-future builder;
geometry declared-extra filter feeding `native_geometries`; provider-output restriction. Climate: undeclared extra
fails / declared dropped (monthly, seasonal, EE monthly); seasonal rain paint graph unfiltered vs reduction filtered to
requested codes and emitted ids == requested roster areas.

## Real-asset evidence (`binding_check_real.py` -> `binding-check-real.json`, rc 0; runs 1-2 failed logs kept)
- Candidate envelope v1 (create-only) `R/scratch/h2h8h14-final/envelope/ipcch-combination-envelope-v1-candidate.json`,
  sha256 e0ad66a217eb94c78a9b0192aaea1ec4831e65cee9757eea9a5c9aacd461e88f: package 18b91d45..., feature order sha
  0ef1ffec..., handoff manifest e6e3ebc6..., roster 9ff2c420... (6226), draft entries 3621c350... (information only),
  status candidate, acceptor/accepted_at null. Package and bundle bytes untouched.
- Smoke verify OK without resolving the handoff; bundle digests == envelope (4/4); real refuses the candidate envelope;
  finalized-entries check refuses the draft entries; an accepted envelope cannot be built on draft entries.
- Population (43,889 rows, 6,226 areas, 2014-01..2026-04): O=2026-10 and 2026-08 -> 6,226 rows = roster, all carried
  forward from <= 2026-04, 0 future rows; O=2026-04 -> 2,774 observed / 3,452 carried. Early origins before an area's
  first reference period are refused (latest first period 2026-02), never back-filled.
- Geometry: 6,227 features -> 6,226 in roster order, dropped declared [1315]; `native_geometries` == roster.

## Remaining for CP2 acceptance (research-side act, awaiting Supervisor checkpoint)
Finalize acceptance_entries.json (acceptor/date) as a new versioned file, build accepted envelope v2 binding its digest,
then real `install_acceptance` + `initialise` dry run on a local store.
