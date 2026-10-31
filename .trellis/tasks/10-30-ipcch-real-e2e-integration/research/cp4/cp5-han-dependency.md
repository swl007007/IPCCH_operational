# CP5 actual han-sandbox / external dependency use (code trace at 115798f; no cloud call)

**Probe result (Supervisor, execution `ipcch-v2-runtime-preflight-20261031-7jq5m`, exit 2):**
- `ee.Initialize` succeeds under `monthly-runtime`.
- GCS object get, create, delete and list are granted on the data and request buckets.
- `getAsset` on both han-sandbox assets (admin FC, PRCP baseline) is refused.

**CP5 inputs:**
- M = 2026-10, so O = M-2 = 2026-08. M is fixed at the freeze instant and persisted.
- The accepted handoff retains, through O:
  - climate monthly and seasonal: no gaps;
  - nightlight: coverage end 2026-08.
- GPP coverage ends 2025-12; 2026-01..08 are unpublished upstream.
- Source: the 10-29 real-integration run at the same M/O, `archive/2026-10/10-29-ipcch-validity-feature-inference/research/cp3/real-integration/run2-result.json`:
  - `climate_provider_calls=[]`;
  - `gaps.climate_* = {}`;
  - `gaps.nightlight = []`;
  - `GPP_unpublished` = 2026-01..08;
  - 8 GPP HEAD probes, all 404.

## Provider construction: `ipcch_generation` true, so `entrypoint_v2.context` → `real_providers` (`entrypoint_v2.py:98-127`)

| Call | External access | han read? |
|---|---|---|
| `ee_transport.from_environment` | `storage.Client()`, `ee.Initialize(project=feisty-flames-511718-d4)` | no (probe: OK) |
| `CloudSourceAcquirer(...)` (`prepare.py:576`) | none at construction | no |
| `TableProducer(...)` `__post_init__` | regex checks of `producer_asset_root` only | no |

## First use: the `climate` step (`generation.py:200-202`) calls `climate_providers(windows, O)`

1. **`TableProducer.run`** (`table_producers.py:465-480`).
   - `demand()` reads the RETAINED VersionedTables from GCS for `evi_anom`, `spi03` and `spei03`, monthly and seasonal.
   - With nothing unsaved through O, `jobs == []`, and it returns `skipped` BEFORE any EE call.
   - The han admin polygons (`missing_assets(self.inputs.admins())`) and every export are reached only when `jobs` is non-empty.
2. **`climate_run.real_providers`** (`climate_run.py:97-121`) constructs the provider objects. It does no I/O.
3. **`climate_run.update_all`** calls `fetch` / `fetch_season` only for unsaved months or area-season keys.
   - Every `missing_assets` call on han refs (admin FCs, STAGE2A/2B/2D baselines, tables) is inside `fetch*`:
     - `climate_ee.py:455`;
     - `climate_ee_seasonal.py:481`;
     - `climate_tables.py:288/341/382/496`.
   - With empty gaps, none is called.

## Other sources in CP5

- **GPP:** `gpp.update_gpp` uses public HTTPS HEAD/GET to `data.globalecology.unh.edu` for 2026-01..08. That is internet egress from Cloud Run, with no han and no EE.
  - If a month is published by run time, it is downloaded and zonal-stated in the job. That is a real acquisition and is recorded as such.
- **Nightlight:** retained through 2026-08, so no acquisition is expected.
- **ACLED** (refresh, uploaded file), **WFP and research families** (keep), and **history_snapshot** (keep) are all GCS pins only.
- **FEWS member:** inherited literally from current; no FEWS scoring in the v2 run.

## Conclusion

- **Expected han-sandbox reads in this CP5: none.** CP5 readiness rests on `ee.Initialize` and GCS, which the identity probe PROVED.
- **Public HTTPS egress is NOT yet proven** under the Cloud Run runtime. The identity probe covered only EE initialization and GCS. The GPP HEAD probes in the run are the first evidence; record their actual result.
- **The runtime SA's han read access is CONFIRMED DENIED** by the identity probe (`ipcch-v2-runtime-preflight-20261031-7jq5m`). `getAsset` was refused for both the admin FC and the PRCP baseline. han read is required at the first unsaved climate or table period:
  - DA1/DA2: first natural O = 2026-09, at M = 2026-11;
  - any run whose demand is non-empty.

  There it fails closed:
  - `TableProducer`: "unreadable producer input polygons";
  - climate fetch: `missing_assets` / `EETransportError` "exists but is not readable".

  It does so before any export, and nothing is published. Future DA permissions stay an explicit open item. Per the Supervisor, there is no IAM widening in this round.
- **The C sequence must finish, and the CP5 freeze must happen, before 2026-11-01T00:00:00Z.** The freeze instant fixes M:
  - a freeze at or after midnight UTC gives M = 2026-11 and O = 2026-09;
  - that makes the demand non-empty, which needs han, so the run fails closed.

  A run frozen before midnight keeps M = 2026-10 even if it executes past midnight. Today 13:58Z leaves about 10 h; the C estimate is about 2.5 h.
- **Residual uncertainty.** The no-gap expectation is the 10-29 local replay at the same M/O over the same accepted handoff. The live retained store is initialised from that same handoff (`initialise --mode real`, same manifest), so the same demand is expected.
  - The run's own report (`climate_provider_calls`, `production.skipped`, per-source acquisition versus retained reuse, R5) is the actual evidence.
  - A non-empty demand would stop the run fail-closed; it would not be treated as success.

## Line evidence: no eager han read (verified after the Supervisor's 2026-10-31 user-EE probe)

**Construction does no I/O on han.**
- Dataclass providers have no `__init__` I/O:
  - `MonthlyEEProvider` (`climate_ee.py:421-427`) and `SeasonalEEProvider` (`climate_ee_seasonal.py:437-445`);
  - `VegetationProvider` (`climate_tables.py:269-275`; reads lazily in `_read`, `:277-280`) and `DroughtProvider` (`:370-376`);
  - `TableRefs.__post_init__` (`climate_tables.py:88-95`) checks only the in-memory `produced` mapping.
- `ClimateProviders.monthly` / `seasonal` (`climate_run.py:31-44`) only return bound fetch callables.

**Fetch happens only for unsaved periods.**
- `update_monthly` → `_monthly_loop` calls `fetch(src, month)` only `for month in months_to_update(saved, origin)` (`climate.py:287-289`).
- `update_seasonal` calls fetch only for `pending_seasons(table, windows, origin)` (`climate.py:368, 382`).

**Producer.** `TableProducer.run` (`table_producers.py:465-476`):
- `demand()` reads only the retained GCS VersionedTables (`:313-324`);
- `if not jobs: return` (skipped) at `:472-474`, BEFORE `missing_assets(self.inputs.admins())` at `:476`.

**Geometry** for the zonal sources (GPP/nightlight) comes from the installed bundle's fixed shapefile: `geography.roster_geometries(bundle_dir, …)` (`geography.py:85-93`; `generation.py:203`). It is not EE and not han.

**Result (Supervisor-accepted 2026-10-31 after direct checks).** A retained-only M=2026-10 CP5 is not gated by han access. Public HTTPS (GPP) under Cloud Run stays unproven until the run's actual GPP probe results are recorded.
- The user-credential readability that the Supervisor probed (getAsset OK, getAssetAcl denied) is NOT used by the runtime, and must not be deployed.
- The runtime SA's han read, CONFIRMED DENIED, is the separate future DA1/DA2 access gap: ownership-based sharing by the upstream owner, or an owner-approved copy. Out of this round.
