# Task 10-31: operator handoff and AC matrix (Executor evidence; Supervisor owns acceptance and closure)

**Use the corrected DA2 wording.** `cp5-result-corrections.md` supersedes the DA2 lines of `cp5-result.md`.

## State after this task

| Item | Value |
|---|---|
| Live current | `gs://food-crisis-test-ipcch-data/monthly-staging/current.json#1793503777656101` → release `ipcch-real-fe7282ef75e747fd-ipcch` (record #1793503777593004) |
| Publication | M 2026-11 / O 2026-09; H2 → 2026-11, H8 → 2027-05, H14 → 2027-11; 6,226 rows each; 527 features |
| Members | fewsnet (inherited literally from pointer 1793461128385732) and ipcch (this run). Contract activation is CARRIED from 2026-10-31 (run 522b…), not newly activated |
| Run | `ipcch-real-fe7282ef75e747fd`, execution `oct-delivery-625sk` (59m57s, exit 0), image acc3e467, product 115798f |
| Failed attempt (preserved) | `ipcch-real-9eee4305db494a35` / `oct-delivery-4jkcj`: EE root 404 before any export; its ACLED refresh is retained as v2 |
| Root recovery | job `ipcch-ee-root-check-20261101` created the feisty EE asset root once (CP3) |
| Live idle state | No locks, no hold, no running execution, workflow or Batch job (03:43-03:45Z) |
| Retained store (56 tables) | 13 monthly climate tables v1 → v2 (+2026-09); nightlight v2; GPP ledger v17; acceptance_manifest v7. The 11 manual inputs are unchanged (ACLED v2 is the keep baseline) |
| EE assets created by this run | 7 tables under `projects/feisty-flames-511718-d4/assets/*__M202611_ipcch-real-fe7282ef75e747fd_165617d8`. 6 are consumed; PERSIANN is unconsumed, explained by source-calendar incompleteness. No deletion |

## Operator notes for the next month

1. **GPP.** GOSIF-GPP 2026-01..09 all returned HTTP 404 "unpublished"; GPP features at O stay NaN (optional-missing, R65). Coverage ends 2025-12. The run did not fail on this.
2. **bbg_soybean_oil.** The kept input covers only through 2026-07, so its features at O are NaN (optional-missing). Refreshing it would be a manual research-input action.
3. **PERSIANN.** No complete source days for 2026-08/09 (`days_present` 0), so those months are masked and not consumed. spi03/spei03 used CHIRPS and ERA5LAND. This is source-calendar unavailability, not an export failure.
4. **Fill-audit size.** The delivery fill audit is large: 810 MB merged; IPCCH sidecar 78 MB.
5. **Log warnings.** These were non-fatal and need no action now; no assessment beyond that is claimed:
   - httplib2 "per-request timeout not supported" (×2);
   - pandas fragmentation `PerformanceWarning` (×2).
6. **Retries.** A new month needs a new submit with a fresh M. Do not resubmit this run ID. Under this task, no third attempt was authorized.

## AC matrix

| AC | Status | Evidence |
|---|---|---|
| AC1 Bound submission | **Met** | Attempt 1 (refresh plus 10 keeps) is preserved in cp1/cp2. The D5 request #1793500174046456 (b0f8b507) declares all 11 keep, real mode, the pinned image and models, and M 2026-11 / O 2026-09. It was submitted once, after the CP3 root check passed (`cp4/run/*`, `cp4/cloud-operations.jsonl`: the only `scope=mutation` record is the one submission) |
| AC2 Real production | **Met** | Nonempty demand: 3 table bases at 2026-09; 13 monthly bases need 2026-09. 7 run-specific `table_to_asset` tasks completed with operation names and no Tasks-panel action. Destinations were read back and validated (`lineage.json`: receipts == jobs, receipts join completed tasks, no duplicate task or destination) |
| AC3 Consumption | **Met** | Produced IDs are linked to the consuming spi03/spei03/evi_anom v2 versions, which appended 2026-09 from this run. Batch `retained_inputs` equals the post HEADs (43); batch → inference (6,226 per horizon) → current ipcch member (`lineage.json`, `witness-links.json`, `post-real.json`). PERSIANN is unconsumed, with an explained disposition |
| AC4 Live data contract | **Partial under D2 (DA2 not passed as a whole)** | Observed: the PATCH32 exact 32-ID set; 93 null-primary/finite-patch candidates; saved spei03 at O finite for 21 of 32 codes and NaN for 11; VI units (3-admin recompute equals saved values; no scaling); explicit nulls; wholly omitted fields from incomplete source calendars, correctly classified as availability, not export failure. Pending under D2: finite-primary preservation, per-row omitted keys, other unseen shapes. PATCH32 evidence is source-level, not an SPEI replay. Operator EE read; identity not established |
| AC5 Publication | **Met** | `post-real.json`: 27/27 checks, including verify_delivery, record_is_this_run, previous_is_pre, raw headers, the 527-feature order, 6,226 rows per horizon and the targets. The FEWS member is fully equal to the predecessor's. Current generation re-confirmed live |
| AC6 Source actions | **Met** | Attempt 1's ACLED refresh evidence is preserved (`cp2/failure-source-checks.json`). For D5, ACLED v2 and the 10 other keeps are unchanged against the recovery pre-snapshot. The ACLED features declare dependency only through 2026-08, so the October refresh is outside the cutoff (`acled-cutoff.json`; provenance evidence, not a replay). Automatic updates are measured separately: 13 climate bases +6,226 rows each; nightlight +6,226; GPP 9 probes all 404 with no publish; warnings GPP_mean and bbg_soybean_oil coverage |
| AC7 Honest bounded outcome | **Met** | Attempt 1's failure and reconciliation are preserved. Every INTERMEDIATE failure is kept (helper/test environment slips, the string-version compare, the relative working directory). The run status, execution, logs and final idle state are reconciled (`runtime-final/`). One D5 attempt, no retry |
| DA1 | **Met** (AC2 + AC3 + AC5, with AC1/AC6/AC7) | Real producer exports → climate reads → retained append → feature consumption → full-roster inference → current |
| DA2 | **Partial under D2** | As AC4; never labelled passed as a whole |

These statuses are the Executor's evidence assessment; the Supervisor decides acceptance.

## Evidence index

- `cp5/`: `cp5-result.md` (frozen) and `cp5-result-corrections.md` (supersedes its DA2 lines); `SHA256SUMS.final`; `SHA256SUMS.supplement`.
- `cp5/runtime-final/`: `runtime-final.md`; `SHA256SUMS`.
- Large local-only cache, recommended not committed: `cp5/batch-feature_provenance.csv` (77.8 MB).
