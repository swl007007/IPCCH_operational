# Pinned-code regression receipt — task 10-30

- BEFORE = clean exported snapshot of 99f3ebd (CH-final sources, pre-change); the first attempt that ran inside the worktree during edits is INVALID and preserved as scratch/origin-ablation-20261030/tests-before-INVALID-concurrent-edits.
- AFTER = clean exported snapshot of 868db9f (implementation 7023d10 + smoke test); identities in after-868db9f/code-at-regression.txt (pooled d2c07d7d…, dataset_input 2b74098a…, features eace18fd…).
- Scientific suites: `$HOME/.venvs/ipcch-validity-idp/bin/python -B -m unittest research_cloud.tests.<suite>` (IPCCH_AE_SRC pinned, PYTHONDONTWRITEBYTECODE=1). Tooling suites: `envs/mlflow-svc/bin/python -B -m pytest -q -p no:cacheprovider` (after: origin+CH+GOSIF dataset identity, test_training_validity_integration, test_training_publication; before: CH+GOSIF dataset identity only).

| suite | before 99f3ebd | after 868db9f |
|---|---|---|
| dataset_identity | 6 passed | — |
| test_ipcch_acledagg_hpt | 14 OK | 14 OK |
| test_ipcch_ch_validity | 20 OK | 20 OK |
| test_ipcch_direct_fourclass | 21 OK | 21 OK |
| test_ipcch_gosif_corrected | 5 OK | 5 OK |
| test_ipcch_origin_ablation | — | 17 OK |
| test_ipcch_validity_features | 36 OK | 36 OK |
| test_ipcch_validity_pooled | 46 OK | 46 OK |
| tooling | — | 72 passed |

All return codes 0 (rc.txt in each directory). Checksums: SHA256SUMS.
