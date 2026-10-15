# Bootstrap cloud pipeline in food-crisis-modeling-test

## Goal

Perform the one-time destination setup from `cloud_pipeline/OPERATIONS.md` ("One-time destination setup") in GCP project `feisty-flames-511718-d4` (display name `food-crisis-modeling-test`, billing enabled, operator `weilun.shi@cgiar.org` is Owner), so the project holds the accepted runtime, IAM and initialized baseline and can run monthly delivery once Earth Engine registration is complete.

## Decisions (grill, 2026-10-15)

- gcloud: new named configuration `food-crisis-test` (project `feisty-flames-511718-d4`, region `us-central1`), selected per command via `CLOUDSDK_ACTIVE_CONFIG_NAME`. The `default` configuration and the global ADC quota project (`manuel-remote-sensing`) are not changed; the init session overrides quota via `GOOGLE_CLOUD_QUOTA_PROJECT`.
- Scope: full one-time setup — APIs, service accounts, versioned buckets, Artifact Registry, IAM bindings, image copy, `deploy/setup.sh --execute`, `pipeline.py init --execute`.
- Names: buckets `food-crisis-test-ipcch-data`, `food-crisis-test-ipcch-requests` (us-central1); SAs `monthly-runtime`, `monthly-workflow`; AR repo `monthly-delivery`; prepare job `monthly-prepare`; namespace `monthly-staging`; operator `weilun.shi`; EE project = same project.
- Image: `crane copy` (checksum-verified crane release binary in `~/.local/bin`) of `…/manuel-remote-sensing/october-delivery/runtime@sha256:7e6133f3…` to `us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime:accepted-october`; `image_uri` pinned by digest.
- Private config: `~/ipcch-operator/food-crisis-test/project.json`, `work_dir` `operator-state/` beside it; copy of `initialized.json` kept under this task's `research/`.
- Python: new venv `~/.venvs/ipcch-cloud-operator` (python3.12) from `requirements.lock.txt --no-deps` + `pip check`.
- Earth Engine: operator registers the project in Console during execution; verified at the end.
- Existing bucket `historical_input_data_from_dropbox` is not touched. No lifecycle rules. No monthly run or scoring.

## Acceptance Criteria

- [ ] All 12 OPERATIONS APIs enabled.
- [ ] Two SAs exist; all OPERATIONS IAM bindings present (verified by reading policies back).
- [ ] Both buckets exist in us-central1 with uniform access and versioning.
- [ ] Destination image digest equals `sha256:7e6133f32ab0b28d3f29b827d4153975e99f97d440e97a1a8cdacdfa1052f0d0`.
- [ ] `setup.sh --execute` completes: Run jobs `monthly-prepare`, `oct-delivery`; Workflow `oct-delivery-trigger`; Eventarc `oct-delivery-requests`.
- [ ] `pipeline.py init` preview passes, then `--execute` writes `initialized.json`; all 74 baseline objects present with recorded generations.
- [ ] Earth Engine registration status reported (verified or explicitly pending).
- [ ] Receipt with resource list, IAM snapshot, digest and initialized.json under `research/`.
