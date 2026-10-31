# Real run ipcch-real-522b30030f944868: progress record 1 (15:31-15:33Z; actual durable objects, not elapsed-time inference)

- **Execution** (Supervisor readback, `cp5/supervisor-real-execution-progress.json`): `oct-delivery-t6vlm`, image `acc3e467`, SA `monthly-runtime`, `--v2-config /opt/ipcch/deployment.json`, 8 CPU/32 Gi/14400 s/maxRetries 0; runningCount 1.
- **Runtime logs:** 0 entries at 15:31Z (`cp5/real-logs-progress-1.json`). The entrypoint's output is emitted at the end, so the logs give no progress yet.
- **Durable objects created since 15:21Z** (`cp5/real-progress-objects-1.json`):

| Time (UTC) | Object |
|---|---|
| 15:21:13 | `inputs/v2/<run>/acled/acled_regional_aggregate_f2f3.csv` (38,765,520 B), the submit upload |
| 15:21:17 | `dispatch/<run>/claim.json`, the Workflow claim |
| 15:22:57 | `locks/ipcch`, `runs/<run>/v2_reservation.json` (reservation and lock) |
| 15:23:13 | `ipcch-v2/real/acled_agg_weekly` HEAD + version 000001 (14,891,709 B): the ACLED refresh appended, first ACLED history |
| 15:23:18 | `acceptance_manifest` version 000002 |
| 15:27:06–09 | `gpp_availability_ledger` versions 1–8 + HEAD: one ledger write per probed month |
| 15:27:14 | `acceptance_manifest` HEAD → version 000003 |

- **GPP: actual public HTTPS from Cloud Run** (`cp5/real-progress-gpp-ledger-1.txt`). The ledger has 8 rows; 2026-01..2026-08 are all `unpublished`, each with evidence `{"url": ".../GOSIF_GPP_2026.MMM_Mean.tif.gz", "http": 404}` and checked_at 2026-10-31. These are real HTTP responses received inside the job, so egress works. No GPP month was published, and nothing was downloaded.
- **Not yet observed:** climate/production demand, the feature batch, inference, publication. Those come from the final run status and readback.
