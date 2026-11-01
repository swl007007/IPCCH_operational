# IPCCH monthly operations

- **[Production cloud pipeline](cloud_pipeline/README.md)** — incremental IPCCH inputs, generation, inference and publication to the existing production bucket. Follow the [operator manual](cloud_pipeline/OPERATIONS.md) and [all-keep example](cloud_pipeline/selections.example.json).
- **[September manual delivery](september_manual/README.md)** — the historical September CSVs and independently replayable offline package.

Production uses `feisty-flames-511718-d4`, bucket `food-crisis-test-ipcch-data` and pointer `monthly-staging/current.json`. The existing histories, installed models and cloud workflow are reused. Operators choose eleven explicit keep/refresh inputs; automatic source updates and inference follow submission. Execution month is the UTC month at request freeze.

The [IFPRI code repository](https://github.com/IFPRI/MTID-FSP-FOOD-CRISIS-MODEL-INPUT) receives snapshots of `cloud_pipeline/`. This repository remains canonical. Production data, model binaries, filled operator configuration and credentials are not synchronized to GitHub. Historical handover archives do not replace the current operator state or accepted v2 assets.

Completed task evidence remains under `.trellis/tasks/archive/`, separate from operator instructions. The sibling legacy archive is retained for historical source recovery.
