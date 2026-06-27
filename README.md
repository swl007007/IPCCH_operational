# IPCCH Operational

This repository produces monthly model-compatible IPCCH input tables. A later
prediction step will use exported model weights and the model pipeline together
with that monthly input to generate predictions.

Start here:

1. `docs/00_handover_overview.md`
2. `docs/01_environment_setup.md`
3. `docs/02_ee_gcs_account_setup.md`
4. `docs/03_workflow_runbook.md`
5. `docs/04_output_inventory.md`
6. `docs/05_weilun_handover_gap_list.md`
7. `docs/08_sediqa_raw_data_download_notes.md`

Local filled config files such as `config/paths.ini` and `config/ee_gcs.ini` are operator-specific. Share templates, not secrets.

## Cloud Monthly E2E

The cloud monthly E2E path is the GCP-only v1 production path for one selected
feature month. It replaces local ArcPy remote-sensing extraction for the cloud
run with:

1. Cloud Run orchestration and manifest/run-state validation.
2. Cloud Batch monitoring of GEE EVI export plus rasterio zonal extraction.
3. Monthly base input assembly and schema validation.
4. Vertex AI custom-job inference with the fixed launch model package.
5. Release staging and atomic publication of
   `released/{YYYYMM}/release_manifest.json`.

The detailed operator quickstart is
`specs/001-cloud-base-input/quickstart.md`; implementation contracts are under
`specs/001-cloud-base-input/contracts/`.

### Required Inputs

Prepare a cloud input manifest in GCS with:

- `provider=gcp`, project, region, and object-store roots.
- A digest-pinned runtime image, for example `.../ipcch@sha256:<digest>`.
- Split service accounts for Cloud Run, Cloud Batch, and Vertex AI.
- Immutable references for scaffold, source panel, fixed/slow features,
  geometry, model package, and optional reference samples.
- EVI/GEE settings and runtime defaults or explicit overrides.

Every required GCS artifact must have a checksum with
`checksum_algorithm=sha256`, a generation/version reference, or an explicit
approved waiver in the manifest.

### Build Runtime Image

Build and push the single runtime image from the repo root, then use the image
digest in the input manifest:

```bash
docker build -f docker/Dockerfile -t REGION-docker.pkg.dev/PROJECT/REPO/ipcch:YYYYMM .
docker push REGION-docker.pkg.dev/PROJECT/REPO/ipcch:YYYYMM
docker inspect --format='{{index .RepoDigests 0}}' REGION-docker.pkg.dev/PROJECT/REPO/ipcch:YYYYMM
```

Use the returned `@sha256:...` reference, not a mutable tag, for release runs.

### Dispatch a Monthly Run

Run one feature month through the Cloud Run orchestrator:

```bash
gcloud run jobs execute ipcch-monthly-e2e-orchestrator \
  --region REGION \
  --args="--feature-month=YYYY-MM,--run-id=RUN_ID,--input-manifest-uri=gs://BUCKET/path/input_manifest.json"
```

Use a unique `RUN_ID`. Duplicate run ids are rejected before modifying the run
prefix.

### Inspect Results

For a successful run, consumers should start from:

```text
gs://.../released/{YYYYMM}/release_manifest.json
```

The release manifest is the authoritative stable entry point for accepted base
input, summary, prediction outputs, EVI/GEE evidence, Vertex AI job manifest,
inference report, model package reference, checksums, validation status, and
release timestamp. Do not infer release completeness from folder listings.

For local or downstream tooling, use:

```python
from cloud.common.release_reader import read_release_manifest

release = read_release_manifest(
    store,
    "gs://BUCKET/path/released/YYYYMM/release_manifest.json",
)
```

Failure evidence:

- Before run-prefix acquisition: inspect Cloud Run job status/logs; the run
  prefix should not be modified.
- After run-prefix acquisition: inspect `runs/{run_id}/run_summary.json` and
  the report files named in `artifact_paths`.
- Vertex inference failures write `runs/{run_id}/inference/inference_error.json`,
  `vertex_ai_job_manifest.json`, and `inference_report.json`.
- Release conflicts leave the previous `release_manifest.json` current.

### Local Validation Before Deployment

Run local deterministic checks before building/deploying:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_operational_launch_cli.py \
  tests/test_operational_launch_input_contract.py \
  tests/test_reshape_remote_sensing_wide_to_long.py \
  tests/test_build_monthly_ipcch_base_input.py \
  -q -p no:cacheprovider
ruff check cloud tests/cloud
ruff format --check cloud tests/cloud
```

The live GCP smoke test is intentionally gated. Run it only when real cloud
credentials and smoke-test environment variables are configured:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/cloud/test_gcp_smoke_monthly_e2e.py -q -p no:cacheprovider
```

Cloud v1 must not invoke local workstation scoring, prediction maps,
prediction sheets, full delivery packages, model training, FLDAS, GOSIF-GPP,
VIIRS, or undeclared non-Vertex inference.

## Operational Launch Inference

After the monthly model input table is built, run pure inference with a fixed
model package:

```bash
python3 model_pipeline/run_operational_launch_inference.py \
  --input Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_YYYYMM.csv \
  --model-package model_artifacts/launch_2026_04 \
  --spatial-path Outcome/ipcch_unified/spatial/ipcch_admin_geometry.shp \
  --output-dir Outcome/ipcch_unified/predictions/YYYYMM \
  --feature-month YYYY-MM
```

The command writes six primary delivery files: prediction sheet and map for
`0m`, `6m`, and `12m`. The production command does not train models.
