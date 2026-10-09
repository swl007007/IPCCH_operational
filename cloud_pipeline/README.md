# Cloud pipeline

This directory is the maintained runtime and operator entrypoint for FEWSNET/IPCCH monthly delivery. It preserves the existing feature, fill, model and event contracts. Start with [QUICKSTART.md](QUICKSTART.md) and the detailed [operator commands](OPERATIONS.md).

`bootstrap/` contains the frozen assets, full historical baseline, six accepted model scopes and explicit descriptor used for one-time destination initialization. It also binds per-horizon diagnostic evidence in `bootstrap/evidence/`; see [diagnostic evidence](OPERATIONS.md#diagnostic-evidence). Full history is required by lag and normalization semantics. `fallback/october_2026/` preserves the accepted October delivery (cloud rerun with populated confidence diagnostics) and its evidence; no new scoring is implied by relocation.

Use a destination-owned project, buckets, service accounts, digest-pinned runtime and Earth Engine registration. No live deployment is performed by obtaining this directory. Keep credentials, filled project configuration and mutable work/state outside the distributable.

## Runtime and deployment

Install the frozen Python 3.12.3 environment from `requirements.lock.txt`. For bootstrap, copy the accepted image to your registry preserving its digest; no rebuild or October replay is needed. `docker build -f deploy/Dockerfile .` and `bash deploy/build_context.sh` produce a new runtime whose changed digest needs separate actual compatibility evidence before acceptance. The image includes the four runtime packages and package data; baseline/fallback data is uploaded separately.

`deploy/workflow.yaml` retains the Storage-finalized -> Workflows -> Cloud Run delivery path. `bash deploy/setup.sh /private/project.json --execute` provisions preparation, delivery, Workflow and Eventarc resources from the same config; without `--execute` it prints commands. Set `workflow_service_account` in that config. Read OPERATIONS before using it. Successful submission is not successful delivery; inspect durable run status.

## Handover archive

After all bootstrap and fallback members are present:

```bash
python deploy/handover_package.py build --archive dist/cloud_pipeline.tar.gz
python deploy/handover_package.py verify --archive dist/cloud_pipeline.tar.gz
```

The builder reads only the supported public files and runtime/data directories, writes an internal exact SHA-256/size inventory, verifies archived bytes and writes a checksum beside the archive. The source operational directory remains writable. Archives are create-only; choose a fresh output name for a new release. Developer controls, local config, state, tests and existing dist archives are excluded. Extract to a fresh directory, verify before use, and install the lock there.

## Local checks

From this directory, `python -m pytest tests/cloud tests/test_refresh_h5_inputs.py` checks supported contracts. September comparison fixtures are included under `tests/fixtures/september/`; standalone runtime import checks need no original repository. Tests do not repeat accepted model scoring or call live providers.

The archived original migration builders and Final_harmonise wrapper are superseded and their legacy-only tests are omitted. Training/debug CLIs are omitted; internal FEWS helpers still imported by its existing package exports are retained unchanged. Old source paths inside frozen evidence are provenance, not runtime instructions.
