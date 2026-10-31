# Which summary is final

- `final-totals.txt` is the FINAL CP3 suite summary: 18 files, 285 passed, every exit 0 and child 0.
- `runs-summary.INTERMEDIATE-before-delivery-workflow-fix.txt` was renamed from `runs-summary.txt`; its bytes are unchanged (sha256 below). It is stale.
  - It was written before `test_delivery_workflow` was re-run. That is line 7, `exit=1`, the stale render map that lacked `v2_config`.
  - The failed run's evidence is kept as `runs/test_delivery_workflow.INTERMEDIATE-stale-render-map.{log,exit}`.
  - The final passing run is `runs/test_delivery_workflow.{log,exit}`.
0736015e9786406649b404737261250dd53ff5003d44dfe27421ab27929e1941  runs-summary.INTERMEDIATE-before-delivery-workflow-fix.txt
