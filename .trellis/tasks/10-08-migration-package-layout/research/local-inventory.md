# Local inventory (2026-10-08)

Read-only inspection; no cloud calls and no historical lineage research. Windows Python/Git were used because WSL/DrvFS reads intermittently fail with EIO. Two delegated inventory agents failed at model capacity; their results were not used.

## Existing delivery directories (initial inventory; cleanup policy revised below)

| Source | Files | Size (MiB) | Proposed destination |
|---|---:|---:|---|
| Outcome/model_delivery/202609_h5/20260909_refresh_v1 | 134 | 4502.44 | Outcome/manual_delivery/202609_h5/20260909_refresh_v1 |
| Outcome/model_delivery/202609_h5/20260909_refresh_v1_superseded_civ_mapping | 24 | 2669.55 | Outcome/manual_delivery/202609_h5/20260909_refresh_v1_superseded_civ_mapping |
| Outcome/model_delivery/202609_h5/20260911_training_confidence_v2 | 154 | 4515.67 | Outcome/manual_delivery/202609_h5/20260911_training_confidence_v2 |
| Outcome/model_delivery/202609_h5/20260923_country_confidence_v3 | 173 | 4536.57 | Outcome/manual_delivery/202609_h5/20260923_country_confidence_v3 |
| Outcome/model_delivery/october_cloud_delivery/oct-final-20261008a | 48 | 757.14 | unchanged |

Counts include all existing versions, including the superseded mapping variant. Initial proposal was to preserve them all; superseded by the user-authorized backup cleanup below. The four manual trees total 485 files / approximately 15.8 GiB. Generated delivery trees are ignored by .gitignore:47-48; the new destination needs equivalent explicit treatment.

Active reference: tests/cloud/test_delivery_outputs.py:8 uses the September v3 directory; its skip guard at line 9 means an uncorrected move could silently skip parity tests. Historical plans under docs/superpowers refer to original paths and should retain their historical wording, with a relocation index explaining the new location.

## Reusable local migration inputs

- deploy/october_delivery/build_context.sh:6-8 already stages cloud, fewsnet_partitioned_rf_pipeline, model_pipeline, tools, the Dockerfile, and the lock file. Reuse its scope rather than copying the whole repository.
- deploy/october_delivery/Dockerfile:3-17 defines the frozen Python runtime and prepare entrypoints.
- /tmp/oct-full-assets contains full FEWSNET/IPCCH geometry, rosters, and 9 remote-family history CSVs, approximately 528 MiB total. These must become durable package members, not /tmp dependencies.
- /tmp/oct-staging-oct-final-20261008a/downloads contains the exact FEWSNET refreshed raw panel (~740 MiB) and IPCCH history panel (~1700 MiB), plus the frozen inputs manifest and small model schema/report files.
- /tmp/oct-staging-oct-final-20261008a/run_manifest.json records consumed inputs. Use it only as a mapping/checksum reference, not as a destination request.
- September v3 inputs and the October final delivery provide additional fixed panels and population reference files. Verify the selected bytes against the consumed references during packaging; no reconstruction or historical tracing.
- Outcome/model_delivery/october_cloud_delivery/oct-final-20261008a/webapp_model_bundle.tar.gz is 395497758 bytes. Its members include accepted FEWSNET 0/6/12 packages, IPCCH scope packages, geometry, reference CSVs, runtime, frozen inference rows, and final scope tables.
- The existing replay bundle does NOT include the complete raw history panels and remote extraction history needed for future preparation. It is not by itself a full cloud migration package.

## Configuration gaps to fix within migration scope

Archived request makers under .trellis/tasks/archive/2026-10/10-07-october-cloud-delivery/research/cp3_evidence/cloud_final_replay/ use the old project/bucket and require a .trellis ancestor (oct-make-request.py:4,9-10; oct-make-final-request.py:11,18,22,25-28). Ship supported destination-configurable entrypoints beside deploy/october_delivery, reusing current request contracts. Preserve archived originals as historical evidence.

The delivery deployment script accepts explicit destination variables but is not an infrastructure bootstrap. Source image URI/environment bindings and nested object references must be regenerated after upload. Old GCS generations are reference evidence only.

Root README.md:3-5 still describes prediction as a later step, and lines 19-165 describe the earlier EVI/Vertex path. Put the current October delivery/migration entry first and label retained older instructions clearly.

## User-authorized cleanup revision

The user asked why the data was so large, confirmed offline replay had already been verified, and authorized deleting backups. This supersedes the initial preserve-all proposal.

Each complete manual version holds approximately 3189 MiB of inputs, including ipcch_panel.csv (~1700 MiB), fewsnet_refreshed_raw.csv (~740 MiB), and fewsnet_panel.csv (~740 MiB). Expanded geometries add roughly 955 MiB. These dominate the 15.8 GiB total, not the accepted compressed delivery itself.

The final v3 archive is 240305152 bytes (~229 MiB), with 165 file members (~1090 MiB expanded). Its inputs contain fewsnet_april_features.csv, fewsnet_identity_population.csv, and ipcch_april_panel.csv; it does NOT contain the full raw history panels. Those must be preserved separately for cloud migration before removing redundant manual copies.

A compact v3 handoff retaining the archive, final/reference CSVs, small metadata, ipcch_april_panel.csv and ipcch_four_target_training_replay.csv is approximately 250 MiB. The last report is 10059255 bytes and used at tests/cloud/test_delivery_outputs.py:214. Expected cleanup savings are roughly 15.6 GiB. No rerun of the accepted offline replay is needed.
