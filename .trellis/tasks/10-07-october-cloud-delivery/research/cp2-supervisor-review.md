# CP2 supervisor disposition

Baseline `0feaad9`; accepted after five corrections. This accepts current-script implementation and local/mock behavior, not a completed live refresh.

Two read-only reviewers ran the original 32 CP2 tests and found four uncovered cases: history bypassed the cutoff/complete-month limit; Batch submission failure left no structured failed status; preparation request checksum was not persisted; raster mosaicking lost internal masks when nodata was unset. The executor corrected them and added regression coverage.

Supervisor independently ran 126 related CP1/CP2/Batch tests (all passed, 208 dependency warnings), then reproduced an additional defect in the first mask fix: Rasterio default destination nodata treated **valid zeros** as missing. Adjacent all-valid `[0,10]` and `[20,30]` shards returned `[masked,10,20,30]`. The executor now explicitly sets float64/NaN nodata on the merge itself and tests valid zero alongside a separate masked pixel. Final supervisor rerun:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/ipcch-oct-cp2/bin/python -m pytest tests/cloud/test_remote_sources.py tests/cloud/test_prepare.py -q -p no:cacheprovider
```

**39 passed in 1.55s**, exit 0; 219 Rasterio/Affine PendingDeprecation warnings retained, not suppressed. Larger executor regression before the final isolated mask fix: 413 passed, one live-GCP skip, one known baseline horizon failure. Relevant source fixes and full executor logs are under `research/cp2_evidence/`.

Confirmed boundaries: two explicit native rosters; current source/reducer contracts; FEWS nightlight mean and IPCCH sum; named FLDAS bands; provider SD regional mean; known CRS required; exact discovered EE image identity; retained HTTP bytes/hash; generation-bound input reads; per-system pinned histories; cutoff-bound history; plan and extraction sentinels; actual Cloud Run planning entry submits the existing Batch launcher with extraction worker and zero task retries. New paths are not evidence that a runtime image has been deployed or a provider run succeeded.

Cloud authorization is recorded in `supervision.md`. Live SDK project verified `manuel-remote-sensing`. Supervisor enabled Run, Batch, Workflows/Executions, Eventarc, Artifact Registry, Cloud Build, Compute, Pub/Sub, IAM and IAM Credentials APIs. Service Usage operation `operations/acf.p2-645415198431-cdc0c453-d347-4976-9e85-d696a32a0f00` completed successfully. Earth Engine and Storage were already enabled. No scoring run, training or existing-release pointer mutation has occurred.
