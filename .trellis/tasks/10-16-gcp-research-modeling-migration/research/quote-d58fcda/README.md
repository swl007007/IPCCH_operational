# Revised quote at native d58fcda (supersedes quote-7d83228)

| Pool | Monthly | One-time | First month | Envelope |
|---|---|---|---|---|
| platform | 79.97 | 12.20 | 92.18 | 100 |
| training | 0 | 1.06 | 1.06 | 100 |

**Scope.** These are gross list-price estimates for the resources of this migration in `food-crisis-modeling-enso`:
- **Prices:** catalog effective 2026-10-15T07:00:00Z; free tiers and credits are not subtracted.
- **Billing actuals:** not available yet (no billing export was read), so nothing here is billed spend.
- **Not a project-wide cap:** the project is shared, and the 100 USD envelopes and the ledger cover only this migration's operations. Nothing here caps the whole project.
- **Excluded:** the Earth Engine bucket `food-crisis-modeling-enso-han` and the EE workload. They were not inspected (the actuals collector skips the bucket by name).
- **Earlier baseline:** the initial user-supplied 0 spend baseline remains the evidence it was; this quote does not revise it.

**Measured inputs** (`g12-cutover/actuals/actuals-1155.json`, metadata-only reads; supervisor reconciliation S89):
- **GCS live:** 110.54 GiB, made of 106,113,317,859 B from 156,113 transferred objects plus 12,578,866,404 B from 15,477 publication copies (server-side copies of the packages into the MLflow artifact paths). Quoted at 122 GiB-month with a 10% soft-delete/growth margin (+0.26 vs 109).
- **Class A:** 171,590 logical writes, publication copies counted once. Quoted at 172k one-time (+0.01).
- **Class B:** acceptance reads were about 414k: upload reload and verify 312,226, publication verify 30,954, archive downloads 55,964, package downloads 15,477. Quoted as a one-time 400k plus the monthly 100k, so 500k in the first month (indicative, +0.16).
- **Direct GCS downloads:** scen archive 42.23 GiB (43 GiB line, unchanged). New 3 GiB line (+0.36): AC8 clean-run input reads of 2.34 GiB (6 objects, sizes from object metadata) plus confirm-onset 0.06 GiB.
- **Proxied package downloads:** the full 223 came to 11.71 GiB. Pilot, trial, HPT and AC8 downloads add 0.11 GiB. Together they fit the 12 GiB line.
- **Secret Manager:** 16 secrets, 18 ENABLED versions (+0.12). The steady state is 17 after the temporary admin's versions are destroyed.
- **Artifact Registry:** 7 digests in 4,105,870,693 B (3.82 GiB): the original 5, plus service 4cc5d93b and training-ipcch 6ad7f46c. The 11 GiB allowance is kept.
- **Cloud Build:** 7 successful builds (18.64 min) plus 1 failed (~1.93 min) = 20.5 min, inside the 120 min allowance.
- **Cloud Run:** max 1 instance, concurrency 40, 1 vCPU / 2 GiB, CPU only during requests (`cpuIdle`). Matches the quoted basis.
- **Cloud SQL:** db-g1-small, 30 GB, Enterprise, zonal, backups on, PITR off, public IPv4 enabled. Matches.
- **Training:** the 7 jobs actually submitted, at their reservations, total 1.0555. These are estimates; every ledger actual is NULL. The two feature-snapshot jobs of earlier quotes did not run on Vertex.

**Ledger:** platform 77.10 reserved over 16 operations, 0 actual. `G12-revised-quote-amend-2026-10` (0.79) records the storage, Class A, Class B and download deltas. That reservation is **post hoc**: those reads and copies had already happened. Still unreserved: contingency 10 and logging 5.10.
