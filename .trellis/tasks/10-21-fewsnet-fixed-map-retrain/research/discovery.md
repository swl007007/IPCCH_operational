# Discovery record

Planning observations from 2026-10-21 with final-grill additions on 2026-10-22. Cloud observations below were obtained earlier in this conversation; final-grill network reads queried public HDX and its registered official download URLs only. Reconcile mutable state before execution. Nigeria/Somalia CS contents were sampled online; full-country label coverage and current remote-provider publications remain unverified.

## Operational identities

- Map: `cloud_pipeline/fewsnet_partitioned_rf_pipeline/assets/partitions/cluster_mapping_k40_nc17_general_refined_contig3.csv`; SHA256 `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`; 5,365 mapped areas, 17 partitions, separate from the 5,718-area prediction roster.
- Feature contract: `cloud_pipeline/fewsnet_partitioned_rf_pipeline/assets/feature_contracts/fewsnet_stage3_v1.json`; file SHA256 `3779c6bcde70560c0e1514c563ced6e7bd559c6d352689398c3cecb93d44a67b`; its 123-feature schema SHA256 is `6e6f0bdc2df7bb40ec37f2d44926d2a24fbb746bc5272ed9b93a7ae4047d891b`. These are different kinds of hashes.
- Lock: `cloud_pipeline/requirements.lock.txt`; SHA256 `2f0a7251e0436d900ddb91d0a783421b205094ffdb26ba52ccbdfb7f9bb31e3d`. Operational versions: Python 3.12.3, NumPy 2.4.2, pandas 3.0.0, scikit-learn 1.8.0, imbalanced-learn 0.14.0, joblib 1.5.3, SciPy 1.17.0.
- Production: `feisty-flames-511718-d4`, configuration `food-crisis-test`, region `us-central1`; jobs `oct-delivery` / `monthly-prepare`; data bucket `food-crisis-test-ipcch-data`, requests bucket `food-crisis-test-ipcch-requests`, namespace `monthly-staging`.
- Approved Cloud Run read returned image `us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime@sha256:7e6133f32ab0b28d3f29b827d4153975e99f97d440e97a1a8cdacdfa1052f0d0`.
- Operator config: `/home/swl007007/ipcch-operator/food-crisis-test/project.json`. Prior model slots: FEWS `local-202604-57cb3b981198-510375f58cd8/{0m,6m,12m}`; IPCCH `launch_2026_04_production_safe/scope_{0m,6m,12m}`.

## Candidate source data

Actual research root is `/home/swl007007/projects/food-crisis-research`; its integration checkout is `control-plane/research_cloud/`. Research image/source snapshots are provenance, not editable operational runtime copies. The research FEWS adapter is pooled four-class XGBoost and is unsuitable for this binary RF refit.

Let `S=/home/swl007007/projects/food-crisis-research/staging/ipcch-update-202610`.

- Local assembled FEWS inputs reach 2026-04, labels 2026-02. Outcome source directory: `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/Outcome/FEWSNET_IPC`. `scrape_fewsnet.py` uses `https://fdw.fews.net/api/ipcphase.geojson` with an old end date. `append_2025_2026.ipynb` discards identifiers/geometry before a name-only merge and uses a binary expression that can convert missing labels to zero. This is a candidate-ingestion risk, not proven contamination of production. No verified reusable fnid-to-production-code crosswalk was found.
- WFP: `S/sources/wfp_price/raw/hdx_2026-10-19/`, annual 2009-2026 raw CSVs plus market/commodity files. IPCCH processed columns differ from FEWS definitions.
- ACLED: `S/sources/acled/NOTES.md`; the October 19 fetch ended at 2025-10-19, so 2025-09 was its latest complete month. This is account-lag evidence, not a guaranteed current API cutoff.
- GOSIF: `S/sources/gosif_gpp/NOTES.md`; raw 2025 v3 means are locally available. v2/v3 differences are material and month-dependent; no simple correction is justified. Processed IPCCH output is not FEWS geometry.
- Research GCS FEWS migration inputs end in 2024-10 and an extension in 2025-06; their October 2026 upload dates do not make them current observations.

## Pinned FEWS remote snapshot

Prefix `P=gs://manuel-remote-sensing-oct-delivery-debug/prepared/full-window-20261008c`.
`P/prepared_manifest.json#1791484258622845` reports succeeded, origin 2026-10, availability cutoff `2026-10-08T13:00:00Z`, extraction contract `current-repo-remote-scripts-v1`, and 5,718 areas. The following are saved-snapshot limits, not proof of providers' latest publication.

