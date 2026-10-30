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

## R48 fix (Supervisor finding on e3a438b: verify_fixture_bundle read the bundle before the fixture check)
- Smoke bindings now carry a declared `fixture_root` (`verify_combination(..., mode="smoke", fixture_root=...)`; real
  takes none). `admit_fixture_dir` decides admission LEXICALLY (abspath/normpath, no filesystem call) before any access:
  a bundle outside the fixture root - e.g. a misrouted real handoff bundle, including `..` paths - is refused unread.
- `fixture_file` then lstat-checks each path component from the fixture root down (only paths inside the root) and
  refuses symlinks, so no read can leave the root; `verify_fixture_bundle` reads the manifest, checks the fixture marker
  and schema BEFORE any payload, then the roster; `initialise` (smoke) admits every runtime file the same way first.
- Tests: misrouted real bundle through `verify_fixture_bundle` and `initialise` (plus a `..` path) with the
  open/io.open/os.open/stat/lstat/listdir/scandir spy -> zero touches; a non-fixture bundle inside the root -> refused
  by marker; symlinked bundle dir / symlinked manifest -> refused, never opened. Mutation check: restoring the pre-fix
  order (handoff_identity first) makes the spy test fail (1 failed). Regression `binding-r48-fix-tests-run1.log`:
  test_ipcch_*.py + request_v2 + population_output 138 passed rc 0.

## Acceptance publication packet (prepared; the acceptance itself awaits the Supervisor's explicit act)
Tool `cloud_pipeline/tools/ipcch_finalize_acceptance.py` (inputs: acceptor, YYYY-MM-DD date, envelope version):
checks the r5 manifest sha (e6e3ebc6...) and that the draft entries list exactly the runtime files at manifest sha;
creates a NEW bundle dir (manifest-listed files + unchanged handoff_manifest.json hard-linked byte-for-byte), writes
finalized entries fresh (draft file untouched), writes the accepted envelope create-only, and verifies it exactly as
real mode does (verify_combination real + verify_handoff).

Proposed real command (acceptor/date to be supplied at acceptance):
`python tools/ipcch_finalize_acceptance.py --package R/scratch/h2h8h14-final/package-build/out-r1/package
 --bundle R/scratch/h2h8h14-final/handoff-build/out-r5 --expect-manifest-sha256 e6e3ebc60ad816bda4580cf3cef65258ba1cb708a4766d9f4d76fbd13f5c97b4
 --out-bundle R/scratch/h2h8h14-final/handoff-build/out-r5-accepted-v1
 --envelope R/scratch/h2h8h14-final/envelope/ipcch-combination-envelope-v2-accepted.json --envelope-version 2
 --acceptor "<acceptor>" --accepted-at <YYYY-MM-DD>`

DRY RUN on the actual assets (`acceptance_dryrun.py` -> `acceptance-dryrun.json`, rc 0, 127 s; output dir
R/scratch/h2h8h14-final/envelope/DRYRUN-NOT-ACCEPTANCE, acceptor "DRY-RUN (not an acceptance)"): accepted dry-run
envelope v2 sha eede3061... binds package 18b91d45..., feature order 0ef1ffec..., handoff manifest e6e3ebc6...
(unchanged), roster 9ff2c420.../6226, finalized entries 4a1e94b4... (57). Real-mode `install_acceptance` appended 57
records; `initialise` 52 tables + 5 geometry files verified, pairing recorded; re-initialise 52 unchanged;
`read_assembly_inputs` roster 6226, order 527 == package; `read_population(2026-08)` 6226 rows, all carried forward
<= 2026-04. The ORIGINAL r5 (draft entries) is refused for that binding; its draft digest 3621c350... is unchanged.

## R48 residual (Supervisor review of 89b0e02): symlinked fixture root
`fixture_file` now lstat-checks the declared fixture root ITSELF (must be a real directory, not a symlink) before any
child lstat or open. Regression `test_smoke_refuses_a_symlinked_fixture_root`: fixture_root -> real bundle symlink,
through `verify_fixture_bundle` and `initialise`: refused, zero `open` calls and zero spy touches of the real bundle.
Targeted: test_ipcch_binding.py + test_ipcch_initial.py 21 passed.
