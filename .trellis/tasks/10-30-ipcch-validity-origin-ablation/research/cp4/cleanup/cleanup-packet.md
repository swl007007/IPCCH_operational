# Annual-weight cleanup packet r1 — task 10-30 (R9 / A6; NOT released)

Removes ONLY the temporary annual-context booster files of the three origin-ablation runs, after their replays passed and the
final read-only packet passed (final_pass true). Retained: the three holdout packages (published LoggedModels; untouched), the
annual package.json (sha256 of every removed file), records, routing, reference sample, loader, every keyed prediction,
membership, config, metric/report file and receipt; nothing in MLflow; no CH-final/baseline object.

Tool: `staging/ipcch-origin-ablation-20261030/final-packet/cleanup_annual_weights.py` sha256 26eb5d2392d52f71b0c0942bf72698e9426b3a59601679c73601117b40648741 (with replay_check.py 3d30a801ee7e5c1921f55e2e96f7011afb988b39b2cbd07ef502d2e9502c91f6);
source bound to this task's ledger records (final.json SUCCEEDED == submit.json name, display name, task/horizon labels);
refusal tests 13/13 (`final-packet/logs/test_cleanup_and_replay.log`).

Dry run (local, no cloud call): `research/cp4/cleanup/00-dry-run.json` sha256 a0b255c8d2a47346e17c2ec3720ab432c25ea537e2b33d29c1885c3d6292019a — 32 targets, problems []:
- H0 job 2842603222726606848: `gs://food-crisis-modeling-enso-research-artifacts/trials/ipcch_validity_pooled/2842603222726606848/trial-0/gcs-only/annual-package/weights/{h00_main_2023,h00_main_2024,h00_main_2025}/q{2,3,4,5}.ubj` (12)
- H6 job 2596031143128072192: `…/2596031143128072192/trial-0/gcs-only/annual-package/weights/{h06_main_2023,h06_main_2024,h06_main_2025}/q{2,3,4,5}.ubj` (12)
- H12 job 3377405678476853248: `…/3377405678476853248/trial-0/gcs-only/annual-package/weights/{h12_main_2024,h12_main_2025}/q{2,3,4,5}.ubj` (8)
plus the same 32 local harvest copies under `scratch/origin-ablation-20261030/harvest/formal-hXX/trial-0/`.

Command (once, cwd control-plane-origin-ablation):
`IPCCH_ORIGIN_CLEANUP_CONFIRM=r1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $W/envs/mlflow-svc/bin/python -B $F/cleanup_annual_weights.py --execute --out "<task>/research/cp4/cleanup/01-execute.json" > "<task>/research/cp4/cleanup/01-execute.log" 2>&1`
It recomputes every precheck (bound source, harvest listing generation/size/CRC32C, local bytes == package.json, bound passed
annual replay) before any delete; deletes with if_generation_match (retry=None), reads each back as NotFound before removing the
local copy; any unconfirmed delete stops. Cost: deletes are free class operations (within the held platform line).
After: a local listing check that every retained file still exists and the holdout package still verifies.
