# URI and capacity checkpoint — 2026-10-16

Read-only scouts inspected native implementation at `5003e4f`, snapshot r1 and the active SQL rehearsal. Dynamic counts below describe those snapshots, not cloud acceptance. No cloud calls, imports or credential reads occurred. Native root is `/home/swl007007/projects/food-crisis-research`; `C` is its `control-plane`, `S` its `sources/Food_Crisis_Cluster/IPCCHMLflow`.

## URI mapping and features

- Snapshot r1: all 6 experiment artifact locations, 679 run artifact URIs, 242 logged-model artifact locations and 242 version storage locations use `mlflow-artifacts:/`; 242 version sources use `models:/`. Preserving IDs and the relative artifact tree should preserve these standard links; prove it through the staging service rather than rewriting them indiscriminately.
- `card.feature_list`: 172 tags, of which 56 contain the local artifact root (42 distinct specs in five `source.tar` files) and 116 use `runs:/`. No mapped feature-list tag exists yet. Local references span six forecast families; the largest archive is 130,211,840 bytes.
- The scout resolved all 172 existing feature specs locally using the existing reader: zero errors and zero `n_features` discrepancies. This is a count baseline, not yet a saved ordered-name or remote-download acceptance record.
- `S/ipcch_model.py:141-165` reads only the original tag; `!member` handling is inside its local-path branch. Mapping directly to `runs:/...source.tar!member` would incorrectly download a filename containing `!member`. `mlflow-artifacts:/` also is not handled by this reader. Preserve labels, block order, member names and `#column?filter` selectors exactly.
- Reuse `read_columns` (`S/ipcch_model.py:116-138`) and the installed MLflow artifact downloader. Add only the mapped-reference preference, remote archive handling and actual cloud command installation. `C/research_cloud/service/assistant_patch.py:52-55` permits `ipcch-model features`, but the native service command and `service/ipcch_model.py` were absent at inspection. `S/manage.sh:64-66` is the original installer.
- Acceptance: retain original tags unchanged; bind all 56 mapped references; leave 116 existing refs unchanged; repeat mapping without drift; compare all 172 complete ordered feature lists through authenticated download with the old root unavailable. Cover gzip, multi-block selectors, archive-member failure and the largest archive. Verify standard `runs:/`, logged-model `models:/`, registered-version `models:/` and `mlflow-artifacts:/` downloads against original bytes.
- `S/summary_catalog.py:87-98` remains local-file based but is not called by the feature CLI. Adapt only if cloud catalog rebuilding actually uses it.

## SQL/PostGIS coverage and capacity

- At 09:18:33 UTC, `scratch/sqlimport/report.json` held 40 `verified` entries and no current failures. Aggregate input bytes 2,741,350,328; main-table total bytes 2,199,945,216; heap bytes 2,152,833,024; rows 2,053,436. This partial report had neither terminal `reconciliation` nor `database_bytes`.
- `load_inputs.expected_entries` selects 53 distinct CSV paths totaling 13,763,421,380 source bytes. Wait for the current complete reconciliation; old `run.log` and `report-stopped-643d1a4.json` results are superseded and must not supply the quote.
- The input inventory also declares three shapefile bundles: FEWS geometry, IPCCH original geometry and IPCCH repaired geometry, with all associated files. No PostGIS importer/roundtrip receipt was found at this checkpoint; CSV verification and an installed extension do not establish geometry migration.
- Main-table `total_bytes` includes its index/TOAST but omits standalone irregular-row side tables and the column catalog. Final `pg_database_size(research)` still excludes the separate `mlflow` and `mlflow_auth` databases. Record all three databases and relation/index/TOAST totals after complete CSV and geometry import.
- Source key profiles cover 26 of 53 CSVs; 27 of the current 40 receipts had `keys:null`. Reconcile key-contract applicability and explicitly mark gaps; full cell preservation alone does not prove uniqueness semantics, nor should migration invent deduplication rules.
- The FEWS outcome irregular row is preserved in its side table (source line 302949, content `System.IO.MemoryStream`); retain it and its original disclosure.
- The 20 GiB candidate is conditional on measured capacity. Include actual spatial-index size, currently observed WAL/temporary requirements and explicit headroom; distinguish client disk-backed readback from server temp. A past peak cannot be reconstructed from final DB size. Do not rerun unchanged full imports solely to manufacture a peak; use remaining work and conservative documented allowances.

These are remaining scoped implementation/acceptance items, not authorization to broaden data migration, change scientific keys or repeat completed store-copy checks.
