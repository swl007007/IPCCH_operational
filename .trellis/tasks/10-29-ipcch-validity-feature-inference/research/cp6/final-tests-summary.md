# CP6 final regression receipt (Executor, 2026-10-30)

- HEAD tested: `bbf21a49fc852ceabf514986aa00de1f5fba258f` (bbf21a4; code identical to d57a3fb - bbf21a4 changed only the executor handoff).
- Command: `cd cloud_pipeline && PYTHONDONTWRITEBYTECODE=1 ~/.venvs/fewsnet-test-lock-20261022/bin/python -m pytest tests -q -p no:cacheprovider`
  (the whole tree: tests/cloud, tests/fewsnet_partitioned_rf, operator, model-pipeline and contract suites).
- Result: **957 passed**, 0 failed, 0 errors (1015 library deprecation warnings), 322.7 s; exit 0.
- `py_compile` (PYTHONPYCACHEPREFIX outside the repo) of cloud/ipcch, cloud/orchestrator, cloud/common, pipeline.py,
  tools/ipcch_finalize_acceptance.py and the research scripts (fews_parity.py, cp5_smoke.py, cp6/*.py): exit 0.
- Matrix checks: `python3 check_matrix.py` -> 116 rows present once, every test reference resolved (524 indexed tests).
- Examples: `operator_examples.py` -> 6 requests + prepare request + deployment config valid (exit 0).
- Earlier whole-tree runs: 954 passed at da1ebd0 (before the initialise route and the R53/R62 fix).
- Logs `final-tests-run*.log` stay local (*.log is gitignored); this summary is the committed receipt.
