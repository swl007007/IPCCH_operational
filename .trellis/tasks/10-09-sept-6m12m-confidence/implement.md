# Implement — September 6m/12m with confidence

Order matters: a gate failure stops the later steps. Run Python from `cloud_pipeline/` with `~/.venvs/ipcch-h5-202609/bin/python` unless stated otherwise.

## Step 0 — Preconditions
- [ ] Record the sha256 of `CP/bootstrap/baseline.json`, `CP/dist/cloud_pipeline.tar.gz` and all files in `september_manual/inventory.json` and `CP/fallback/october_2026/retained_inventory.json` to `research/preservation-before.json`.
- [ ] Confirm the venv imports `xgboost==3.2.0`, `pandas==3.0.0` and `geopandas`. Confirm at least 12 GB of free memory.

## Step 1 — FEWS proxy evidence (gate G1)
- [ ] Write `research/build_fewsnet_proxy_evidence.py`. Use fs1 in regression mode against `september_manual/fewsnet/polygon_confidence.csv` (exact counts). **G1: an exact match is required.**
- [ ] Emit the fs2 → 6m and fs3 → 12m evidence CSVs to `CP/bootstrap/evidence/`. Record source hashes, drops and counts.

## Step 2 — IPCCH resubstitution evidence (gate G2)
- [ ] Write `research/build_ipcch_resubstitution_evidence.py` (trainer frame rules, saved medians, four-target predict).
- [ ] Run it in h5 regression mode (bundle scope_5m extracted to `/tmp`, refreshed panel, saved keys). **G2:** counts must equal `polygon_training_errors.csv` exactly and residuals must be within `atol=1e-6` of the four-target replay.
- [ ] Emit the area and residual evidence for scopes 0, 6 and 12. Assert medians and row counts per scope.

## Step 3 — Validator allowlist (gate G3)
- [ ] Run GitNexus `impact` upstream on `_evidence_identity` and report the risk.
- [ ] Add `APPROVED_PROXY_EVIDENCE` and its branch. Add the accept/reject tests listed in design §3.
- [ ] **G3:** `python -m pytest tests/cloud tests/test_refresh_h5_inputs.py tests/test_operator_cli.py` passes, or only pre-existing failures remain and are reported with their output.

## Step 4 — Baseline binding (gate G4)
- [ ] Write and run `research/bind_baseline_evidence.py`. It adds the `files` entries, flips the 13 declarations and writes `provenance.json`.
- [ ] Before writing, diff the old and new JSON: only the `files` and `diagnostics` keys may change.
- [ ] **G4:** a fake-service init/validation of the new baseline passes, and the operator CLI tests pass.

## Step 5 — September-origin run (gate G5)
- [ ] Download the prepared snapshot and the retained ACLED/WFP into `~/work/sept-6m12m-20261009/inputs`, verifying generation and sha256.
- [ ] Write `research/run_september_delivery.py`: request with origin 2026-09, reference verification, per-system `run_system` (separate processes, `/usr/bin/time -v`), `finalize`, validation.
- [ ] **G5:**
  - Validation status passes, and 30 scope tables exist with targets 2026-09 / 2027-03 / 2027-09.
  - 6m/12m diagnostic availability has no `missing_evidence`.
  - FEWS 0m stays `missing_evidence`.
  - Record memory and runtime.

## Step 6 — Publish to `september_manual/scopes/` (gate G6)
- [ ] Copy into a staging sibling, verify hashes, rename into place. Write `scopes/inventory.json`.
- [ ] Check AC1/AC2 with a script: headers equal the h5 root files, roster counts, months/horizons, basis/period strings, populated counts. Save the result to `research/acceptance-check.json`.
- [ ] Add a summary comparison against October 6m/12m: the median absolute difference in polygon scores, expected small but non-zero. This is informational only.
- [ ] **G6:** September root files and the October fallback are unchanged (compare with `preservation-before.json`).

## Step 7 — Docs, specs, archive (gate G7)
- [ ] Update `september_manual/README.md`, `CP/OPERATIONS.md` and `CP/README.md`, plus the three specs (design §7).
- [ ] Build and verify `dist/cloud_pipeline-20261009.tar.gz`. **G7:** verify passes, and the old archive sha256 is unchanged.

## Step 8 — Finish
- [ ] `trellis-check` on the changed code. Run GitNexus `detect_changes`.
- [ ] Commit the task files, code, tests, docs and specs on the current branch. Exclude the pre-existing CRLF-only changes. No push, no audit.
- [ ] Archive the task and record the journal.

## Rollback points
- After Step 3: revert the code commit hunk; no data is touched.
- After Step 4: restore `baseline.json` from `research/preservation-before.json` (old bytes in the old archive) and delete `bootstrap/evidence/`.
- After Step 6: delete `september_manual/scopes/` and the README section.