| File below `P/features/fewsnet/` | Generation | SHA256 | Latest month / areas |
| --- | --- | --- | --- |
| `evi.csv` | 1791478904987964 | 32fbe9676480de1c43e0e8c1cf3446f7350a58cfa7fb9389bdc975329371645d | 2026-08 / 5716 |
| `fldas.csv` | 1791482199705845 | a8a47ff2b7ded7d7de2ff7aab24d5bb7406ecb797674fa8149fd7808034b934e | 2026-08 / 5131 |
| `viirs.csv` | 1791484255798555 | 0ece15a599befcb67c9d7725ec7458696f1013acb8c7fb59c5fe58c862156dec | 2026-08 / 5619 |
| `gosif_mean.csv` | 1791482233587220 | 22fc39cb49e6cb6b8fcb9843a3b3d9b42dedc460dadaf9a12caf3db15ade7ad2 | 2024-12 (v2) / 5494 |

Assets prefix `gs://manuel-remote-sensing-oct-delivery-debug/assets/full-20261008a/fewsnet/`:

- `roster.csv`, generation `1791464483389036`, SHA256 `57c3ffaec68103321bb8da485e86026e1ef0e861db3f6274709fab84bcdfb2ef`.
- `geometry.geojson`, generation `1791464507801287`, SHA256 `4a491eae5f88f99226f57b93542dcb9f527609787fb81059043a9c8721999386`.

## Source-code findings behind the design

Paths below are relative to `cloud_pipeline/`; line numbers are discovery pointers, not immutable code identities.

| Finding | Evidence |
| --- | --- |
| Reusable full fitting primitive and final predictor | `fewsnet_partitioned_rf_pipeline/core/training.py:202,518`; old 36-period constraint at 399 |
| Observed horizon target join and missing-target exclusion | `fewsnet_partitioned_rf_pipeline/core/horizons.py:160,183` |
| Mandatory legacy validation ranges | `fewsnet_partitioned_rf_pipeline/core/validation.py:408`; `local/package.py:308,372,627`; `cloud/orchestrator/delivery_outputs.py:201` |
| Current diagnostic arithmetic must be bypassed | `cloud/orchestrator/delivery_outputs.py:338,550`; supplied country fields supported at 410 |
| Old evidence cannot truthfully be renamed as new package validation | `cloud/orchestrator/delivery_manifest.py:269`; `delivery_outputs.py:229`; `deliver.py:54` |
| Offline diagnostics also recompute today | `cloud/orchestrator/delivery_bundle.py:442` |
| Prepare always processes two systems, even refreshing latest existing month | `cloud/orchestrator/prepare.py:149,206,237,343` |
| Shared provider vintage affects effective remote input clearing | `cloud/orchestrator/delivery_inputs.py:96` |
| Delivery currently accepts one shared prepared snapshot | `cloud/orchestrator/delivery_manifest.py:127`; `delivery_job.py:179,289` |
| Global keep compares retained snapshots with both exact history panels | `cloud/orchestrator/delivery_job.py:222,237` |
| Operator destination binds image; acceptance must match image/runtime | `pipeline.py:234,507,514`; existing per-slot model selection at 821 |

Current-source scouts found the GitNexus index stale; source inspection supplied these pointers. No code was changed and no training, model evaluation or new cloud operation was executed while writing this planning record.

## Second-grill source findings and decisions (recorded 2026-10-22)

The user confirmed manifest-controlled remote update / FEWS inference / IPCCH inference, with this release selecting FEWS inference only. Necessary training/data-building remote additions remain; release-time preparation is skipped. New FEWS weights become the production default. Preserve a complete two-system package by inheriting IPCCH from an accepted same-origin source. Missing/incompatible dependencies stop execution without automatically running skipped steps. Cross-origin inheritance is rejected. These decisions replace the earlier per-system preparation design. The then-current October 21 label-vintage limit was superseded in the final grill below; non-label limits remain unchanged.

Current-source findings (paths below `cloud_pipeline/`):

| Finding | Evidence |
| --- | --- |
| Two existing Cloud Run jobs; preparation submits Batch extraction | `deploy/setup.py:45-81`; `cloud/orchestrator/prepare.py:495-542` |
| Delivery already has a per-system entrypoint but always invokes both | `cloud/orchestrator/delivery_job.py:282-299,375-376,428-430`; `deliver.py:114-130` |
| Operator unconditionally launches/waits for preparation; intent/status need skip semantics | `pipeline.py:634-719,602-603`; CLI at 938 |
| Prepared reference permits a prepare ID distinct from delivery run ID | `cloud/orchestrator/delivery_manifest.py:127-131`; `delivery_job.py:179-200` |
| Six-slot/request exact-key contract must distinguish execution from release contents | `pipeline.py:367-371`; `cloud/orchestrator/delivery_manifest.py:55-72,124-125,242-257` |
| Complete export includes 30 tables and both systems' portable dependencies | `cloud/orchestrator/deliver.py:168-180`; `delivery_bundle.py:124-148,320-346` |
| Existing diagnostics verification and offline replay process both systems | `cloud/orchestrator/delivery_bundle.py:471-539` |
| Existing publication uses one complete release pointer | `cloud/orchestrator/delivery_run.py:98-110`; `pipeline.py:785-817` |
| Old GOSIF source is v2; overlay metadata can erase new panel values | `cloud/batch/remote_sources.py:94-102`; `cloud/orchestrator/delivery_inputs.py:96-115` |

