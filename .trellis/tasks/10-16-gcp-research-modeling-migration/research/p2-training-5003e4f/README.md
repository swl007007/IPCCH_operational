# IPCCH training chain, local rehearsal (written 2026-10-16 05:11:04 EDT by `date`)

This is local WSL evidence only: no cloud or Vertex job was run, and the MLflow server is the local rehearsal server with throwaway credentials. Native code is at `5003e4f`.

1. **Base inputs** (`manifest-ipcch-base.json`): the raw `IPCCH_2026_completed.csv` and the country lookup, with the hashes recorded in P6 `config/inputs.json`, verified before use.
2. **Linux feature snapshot** (`research_cloud.training.ipcch_features`, H3) built with the P6 low-level builders:
   - 42,695 rows × 561 columns; keys identical to P6 `prepared/keys_h03`;
   - X equals P6 except 12,576 cells in 45 entropy-derived columns, with max absolute difference 1.7e-16 and max relative 7.9e-14 (≤ 512 ULPs in near-cancelling slopes), and no NaN-pattern difference (`features-h03-vs-p6-comparison.json`);
   - this is a declared platform floating-point drift, not a logic change.
3. **Trial** (`research_cloud.training.ipcch_quartet`, config `config-ipcch-h03.json`):
   - two declared development folds before the 2023 holdout; parameters `max_depth=3, rounds=50`;
   - pooled crisis F1 0.8627 (TP 311, FP 47, FN 52).
   - The trial record persists its config, resolved parameters and input identities (`linked-trial.json`).
4. **Portable package** in GeoXGB format (`linked-package.json`), logged as an MLflow artifact.
5. **MLflow linkage:** the run was logged over HTTP by the dedicated job-writer identity (workspace USE). It FINISHED with source-commit and status tags, metrics and artifacts uploaded through the artifact proxy.
6. **Download and replay:** a read-only identity downloaded the package from MLflow, and replay passed 48/48 rows (`downloaded-package-replay.json`).

**Open:**
- the FEWS adapter;
- images and Vertex/HPT execution (paid, gated);
- live Gemini (G10).
