# Local SQL/PostGIS rehearsal and capacity (native `f93bfa1`)

These are disposable-PG rehearsal results: PostgreSQL 16 with PostGIS 3.5.0 at `scratch/pg-rehearsal`. Nothing here is a cloud import or a provisioning receipt.

## CSV inputs: `csv-import-report.json` (load_inputs, code 8868583, run3)

- **Reconciliation:** 53 expected and 53 verified. The stale_receipt, failed, not_imported and verified_but_table_absent lists are all empty.
- **Verification:** every cell is compared, with floats exact and NULL positions exact. Source bytes total 13,763,421,380.
- **Irregular row:** the single FEWS outcome irregular row is preserved in `fewsnet.outcome_ea382f78__irregular_rows` (source row 302949, `System.IO.MemoryStream`).
- **Key-profile coverage:** 26 of 53 tables have a source key profile, and all 26 agree with it exactly (`agrees_with_profile`). The source key anomalies are preserved, not deduplicated:
  - `fewsnet.extension_component_2025_combined` (`FEWSNET_admin_code`, `date`): 2 duplicate rows in SQL, as in the profile;
  - `fewsnet.outcome` (`admin_code`, `year`, `month`): 1 null-key row, kept in the irregular side table, as in the profile.

  The other 24 profiled tables have 0 duplicates and 0 null/empty keys. The 27 unprofiled tables are row- and cell-verified only, with no key semantics invented:
  - fewsnet.coordinates, ipcch.country_lookup, ipcch.region_mapping, ipcch.reference_coordinates_source, ipcch.saved_country_lookup, ipcch.saved_reference_coordinates;
  - ipcch.model_ready.expected_feature_contract/expected_run_index;
  - origin_safe_climate_idp_v1 cohort_keys plus history/idp ledgers (h0/h3/h6/h12);
  - origin_safe_weather_oracle_v1 oracle ledgers (h3/h6/h12);
  - compact_climate_weather_oracle_v1 oracle ledgers (h3/h6/h12) and season ledgers (h0/h3/h6/h12).

## Geometry bundles: `geometry/` (load_geometry, code c1dc977 + e280fde)

| Bundle | Table | Rows | Attributes | SRID | WKB | Invalid (recorded, not repaired) | Total bytes (GiST) |
|---|---|---|---|---|---|---|---|
| ipcch.geometry_repaired | ipcch.geometry_repaired_shp_36cba6d5 | 6,227 | 4 | 4326 | byte-equal | 0 | 69,722,112 (425,984) |
| ipcch.geometry_source | ipcch.geometry_source_shp_68bca802 | 6,227 | 3 | 4326 | byte-equal | 253 | 71,688,192 (425,984) |
| fewsnet.geometry | fewsnet.geometry_shp_45c0b03c | 5,718 | 16 | 4326 | byte-equal | 1 | 104,267,776 (409,600) |

- **Source reading:** every shapefile member's sha256 equals the task input inventory (`export-*.json` `members`; inventory sha `26b3f757…`). The `.shp` is read with `geopandas.read_file` in file order.
- **SRID:** taken from the reader's exact EPSG. The FEWS `.prj` is an ESRI `GCS_WGS_1984` + `VERTCS`. pyproj alone finds no exact code for it; the reader reports EPSG:4326. The `.prj` text is kept verbatim.
- **Receipts:** each binds `export_json_sha256`, the inventory sha256 and `rows_sha256`.
- **FEWS readback hash:** `readback_sha256` differs from `rows_sha256` for FEWS. Only the lexical float format of `AREA1`/`AREA2` differs (59 values each); the typed values are equal. Acceptance is typed equality plus byte-equal WKB, not whole-TSV byte equality.
- **Logs:** full export and load logs are kept, and the exit codes are all 0 (`exit-codes.txt`).
- **Rehearsal metadata reset (recorded):** before the identity-bound reload, the 8-column rehearsal `public._geometry_bundles` was deliberately dropped (`DROP TABLE public._geometry_bundles`). The amended loader creates it with 10 columns. Had it not been reset, the 10-value INSERT would have failed inside the transaction and rolled back.
- **Superseded evidence:** the first-round receipts are kept, not deleted, at `scratch/geometry/superseded-0559/`.
- **Tests:** 6 tests on a throwaway PostGIS DB: round trip, rollback, and tampered rows refused before DDL.

## Capacity: `capacity.json` (capacity.py, read-only, 06:06 EDT)

| Database | Bytes |
|---|---|
| research | 11,579,519,459 |
| mlflow (copied tracking store) | 203,297,251 |
| mlflow_auth | 8,294,883 |
| **Sum** | **11,791,111,593 (10.98 GiB)** |

Disposable `svc_*`, `ws_*` and `wsc_*` rehearsal databases are excluded.

**research breakdown:**

| Group | Bytes |
|---|---|
| ipcch tables (48) | 9,499,910,144, of which indexes 122,912,768 |
| fewsnet tables (5) | 1,790,492,672 |
| geometry tables (3) | 245,678,080; TOAST 214,122,496; GiST 1,261,568 |
| side table | 32,768 |
| catalogs | 10,747,904 |
| non-relation | 32,657,891 |

The largest relation is `ipcch.interim_b19556da` at 1,797,226,496 bytes.

- **WAL:** `pg_wal` is 1,023,410,176 bytes now. `max_wal_size` (1 GB) is a checkpoint target, not a hard cap; WAL can exceed it under load.
- **Server temp:** `research` shows 103 temp files and 4,671,954,944 bytes cumulative since cluster creation, across all import runs and readback sorts. This is not a peak and cannot be reconstructed from it.
- **Client-side readback temp** (load_inputs `COPY ... TO` tempfile on the importing host) is importer disk, not Cloud SQL disk, and is excluded.
- **Sizing (conservative allowances, no import re-run):**

  | Component | GiB |
  |---|---|
  | Data | 10.98 |
  | WAL allowance (max_wal_size target; WAL can exceed it under load) | 1.0 |
  | Temp allowance (assumption: one sort the size of the largest relation; not a measured peak) | 1.67 |
  | **Total** | **≈ 13.65** |

  - 20 GiB would leave ≈ 6.3 GiB (32%), and each further immutable IPCCH panel version adds ≈ 1.6 GB.
  - **The quote carries 30 GiB SSD (+USD 1.70/month vs 20 GiB, platform envelope)**: ≈ 16.3 GiB headroom, with no automatic storage increase (it cannot be shrunk).
