# CP0 live preflight: cloud reads, MLflow identities, research environment pins

Executor: Claude Opus 5.5 1M, session 6a490ae1-ee00-43f9-bdfc-c887c9816c09, pane w1A:p2. Date: 2026-10-30.
Task phase: planning. No task start, code change, fit, worktree, cloud write, IAM/auth or gcloud config change, and no Audit. Reads only, under the user's cloud-read preauthorization.
Caller identity: gcloud active account `weilun.shi@cgiar.org`; the default project stays `manuel-remote-sensing` and was not changed. Every cloud call passed `--project=food-crisis-modeling-enso` and an explicit generation-pinned `gs://…#generation` URI, except the six job manifests/configs, which were described without a generation because no pin is recorded locally; what came back is the generation current at read time, recorded as observed.
Raw evidence (no credential material; checked by grep): `research/cp0-live/{cp0_live_objects,cp0_meta,cp0_bytes,cp0_mlflow}.json`, MLflow reader script `research/cp0-live/cp0_mlflow_read.py`.

## 1. GCS inputs of the approved 10-28 formal source manifest

Bounded object list (34 objects, no bucket listing):
- every `gs://` reference carrying a generation in `R/staging/ipcch-ch-validity-20261028/job-packet-ch/objects/{manifest,config}-formal-h{00,06,12}.json`: 28 unique (uri, generation) pairs; local packet manifest sha256 h00 `f1509cc1…`, h06 `1407b2db…`, h12 `e3e20b2e…`;
- the six uploaded job inputs `gs://food-crisis-modeling-enso-research-inputs/training-jobs/ipcch-ch-validity-refits/r1/inputs/{manifest,config}-formal-h{00,06,12}.json` named by `specs/spec-formal-hHH.json`.

Commands (read-only):
- Metadata: `gcloud storage objects describe "gs://…#<generation>" --project=food-crisis-modeling-enso --format=json`, once per object. 34/34 returned with exit 0 and no permission errors; wall time 7 min 37 s through the Windows SDK.
- Byte check against local copies: local files found by exact basename and size under R/{staging,scratch,.trellis/tasks,cache,exports} and the shared folder; sha256 and base64-md5 computed locally (`hashlib`). No download.
- Streamed byte check of the three objects without a local copy: `gcloud storage cat "gs://…#<gen>" --project=food-crisis-modeling-enso | sha256sum` (bounded, 8,277,042 bytes total, nothing written to disk). Results:
  - h00: sha256 `009caf296724b760…` (= manifest), md5 `OeD8ys5GJL+jm1raV8rXZw==` (= GCS)
  - h06: sha256 `e3801e0c4f567985…` (= manifest), md5 `YN1TMd+r+UtzKgX1thgqwA==` (= GCS)
  - h12: sha256 `92360132170096ec…` (= manifest), md5 `fH4IkhgtBSq3bk04OZ3XzQ==` (= GCS)

Verification classes, kept distinct:
- **METADATA**: the pinned generation exists (latest unversioned generation was not checked), plus size, GCS md5/crc32c, and the custom `sha256` metadata where present. This says what the object store reports; it does not hash bytes.
- **BYTES**: bytes hashed to the expected sha256, and the GCS-reported md5 equals the md5 of those same bytes. The bytes were either a local copy whose sha256 equals the manifest sha256 or a stream from GCS.

Results:
- All 28 pinned generations exist: each `describe` of `URI#generation` returned exactly that generation. Generations are immutable, so this proves the pinned bytes are still retrievable. It does not show that the unversioned (latest) object equals the pin; that was not checked and is not needed, since the packet reads by generation.
- 34/34 objects are BYTES-verified: 29 via local copies, 5 streamed by pinned generation.
- Second pass (2026-10-30, after Supervisor review) streamed the two objects that had been METADATA-only. Exit status and digests are in `cp0-live/cp0_stream2.json`:
  - `gcloud storage cat "gs://food-crisis-modeling-enso-research-inputs/inputs/ipcch.compact.manifest/compact_climate_weather_oracle_v1_manifest.json#1792154075204519" --project=food-crisis-modeling-enso`: exit 0, 138,760 bytes (= GCS size), sha256 `456360536a3929e1571d96ba9f16e2f0de54bc1b20019f797bbe62c0c89732ca` = expected, md5 `HWKhmiv16s2pM5tHA2PLOg==` = GCS.
  - `gcloud storage cat "gs://food-crisis-modeling-enso-research-inputs/inputs/ipcch.idp_admin0_monthly/idp_admin0_monthly.csv#1792154074942115" --project=food-crisis-modeling-enso`: exit 0, 193,702 bytes (= GCS size), sha256 `a1ebb82a8e14fc0fb8103d6086217b93da351fc4a8f7fcfbe9eaa44a9df602e1` = expected, md5 `kkRop+T9yWSYIyShC04oJw==` = GCS.
