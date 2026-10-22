# Local inheritance and activation paths, 2026-10-22

Two bounded read-only exploration agents reported the facts below; the supervisor sampled the referenced fallback README/download receipt, normal project config and destination binding. This is discovery, not candidate acceptance, member-hash validation or a replay. No network request or inference was performed.

## Accepted local source archive

`cloud_pipeline/fallback/october_2026/webapp_model_bundle.tar.gz` is present, 401337529 bytes. The exploration agent independently obtained SHA256 `ac3bfceab55274d0feaad5395d16298fbf84e7baf9ffccb67fcca3d23327b4d9`, equal to the pinned GCS object generation `1791584164926460`. Streaming tar inspection found 195 files: every one of the 194 `portable:true` manifest members plus `manifest.json`; no missing portable member or size mismatch.

- IPCCH: 15 result tables; 23 model-package files; `inputs/ipcch_origin_rows.csv`; nine diagnostic evidence CSVs; `ipcch/polygons.geojson` and `ipcch/country_population_reference.csv`; assembly/declarations/availability/fill-audit reports.
- `reports/ipcch_feature_fill_audit.csv` is in the archive (657769905 bytes), though omitted from the compact loose download. The archive geometry prefix is `ipcch/`; the compact folder uses `shared/ipcch/`.
- `inputs/ipcch_base_series.csv` is explicitly `portable:false` and absent. The accepted portable source does not contain all historical working panels; use its frozen origin input and retain required history separately for the baseline.
- Individual archive-member hashes and copied byte equality remain to be checked during inheritance. Do not rerun IPCCH inference to verify inheritance.

References: fallback `README.md:3-14`, `replay_evidence/download.json:10-14,38-42,57-60`, `manifest.json:408-459,516-531,534-672,732-753,1272-1419`.

## Actual normal-operation state

`/home/swl007007/ipcch-operator/food-crisis-test/project.json` uses `work_dir=operator-state`, relative to the config directory. Its initialized state is `/home/swl007007/ipcch-operator/food-crisis-test/operator-state/initialized.json`, with baseline `95111230975434f14258eac6c46a2525f527e7ee8ad8c1e14eb22033115d9884` and original image digest `7e6133f32ab0b28d3f29b827d4153975e99f97d440e97a1a8cdacdfa1052f0d0`.

Selected FEWS slots are `local-202604-57cb3b981198-510375f58cd8/{0m,6m,12m}`; IPCCH slots are `launch_2026_04_production_safe/scope_{0m,6m,12m}`. `pipeline.py::destination/load_initialized` binds project/buckets/image/namespace and rejects mismatches. `models select` updates only the chosen work directory. `run` consumes those selections; `download` does not activate them. Candidate model selection alone is not promotion of normal-operation defaults.

The active documented fallback is `cloud_pipeline/fallback/october_2026/`. The inspected operator has no fallback-directory selector or automatic failover action; switching this directory/documentation/inventory is a separate local activation. Preserve its confidence-bearing predecessor as specified. The external accepted release remains in `manuel-remote-sensing-oct-delivery-debug/oct-staging`; it is not a previous pointer in the production project's `monthly-staging` namespace.

References: `pipeline.py:59-88,507-529,628-647,708-724,781-818,868-922`; `cloud/orchestrator/delivery_job.py:170-219`; `cloud/orchestrator/delivery_scoring.py:119-139`; fallback `replay_evidence/cloud_run.json:43-46`.

All mutable config/pointer/runtime identities must be freshly checked and saved before maintenance or promotion. These local observations do not establish live cloud state or AC6/AC7/AC9 completion.

## Supervisor follow-up verification

At 05:26:48Z the supervisor independently streamed the archive and hashed every file against the accepted manifest, including the manifest itself: **195/195 checked, zero missing/hash/size errors**. The whole archive SHA also matches the pinned identity; file size/mtime were unchanged across verification. Receipt: `supervisor-source-bundle-verification.json`. This resolves source archive-member integrity only. Candidate copying and new-image compatibility are still pending, and no inference was performed.
