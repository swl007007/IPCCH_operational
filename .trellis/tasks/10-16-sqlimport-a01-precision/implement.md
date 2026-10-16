# Implementation plan

- [x] Commit this spec/plan (registered, 427e12d), then `trellis-audit start sqlimport-a01-precision` from the bound Claude session (ordinary start; no `--remediation-for`). Verify run, base and executor. *(Run 3d5262d6, base 427e12d. The start needed deviation 2, a native start plus `resume-start`; disclosed in prd.md and `research/lifecycle/a01-start.txt`.)*
- [x] Native branch `sqlimport-a01-precision` (from `gcp-research-migration` 6ee56f5):
  - write the failing tests first (pure `infer_types` + local-PG round trip, both orders) and confirm they fail at 6ee56f5;
  - implement the `infer_types` change;
  - confirm the new and existing sqlimport tests pass (RC_TEST_PG = the disposable rehearsal cluster). *(Native 1d9c21d. Red: `research/tests/pytest-prefix-6ee56f5.txt`, 3 failed / 10 passed. Green: `pytest-fixed.txt`, 19 passed.)*
- [x] Exposure scan (R5): run read only over the 53 inventoried sources; write the receipt to the task research dir. *(`research/exposure/`: 53 files, 13,763,421,380 B, 0 candidates, 0 in every class, 429 multi-line records tokenized.)*
- [x] Decision (R6): *no affected column; no cloud repair (`research/exposure/decision.md`)*
  - no affected column → record "no cloud repair needed";
  - otherwise → a scoped repair plan, executed only after supervisor review, with before/after evidence.
- [x] Merge native into the registered lineage *(b93f9c8; tree bd2d781d = native)* (`--no-ff --no-commit --no-autostash`; only `research_cloud`). Verify the trees are equal and the 73 pre-existing paths unchanged; run staged `detect_changes`; commit.
- [ ] Supervisor patch/test/exposure review. Only then `trellis-audit close`:
  - the same 73-path stash authorization applies if needed;
  - restore and hash-check against `scratch/pre-close-dirty-byte-backup/manifest.json` after every attempt.

Validation commands:
- `PYTHONPATH=. envs/mlflow-svc/bin/python -m pytest -q research_cloud/tests/test_sqlimport.py`, with `RC_TEST_PG` set for the PostgreSQL tests;
- the exposure script under `research/`.