- For the three first-pass streams (shell pipeline into `sha256sum`), `gcloud`'s own exit status was not captured. Completeness rests on byte count = GCS size, md5 = GCS md5, and sha256 = expected.
- The six job manifests/configs are BYTES-verified against the local job packet: live GCS md5 equals the md5 of `job-packet-ch/objects/*.json`.

| object (`…/` = gs://food-crisis-modeling-enso-research-inputs/) | pinned gen | described gen | size | GCS md5 | sha256 | class |
|---|---|---|---|---|---|---|
| `…/inputs/ipcch.alphaearth.descriptors.descriptor_table.csv.gz/descriptor_table.csv.gz` | 1792154225849272 | 1792154225849272 | 6527715 | `blG8vOVI9KgpkPs0l6aeSQ==` | `362c58b0f3396fd8…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.ch-validity-links-20261028/ch_links.csv.gz` | 1793219070023026 | 1793219070023026 | 288286 | `QQvcCu2f/Y9nZqW+ZpxqrQ==` | `ac4ad6aaa8dc9e0e…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.climate_monthly/climate_monthly_2015_2026_MODELING_READY.csv` | 1792155988779628 | 1792155988779628 | 1084506970 | `zIuiRbUNSt8vqF9qBkUNFg==` | `8082b72ea5fa5c30…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.climate_seasonal/climate_2015_2026_MODELING_READY.csv` | 1792155829679604 | 1792155829679604 | 186792349 | `W86bOxVdTI8mS3pvRwJUmA==` | `f024a66c8979fb4a…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.compact.manifest/compact_climate_weather_oracle_v1_manifest.json` | 1792154075204519 | 1792154075204519 | 138760 | `HWKhmiv16s2pM5tHA2PLOg==` | `456360536a3929e1…` | BYTES (second-pass stream; sha256 = manifest; md5 = GCS; exit 0) |
| `…/inputs/ipcch.country_lookup/country_area_id_lookup.csv` | 1792153966578810 | 1792153966578810 | 214996 | `jz4+7i3r0F7pjN+53RADWg==` | `e2baf6ae9481b42b…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.idp-20261017/idp_ipcch_monthly.parquet` | 1792258101675874 | 1792258101675874 | 3173840 | `gKcbh3KrPJuUzw4szgVY2A==` | `8b2ba29988178a78…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.idp_admin0_monthly/idp_admin0_monthly.csv` | 1792154074942115 | 1792154074942115 | 193702 | `kkRop+T9yWSYIyShC04oJw==` | `a1ebb82a8e14fc0f…` | BYTES (second-pass stream; sha256 = manifest; md5 = GCS; exit 0) |
| `…/inputs/ipcch.panel-20261019/IPCCH_202610_completed.csv` | 1792463222777994 | 1792463222777994 | 1803935695 | `uZH2paZOtKyRGGaDzXu2yw==` | `09002869ecc25667…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.panel-acledagg-gosifv3-20261027/IPCCH_202610_interim_acledagg_gosifv3_20261027.csv` | 1793144581875896 | 1793144581875896 | 2339008654 | `8Q1HFAyumIRLAMay1C6N4w==` | `b2d5d2ce6bd6a78d…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.region_mapping/area_id_country_region_mapping.csv` | 1792154473935553 | 1792154473935553 | 51343 | `3xUEkvoDRQM5wpt3rZB1uQ==` | `18ab5099ce2d1154…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.report-region-map-20261027/area_id_report_region_mapping_20261027.csv` | 1793144440149174 | 1793144440149174 | 45115 | `gUDHnlREbggAKoXlMhxY+Q==` | `5d1fd7f8b0dbf5e4…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.validity-20261017/static29_by_admin.csv.gz` | 1792213590853844 | 1792213590853844 | 211977 | `YXPyzZ2C0mScEwxrRVuOoA==` | `229d593ef8fc96b3…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.validity-20261019/analyses_combined_2026-10-19.json` | 1792462894893588 | 1792462894893588 | 110194 | `DpCz8q8t3WPBQm7fIQARhQ==` | `1c7dfb786a8f8247…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/inputs/ipcch.validity-20261019/areas_combined_2026-10-19.geojson` | 1792462922478447 | 1792462922478447 | 288951862 | `IFOIQxJIm8oy2N8RTq9Aig==` | `200f5dcaad88e18b…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/training-jobs/ipcch-acledagg-hpt/r1/freeze/freeze-h00.json` | 1792690601404885 | 1792690601404885 | 96852 | `vUcl03FZNMOpbh7/DFAcSA==` | `dc152d4ea6e719a3…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/training-jobs/ipcch-acledagg-hpt/r1/freeze/freeze-h06.json` | 1792690601509870 | 1792690601509870 | 97881 | `Mamv5VUR6lkM9SO9CSiqJw==` | `fe6be936989d045d…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/training-jobs/ipcch-acledagg-hpt/r1/freeze/freeze-h12.json` | 1792690601611221 | 1792690601611221 | 97822 | `/lTBHdbOMwqDK+3EXL+Tkg==` | `b094e05934931eb1…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/training-jobs/ipcch-acledagg-hpt/r1/freeze/index.json` | 1792690601692816 | 1792690601692816 | 919 | `akVniW+zMhL1uD0tUL3kyQ==` | `d85582b3ca1d6364…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/training-jobs/ipcch-acledagg-hpt/r1/inputs/baseline-predictions-h00.csv.gz` | 1792634024285433 | 1792634024285433 | 3063753 | `uEZSQSmqjWnNA8yXxqu8kw==` | `4a18b51d451d739d…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/training-jobs/ipcch-acledagg-hpt/r1/inputs/baseline-predictions-h06.csv.gz` | 1792634025112538 | 1792634025112538 | 2747238 | `WvYThrKWXeCVbht6UTGkrA==` | `f788cb92c6abdc68…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/training-jobs/ipcch-acledagg-hpt/r1/inputs/baseline-predictions-h12.csv.gz` | 1792634025911056 | 1792634025911056 | 2374944 | `1rozOeVod5gQ3I6Xz3MQ0A==` | `4dfea5adbffceb61…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/training-jobs/ipcch-ch-validity-refits/r1/inputs/baseline-predictions-gosifv3-h00.csv.gz` | 1793219070652120 | 1793219070652120 | 3203671 | `OeD8ys5GJL+jm1raV8rXZw==` | `009caf296724b760…` | BYTES (streamed sha256 = manifest; md5 = GCS) |
| `…/training-jobs/ipcch-ch-validity-refits/r1/inputs/baseline-predictions-gosifv3-h06.csv.gz` | 1793219071144730 | 1793219071144730 | 2714883 | `YN1TMd+r+UtzKgX1thgqwA==` | `e3801e0c4f567985…` | BYTES (streamed sha256 = manifest; md5 = GCS) |
| `…/training-jobs/ipcch-ch-validity-refits/r1/inputs/baseline-predictions-gosifv3-h12.csv.gz` | 1793219071644622 | 1793219071644622 | 2359488 | `fH4IkhgtBSq3bk04OZ3XzQ==` | `92360132170096ec…` | BYTES (streamed sha256 = manifest; md5 = GCS) |
| `…/training-jobs/ipcch-gosif2025-retrain/r1/inputs/manifest-formal-h00.json` | 1793144582204676 | 1793144582204676 | 5169 | `UGiLH7/6V9PBsEEOsytBtQ==` | `99b1e964005137cf…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/training-jobs/ipcch-gosif2025-retrain/r1/inputs/manifest-formal-h06.json` | 1793144582454578 | 1793144582454578 | 5169 | `FziBXUoj+l1mCP+LnTVZ0Q==` | `aa73377c901cfb66…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/training-jobs/ipcch-gosif2025-retrain/r1/inputs/manifest-formal-h12.json` | 1793144582716895 | 1793144582716895 | 5169 | `n7fQNEo3uuh0deKlVA/T5A==` | `daabe12d6fa30313…` | BYTES (local sha256 = manifest; local md5 = GCS md5) |
| `…/training-jobs/ipcch-ch-validity-refits/r1/inputs/manifest-formal-h00.json` | live | 1793219071854845 | 5719 | `WP+UHYq19HnzM6DAuXOrEw==` | `f1509cc1f6eb58e0…` | BYTES (local sha256 recorded; local md5 = GCS md5) |
| `…/training-jobs/ipcch-ch-validity-refits/r1/inputs/config-formal-h00.json` | live | 1793219072543496 | 85659 | `H4+vZZapv/PtkZ53ZoSJ6A==` | `fca3f2db9c62483c…` | BYTES (local sha256 recorded; local md5 = GCS md5) |
| `…/training-jobs/ipcch-ch-validity-refits/r1/inputs/manifest-formal-h06.json` | live | 1793219072084269 | 5719 | `c4ImmhqxKZTOMwslEyaaqA==` | `1407b2db46ed9691…` | BYTES (local sha256 recorded; local md5 = GCS md5) |
| `…/training-jobs/ipcch-ch-validity-refits/r1/inputs/config-formal-h06.json` | live | 1793219072800432 | 87112 | `2bF1Oj1wqiTFjjIv4pqBVw==` | `29c4418d78aa4ade…` | BYTES (local sha256 recorded; local md5 = GCS md5) |
| `…/training-jobs/ipcch-ch-validity-refits/r1/inputs/manifest-formal-h12.json` | live | 1793219072287545 | 5719 | `QNfgZEYGGcV4QU9tbrjheQ==` | `e3e20b2e9876e210…` | BYTES (local sha256 recorded; local md5 = GCS md5) |
| `…/training-jobs/ipcch-ch-validity-refits/r1/inputs/config-formal-h12.json` | live | 1793219073056045 | 87111 | `ZjOtbhF2aOXHvSB63yWi1A==` | `8673b0946ac9b80e…` | BYTES (local sha256 recorded; local md5 = GCS md5) |

## 2. MLflow baseline runs and registered models (read-only)

- Credential: the read-only identity documented in `R/control-plane/research_cloud/deploy/mlflow_identities.py:5,27` and `provision_secrets.py` (`IDENTITIES["mlflow-reader"] = ("ipcch-reader", [])`), i.e. Secret Manager `projects/food-crisis-modeling-enso/secrets/mlflow-reader/versions/latest`. It was read with `gcloud secrets versions access latest --secret=mlflow-reader --project=food-crisis-modeling-enso` inside one Python process. The value was held only in memory, never printed or persisted, and no other secret was read or enumerated. No writer secret was used. Pre-check: no MLflow env credentials, `~/.mlflow/credentials` and `~/.netrc` were found locally; anonymous `GET /health` returned 200 and anonymous `runs/get` returned 401.
- Endpoints, all GET to `https://mlflow.weilunshi.com` with a 30 s socket timeout and a 300 s outer `timeout`: `/api/2.0/mlflow/users/current`, `/api/2.0/mlflow/runs/get?run_id=…`, `/api/2.0/mlflow/experiments/get?experiment_id=2`, `/api/2.0/mlflow/model-versions/search?filter=run_id='…'`. Every request returned 200; `users/current` reports `ipcch-reader`.

| H | run id | run status / lifecycle | experiment | registered model (version, status, source) | package.json sha256 tag = local harvest | image digest tag |
|---|---|---|---|---|---|---|
| 0 | 298c4718b4d64e6f8a5c315e8c22d25d | FINISHED / active | 2 `IPCCH dashboard` | "IPCCH Validity-augmented pooled (GOSIF v3 + CH validity 20261028) \| … \| 0-month" v1 READY `models:/m-698519b8daeb456ea5e9126b6fc18e8f` | `a111ab7e…` yes | `sha256:2b18cf72…` |
| 6 | 00d4e94c824343bf86a0c2b79d5b9ed0 | FINISHED / active | 2 | "… \| 6-month" v1 READY `models:/m-46beb4c7d5674c1abd874b3bd90c1f87` | `813b343c…` yes | same |
| 12 | f436da15c71c469199784db065f3b63b | FINISHED / active | 2 | "… \| 12-month" v1 READY `models:/m-9da8be7f46c946e69a8e759d9064a77a` | `e88ac65b…` yes | same |

- Each run has 21 params (12 hyperparameters `{other,q3}_{colsample_bytree,learning_rate,max_depth,min_child_weight,n_estimators,subsample}`) and its `source_commit` tag records `439a488…+overlay:…dataset_input.py@sha256:a6d…`. The local harvest `package.json` sha256 equals each run's `package.json_sha256` tag.
- Hyperparameter pin: for each horizon, all 12 run params equal `winner.params` in `freeze-hHH.json`, whose bytes were verified above (gen 1792690601404885 / …509870 / …611221). These are the values to map H0→H2, H6→H8, H12→H14 (R10).
- Not verified: artifact bytes under `mlflow-artifacts:/2/<run>/artifacts` (not downloaded) and LoggedModel internals.

## 3. Research environment pins

Lock: `R/control-plane/research_cloud/images/training-ipcch-validity/requirements.lock.txt`, sha256 `ce0b23ad2483c8945565b5fdf0ea8c4d477418579ee2746a7679d98f7c43f834`, 62 pins; image base `python:3.12.3-slim@sha256:afc139a0…` (Dockerfile:8). Comparison by installed distribution metadata, all 62 pins:

| venv | Python | exact | missing | differing |
|---|---|---|---|---|
| `~/.venvs/ipcch-validity-idp` | 3.12.3 | 61 | 0 | certifi 2026.10.19 vs 2026.7.22 |
| `~/.venvs/ipcch-mlflow` | 3.12.3 | 33 | 12 | 17 incl. cachetools, databricks-sdk, fastapi, google-auth |
| `~/.venvs/ipcch-geo` | 3.12.3 | 12 | 43 | 7 incl. charset-normalizer, click, idna, packaging, pytz |
| `~/.venvs/ipcch-xgb`, `ipcch-xgboost` | 3.12.3 | 6 | 38 | numpy 1.26.4, cryptography, … |

**Correction to cp1-plan.md §1:** `ipcch-geo` does not match the research lock; the earlier "same versions" statement held only for the core numerical libraries. Selected local research environment: `~/.venvs/ipcch-validity-idp`. It is not an exact lock match: 61/62 pins are exact, and certifi (installed 2026.10.19 vs locked 2026.7.22, CA bundle only, no numerical code) is an explicit, recorded exception, the same kind as the operational env's certifi drift in `~/.venvs/ipcch-cloud-operator`. Cloud fits use the image, not a local venv. The operational test env stays separate (`~/.venvs/fewsnet-test-lock-20261022`, 57/57 of `cloud_pipeline/requirements.lock.txt`).

## 4. CP1/CP2 command and resource packet draft (planning only; nothing released)

This reuses the 10-28 workflow (`R/staging/ipcch-ch-validity-20261028/job-packet-ch/operation-packet.md`): local helper scripts with confirm-env guards, the `research_cloud.training.vertex_submit` submit/poll/reconcile path, the harvest script, and package replay. A new packet directory `R/staging/ipcch-h2h8h14-<date>/job-packet` is created only at CP1, from the isolation worktree commit, and the 10-28 packet is never edited. Each numbered step needs Supervisor release, and receipts go to `$D`.

**CP1, local, no paid operations.**
- **P0. Isolation.** Re-verify the capture fingerprint. Create the worktree/branch and commit the three modules plus four tests (cp1-plan.md §2).
- **P1. Code changes.** C1–C5 on the isolation branch. Run the existing research tests and the new 2/8/14 tests with `~/.venvs/ipcch-validity-idp`: `cd <worktree> && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. ~/.venvs/ipcch-validity-idp/bin/python -m pytest research_cloud/tests -q -p no:cacheprovider`.
- **P2. No-fit plan.** CLI forms confirmed in VP:3167-3299 and VF:1427-1441. Per H in {2, 8, 14}: (a) dataset build `python -m research_cloud.training.ipcch_validity_features --manifest <local manifest> --out <scratch>/dataset-hHH --horizon H`; (b) `python -m research_cloud.training.ipcch_validity_pooled plan --dataset <scratch>/dataset-hHH --config <config-formal-hHH.json> --digests --out <scratch>/plan-hHH`; (c) `python -m research_cloud.training.ipcch_validity_pooled gate --manifest <local manifest> --config <config-formal-hHH.json> --out <new dir>`. Today `--horizon` accepts only `HORIZONS` (0/6/12), so this needs C1 first. Inputs are the byte-verified objects in §1, read locally. Records schedule and eligibility counts, 527-column order equality with the H0 order, GPP availability counts, key multiplicity and complete months (cp0-semantic-followup.md).
- **P3. Configs.** Three `config-formal-hHH.json` derived from the 10-28 configs. The only intended differences are horizon, cutoff, final-context-only schedule, the oracle switch, the GPP filter, and the hyperparameter source mapping record. A `make_packet`-style assertion enumerates the exact differing keys.

**CP2 cloud operations (writes and paid; each requires Supervisor release).**

| step | operation | bound |
|---|---|---|
| B1 | Cloud Build of the overlay image (`training-ipcch-validity` base `sha256:fd921dd7…` + changed modules), in the existing Artifact Registry repo `us-central1-docker.pkg.dev/food-crisis-modeling-enso/research` | one build; new digest recorded; no tag overwrite |
| U1 | create-only uploads (`if_generation_match=0`, `retry=None`, size/md5/crc32c readback) of 3 manifests + 3 configs under a new prefix `training-jobs/ipcch-h2h8h14-final/r1/inputs/` | 6 objects, each < 8 MiB; data inputs reused by generation, not re-uploaded |
| O1 | occupancy read before every submit wave (existing occupancy script; counts all active custom-job vCPUs in us-central1, including other tasks) | region quota 42 vCPUs: three simultaneous n1-standard-16 = 48 > 42 is never allowed. A wave is released only if existing vCPUs + 16 × planned ≤ 42 |
| J1–J3 | Wave 1 = at most TWO jobs (H2, H8) if O1 shows ≥ 32 free vCPUs (else one job, or wait). Wave 2 = H14 only after a fresh O1 shows ≥ 16 free vCPUs and the wave-1 jobs reached a terminal state, checked failure-first as in the 10-28 h12 gate. Each is a Vertex CustomJob: n1-standard-16 ×1, 100 GiB pd-standard, timeout 7,200 s, `disableRetries`, SA `research-trainer@`, the existing job-writer secret read inside the worker only, publishing one new run + model version into experiment `IPCCH dashboard` | 3 jobs, one submit each; unknown outcome → `reconcile` only; no automatic resubmit/refit |
| H1–H3 | harvest (generation-pinned reads) + package replay | reads only |

- **Cost.** Reservation estimate computed as in 10-28: training 3 × (USD 0.8739954/h × 7,800 s + PD) ≈ 3 × 1.9073 = 5.72 at the timeout bound, plus build ≈ 0.19 and platform ≤ 1.00, about USD 6.91. Proposed USD 8.00 task cap = this reservation estimate plus abort boundaries: per-job 7,200 s timeout, `disableRetries`, no resubmit, wave gating, stop on first failure. It is not a billing-enforced hard limit; GCP does not stop spend at USD 8.00, and actual billing can differ from catalogue prices. The final-context-only fit (3 contexts / 12 regressors vs 11 / 44) is expected well below the bound, but the reservation is not scaled down from it. Billed actuals are reported from billing evidence when available, never assumed.
- **Stop rules.** Any precheck, schema, or parameter mismatch stops before the paid steps. A failed job stops the remaining submissions for review. Existing runs, models, versions, and aliases are never modified.
- **Alternative needing no build.** Local fits in `~/.venvs/ipcch-validity-idp` with MLflow publication through the existing writer path. This saves the image build but publishes from a non-image environment. Not recommended; offered for the Supervisor's choice.

## 5. Limits and open items

- All 34 inputs are BYTES-verified (second pass completed).
- MLflow artifact bytes are not verified; registered-model aliases were not queried.
- Vertex job records for the 10-28 runs were not re-read (only the MLflow identities). The job ids are recorded in the 10-28 harvest paths.
- No permission was denied in this pass.
