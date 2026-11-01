# IPCCH monthly production pipeline

This is the code for the existing IPCCH monthly service in Google Cloud project `feisty-flames-511718-d4`. **`food-crisis-test-ipcch-data` is the production bucket, and `monthly-staging` is its production release namespace.** These historical names do not designate a test environment.

Use [OPERATIONS.md](OPERATIONS.md) for the next incremental run: prepare inputs, preview selections, submit once, monitor and read the published release. [selections.example.json](selections.example.json) supplies all eleven keeps for real-mode generation, inference and current publication.

## Monthly delivery

CSV templates for every manual field, column definitions and refresh choice fragments are in [examples/inputs](examples/inputs/README.md). Keep needs no CSV; replace the synthetic examples with complete real input data before refreshing.

```text
11 manual keep/refresh choices
  -> submit uploads/pins inputs and freezes the UTC month
  -> request upload triggers the existing cloud workflow
  -> incremental climate / GPP / nightlight + retained inputs
  -> feature batch -> H2/H8/H14 inference -> production current
```

All-keep preserves the eleven manual inputs while automatic sources still update. Earth Engine exports are submitted and consumed automatically when unsaved demand exists. The current FEWS NET member is inherited unchanged; this IPCCH submission does not update FEWS predictions.

Execution month M is the UTC month at submission freeze; feature origin O=M-2. H2/H8/H14 correspond to public leads 0/6/12 and targets M/M+6/M+12. The next distinct increment after the accepted November run is M=2026-12, O=2026-10.

## Production references

| Item | Location |
|---|---|
| Current release pointer | `gs://food-crisis-test-ipcch-data/monthly-staging/current.json` |
| Retained inputs and feature batches | `gs://food-crisis-test-ipcch-data/ipcch-v2/real/` |
| Manual refresh uploads | `gs://food-crisis-test-ipcch-data/inputs/v2/` |
| Triggering requests | `gs://food-crisis-test-ipcch-requests/requests/<run_id>/run_manifest.json` |
| Published delivery files | `gs://food-crisis-test-ipcch-data/deliveries/<run_id>-ipcch/` |
| Deployment configuration | [deploy/ipcch_v2_deployment.food-crisis-test.json](deploy/ipcch_v2_deployment.food-crisis-test.json) |

Accepted run `ipcch-real-fe7282ef75e747fd` on 2026-11-01 used M=2026-11/O=2026-09, 527 features and 6,226 areas per horizon, publishing current generation `1793503777656101`. This is a dated reference; read the live pointer for later releases. Runtime digest, input formats and known source gaps are in [OPERATIONS.md](OPERATIONS.md).

## Required operator assets

Use the existing private production `project.json`, its initialized `work_dir`, the locked Python 3.12.3 environment and authorized cloud access. Keep operator state: it binds submissions and supports status/resume. The legacy `project.example.json` lacks v2 configuration and cannot replace this production config.

Histories, models and the accepted combination envelope/package/handoff are already installed or retained in production. They are not repeated monthly uploads. Credentials, filled configuration, mutable state, production data and model binaries are supplied privately and excluded from this code repository. Tests and small fixtures are included.

## Code maintenance

`requirements.lock.txt` fixes the environment. Run checks from this directory with the project's memory limits: 4 GiB memory, no swap, 3 GiB address space, one BLAS/OMP thread and a bounded timeout. Focused checks include `python -m pytest tests/test_operator_submit_v2.py tests/cloud/test_ipcch_install.py`; use the existing guarded runner on the operator workstation.

A code sync does not rebuild or deploy the runtime. A future image build needs the separately supplied accepted envelope, package, handoff and isolated smoke fixture through `deploy/build_context.sh`, followed by compatibility acceptance of the new digest. Routine monthly operation uses the current deployment.
