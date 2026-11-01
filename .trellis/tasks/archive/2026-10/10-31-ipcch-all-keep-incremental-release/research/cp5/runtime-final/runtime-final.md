# Runtime-final operational evidence: ipcch-real-fe7282ef75e747fd / oct-delivery-625sk

Read-only reads at 2026-11-01T03:43-03:45Z.
- 10 cloudop-logged reads, each run once, guarded, child exit 0: `cloud-operations.jsonl`.
- Full stdout and stderr are in `outputs/`.
- Local summaries are guarded and child exit 0: `runtime-summary.json` and `log-text-scan.json`.
- The exit-1 results for locks and hold mean the objects are absent (no objects / 404).

**Disclosures:**
- My shell wrapper's summary printing failed on an unquoted path; the reads themselves ran once and are not repeated.
- The guard's own stdout is kept as `*.guard-stdout`.
- The first summary attempt failed on a relative working directory; it is kept as `11-runtime-summary.INTERMEDIATE-relative-cwd.*`.

| Item | Evidence | Result |
|---|---|---|
| Execution | `01-exec-describe.json` | `oct-delivery-625sk`, creator monthly-workflow SA. Start 02:29:44Z, completion 03:29:41Z. Condition Completed=True, "Execution completed successfully in 59m57.44s". succeededCount 1, failed 0. Per-task exit code not shown by describe; the log has "Container called exit(0)" at 03:29:38Z |
| Pinned runtime | same | Image `…/runtime@sha256:acc3e467…`; SA `monthly-runtime@`; 8 CPU / 32Gi; timeout 14400 s; maxRetries 0; taskCount 1; args `--v2-config /opt/ipcch/deployment.json`, request #1793500174046456. `pins_ok: true` |
| Logs | `02-exec-logs.json` (253 entries) | Severity: 251 DEFAULT, 2 INFO; 0 WARNING/ERROR (see the text scan below) |
| Locks | `03-locks` | No objects under `locks/` |
| Hold | `04-hold` | `maintenance/hold.json` 404 |
| Active executions | `05`/`06` | oct-delivery latest three are 625sk (succeeded), 4jkcj (failed attempt 1) and t6vlm (10-31 succeeded); none running. monthly-prepare: 0 listed |
| Workflow | `07-wf.json` | Latest three oct-delivery-trigger executions are all SUCCEEDED, including 53f02176 for this run; none ACTIVE |
| Batch | `08-batch.json` | 0 jobs listed (gcloud warned the filter key was absent from every resource, which is consistent with an empty list) |
| Current | `09-current-describe.json` | `gs://food-crisis-test-ipcch-data/monthly-staging/current.json#1793503777656101`, 231 B, md5 `9hKTWU42AwojhqEuzFC2HQ==`, crc32c `pxv20g==`, updated 03:29:37Z. Equals the readback-pinned generation, whose content names release `ipcch-real-fe7282ef75e747fd-ipcch` #1793503777593004 |
| GPP | `10-ledger.csv`, sha equal to the post inventory (`a818e09c…`) | Ledger v8 → v17 (+9 rows, checked_at 2026-11-01). Nine probes 2026-01..09 → `unpublished`, HTTP 404 at the GOSIF-GPP_v3 Mean URLs. `history__GPP_mean` stays v1 (coverage end 2025-12); GPP features at O are NaN as optional-missing (R65 warning) |
| Nightlight | inventory post | `history__nightlight_mean` v1 → v2: 1,244,388 → 1,250,614 rows (+6,226 = roster × 2026-09); record months `[2026-09]`, `filled_unpublished: 0`; gaps.nightlight `[]` |

**Log warnings found by text scan** (no severity set; no ERROR, traceback or retry text):
- 02:57:31Z (×2): "httplib2 transport does not support per-request timeout. Set the timeout when constructing the httplib2.Http instance."
- 03:06:31Z and 03:06:43Z: pandas `PerformanceWarning` "DataFrame is highly fragmented" at `/app/cloud/ipcch/climate_tables.py:313`.
- The fifth hit is the status JSON line `"failed_operation": null` (false positive).
- Neither warning changed the run status. No impact assessment beyond that is claimed.