Locally recorded accepted source identities, not newly verified cloud availability:

- Prepared manifest: `gs://manuel-remote-sensing-oct-delivery-debug/prepared/full-window-20261008c/prepared_manifest.json`, generation `1791484258622845`, SHA256 `bb367e21854643ecaf16a0603082c96d331c19233624f36dc076980f0864bcec` (`fallback/october_2026/manifest.json:1430-1434`). This is a historical source, not an assertion that it includes the new training-data additions.
- Complete source bundle: `gs://manuel-remote-sensing-oct-delivery-debug/deliveries/oct-confidence-20261009b/webapp_model_bundle.tar.gz`, generation `1791584164926460`, SHA256 `ac3bfceab55274d0feaad5395d16298fbf84e7baf9ffccb67fcca3d23327b4d9` (`fallback/october_2026/replay_evidence/download.json:10-14`). The compact directory omits some expanded inputs/per-system reports; inherit them from the pinned full archive after verifying members.

This follow-up was read-only source exploration and task-document editing. No cloud calls, model runs or application tests were performed.

## Final-grill confirmations and evidence (2026-10-22)

- HDX is the required discovery/source registry for latest FEWS CS labels. Actual retrieval versions are frozen, replacing the label-specific October 21 availability cutoff; origin October 2026, labels no later than origin and exogenous months no later than September remain. Partial verified-label coverage is acceptable, with gap disclosure after all 22 source-country checks. Zero credible added labels stops fitting.
- Public catalog lookup and three bounded CSV inspections are recorded in `hdx-discovery.json`. HDX-registered Nigeria/Somalia URLs point to official FDW CSVs; their content reaches `2026-06-01`, despite catalog ranges ending `2025-10-31`. Ethiopia exceeded the 12 MB sample-read bound. This is source discovery, not a complete downloaded/frozen training dataset or proof of full-roster alignment.
- The manifest must drive actual cloud Workflow dispatch. A local operator switch or scorer branch alone is insufficient. Keep initial intent immutable and bind its resolved request to real completed preparation evidence.
- Produce a candidate, download/verify it and run FEWS-only relocated replay before promotion. Retain old production/default/fallback until checks pass. Pause other monthly computations while changing shared job/workflow settings; old results remain readable. Reopen after acceptance or verified restoration; no temporary candidate job.

Additional source evidence (paths below `cloud_pipeline/`):

| Finding | Evidence |
| --- | --- |
| Local operator currently launches prepare and uploads delivery only afterward | `pipeline.py:666-718,773-774`; `OPERATIONS.md:104-106` |
| Current Workflow only forwards event URI/generation to delivery | `deploy/workflow.yaml:23-49` |
| Prepare job returns after Batch submission; success snapshot/status are later artifacts | `cloud/orchestrator/prepare.py:495-520,382-398,478-488` |
| Source deployment grants Workflow access to delivery, not the new prepare dispatch path | `deploy/setup.py:82-99` |
| Initial request is create-only and run identity is bound to its complete contents | `pipeline.py:119-122`; `cloud/orchestrator/delivery_run.py:57-64` |
| Existing cloud execution publishes before later relocated replay | `cloud/orchestrator/delivery_job.py:375-389`; `delivery_bundle.py:113-118`; `delivery_run.py:97-110` |
| Current download requires an already succeeded delivery | `pipeline.py:781-817` |
| Model selection changes only its work directory; true normal entrypoint also binds runtime/config | `pipeline.py:507-517,628-642,919-921`; `/home/swl007007/ipcch-operator/food-crisis-test/project.json:7-12` |
| SMOTE has existing fallback; estimator fitting failure propagates | `fewsnet_partitioned_rf_pipeline/core/training.py:217-218,282-298` |
| Existing causal fill is origin-window-specific | `cloud/orchestrator/delivery_inputs.py:433-456` |

No GCP operations, training, application tests or implementation were performed in this final grill. Public resource reads do not establish current cloud IAM, archive accessibility or release readiness.

## Remaining execution discoveries

All-country HDX CS coverage/crosswalk, provider September availability, inherited IPCCH archive accessibility/completeness, refreshed inference snapshot identity, fitting row counts/ranges, actual Workflow permissions and candidate/promotion/runtime identities remain to be verified or produced. Record them during implementation. These are execution evidence under the settled contract, not assumed successes or reasons to reopen the user's modeling choices.
