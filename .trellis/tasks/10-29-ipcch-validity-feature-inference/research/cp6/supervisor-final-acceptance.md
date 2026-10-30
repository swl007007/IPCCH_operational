# Supervisor final acceptance — 2026-10-30

Accepted by Codex Supervisor under execution-protocol.md. Implementation/evidence head: `0d484d8`; executable code last changed at `d57a3fb`; full regression ran at `bbf21a49fc852ceabf514986aa00de1f5fba258f` (same code). Executor: Herdr w1A:p2, Claude session `6a490ae1-ee00-43f9-bdfc-c887c9816c09`.

## Decision

CP0–CP6 are accepted for the scope in execution-protocol.md: real H2/H8/H14 model handoff, operational implementation, local real-input compatibility evidence, fixture-only smoke with the actual models, publication/cutover tests and operator handoff. No known blocking finding remains. Native task finish/archive and session recording are released; no Trellis Audit, automatic merge, deployment or live-current mutation is authorized by this acceptance.

## Evidence checked

- CP0–CP2 prior checkpoint decisions remain authoritative. Accepted combination `ipcch-validity-h2h8h14-final-20261030`, envelope SHA256 `03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596`, package manifest prefix `18b91d45`, 527 ordered features and real roster 6,226. Real weights for H2/H8/H14 have cutoffs 2025-11/2025-05/2024-11. No extra refit or performance gate.
- CP3/CP4 requirement and fix evidence is linked in `cp6-evidence-matrix.md` and the existing supervisor review files. All R1–R66, AC1–AC40 and FCC1–FCC10 appear once (116 rows); named test references resolve. Independent bounded checks found no remaining data/model, inherited-member, CAS, shared-lock, legacy cutover or smoke-isolation defect.
- CP3 local real-mode integration: 6,226 finite predictions per horizon from accepted inputs/package. Historical float32 features and raw model scores match; documented float64 coordinate/ACLED parse differences remain. These are local compatibility checks, not live provider validation.
- FEWS actual-scorer parity (0d26d7f, 6598a1d): real 12-area KE/UG inputs and models, keep/refresh/split refresh. All 15 scope tables are byte-identical; 28/31 delivery files match exactly, remaining three match after output-root provenance normalization. Split inference acquires nothing. Synthetic local rasters and subset normalization remain disclosed.
- CP5 b3b5dd2/da1ebd0 run6: actual accepted models with three adjacent fixture areas across two countries; generation-only, named-batch inference, combined run, isolated current replacement, stale-CAS/generation/inference failure preservation. All 12 checks true; calibrated Python read spy recorded 9,712 calls and zero forbidden touches. Native-library filesystem access is not intercepted.
- Final CP6 finding repaired in d57a3fb: R53/R62 batch warnings and coverage cutoffs now reach hash-bound prediction metadata, including inference-only. Independent publication/tamper plus initialization checks: 3 passed. Earlier independent ACLED/climate/assembly/request checks: 46 passed; Executor focused repair suite: 52 passed.
- Full locked-environment `cloud_pipeline/tests`: **957 passed, exit 0**, 322.69 seconds, 1,015 warnings. `final-tests-summary.md` and local `final-tests-run3.log` record the run. Compilation checks passed. No new code after the tested revision.
- Operator examples: six requests pass structural and namespace checks; FEWS prepare body and nested admission checked. Generated FEWS snapshot prefix is permitted narrowly, smoke prefixes unchanged. Runbook documents exact initialization boundary, source recovery, GPP lag, future year dummies, WFP HDX semantics and private climate dependencies.
- Working tree was clean at 0d484d8. Final administrative acceptance/checklist/archive changes follow this code/evidence head and require a final clean-state readback.

## Artifacts and retained limits

Accepted package and bundle remain under `/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/`: `package-build/out-r1/package`, `envelope/ipcch-combination-envelope-v2-accepted.json`, and `handoff-build/out-r5-accepted-v1`. CP5 artifact directory: `cp5-smoke/run6`. Local FEWS parity: `/home/swl007007/scratch/ipcch-fews-parity/`. Committed receipts, digests and scripts identify large local artifacts; ignored verbose logs are not represented as committed payloads.

Live private EE access/exports, full-area cloud acquisition, real GCS initialization, production publication/activation, deployed container/environment, real FEWS acquisition, actual Google Workflows execution and production-state rollback remain DEFERRED, exactly as allowed by execution-protocol.md and listed in the matrix. Runnable fixture placeholders are not upstream baseline delivery. Existing source recovery tag `backup/ipcch-pre-refactor-20261030` names `422f92123932aabfc59b649b3faa90b6d4c0b6f4`; this proves source recovery, not cloud-state recovery. Scientific outputs are not claimed to improve out-of-time predictive performance.
