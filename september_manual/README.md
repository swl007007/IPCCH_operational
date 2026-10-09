# September manual delivery

Final September v3 CSVs are in `fewsnet/` and `ipcch/`. The independently replayable offline package is `webapp_model_bundle.tar.gz`.

To inspect or use the full package, extract it into a new empty directory and follow its bundled README:

```bash
mkdir september-bundle
tar -xzf webapp_model_bundle.tar.gz -C september-bundle
```

Its offline replay has already been verified. This reorganization preserved the accepted archive/results and did not repeat inference. `inventory.json` records hashes and sizes of retained local files. `original_metadata/` preserves the historical full-delivery metadata; it describes the original expanded tree rather than this compact folder. `inputs/` and `reports/` retain the small comparison evidence.

This entrypoint is the accepted manual delivery, not a raw-data assembly workflow. Ongoing monthly cloud preparation, migration and its one-time historical baseline live in the separate `cloud_pipeline/` handover. Original raw assembly scripts are preserved in the external legacy archive and are not required to consume or replay this package.

## September-origin 6m/12m (`scopes/`)

Added 2026-10-09. `scopes/` holds FEWSNET and IPCCH results for origin (feature month) 2026-09: `6m/` targets 2027-03 and `12m/` targets 2027-09, each with `fewsnet/` and `ipcch/` tables that use the same file set and columns as the h5 tables above. `shared/` holds the population references and polygon geometry. `reports/` holds the delivery, assembly and diagnostic-declaration reports and the 6m/12m diagnostic availability. `scopes/inventory.json` records hashes, sizes and run provenance. The h5 root files are unchanged.

The six accepted 0/6/12 model packages scored these results through the cloud delivery code in `cloud_pipeline/` (run `sept-6m12m-20261009a`). No model was retrained. Inputs were the October prepared remote-sensing snapshot `full-window-20261008c` (every observation month is 2026-08 or earlier; GOSIF ends 2024-12) and the October retained ACLED/WFP snapshots (keep/keep), filled under the cloud causal-fill contract. That snapshot is labelled origin 2026-10. `reports/september_run.json` records the label difference and how it was handled.

Confidence bases:

- FEWSNET 6m: `h6_validation_error_proxy_stage3_fs2_lag8_2021_2024`. FEWSNET 12m: `h12_validation_error_proxy_stage3_fs3_lag12_2021_2024`. These are saved errors from Stage3 research runs with 8- and 12-month lags over 2021-02..2024-10, computed with the h5 proxy method. They are not held-out errors of the delivered packages. Five roster polygons have no Stage3 history and stay blank with a reason.
- IPCCH: `training_resubstitution` (2014-01..2026-04). The delivered scope models were replayed on their original training rows, so this evidence is in-sample and optimistic. Maximum-phase fields use the h5 complete-month residual-transfer bootstrap (seed 20260923, 10,000 replicates per horizon). Ten countries have no complete history and stay blank.

The confidence flags describe historical error of the stated evidence basis. They do not measure forecast accuracy for the 2027 targets.

Limitation: all inputs end by 2026-08, and the IPCCH packages use only same-month features with no lag or calendar terms. As a result, the IPCCH 6m/12m scores are numerically identical to the October-origin scores; only the target labels differ. FEWSNET scores do differ from October because its features include lag and window terms. The median absolute difference in `probability_crisis` is 0.03 at 6m (maximum 0.28) and 0.09 at 12m (maximum 0.53).

There is no portable replay bundle for these scopes. The run's 0m tables and its feature-fill audits are kept outside this folder, and `scopes/inventory.json` records their hashes.

Object references such as `gs://sept-local-baseline/...` in `scopes/reports/` (including the `evidence_ref` column) point to a local stand-in bucket. That bucket does not exist in cloud storage. These references identify files by sha256, and the files behind them are the `cloud_pipeline/bootstrap/` baseline and evidence files with those hashes.
