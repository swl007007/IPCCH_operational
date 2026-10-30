# Focused test history: research_cloud.tests.test_ipcch_final_stage (isolation worktree, uncommitted C1-C5 diff)

Command (all runs): `cd control-plane-h2h8h14 && IPCCH_AE_SRC=$R/sources/Food_Crisis_Cluster/IPCCHAlphaEarthExperiment PYTHONDONTWRITEBYTECODE=1 timeout 590 ~/.venvs/ipcch-validity-idp/bin/python -m unittest [-v] research_cloud.tests.test_ipcch_final_stage`

1. Run 1: Ran 18 tests, FAILED (errors=2), exit 1. Output was shown on the console and not saved to a file.
   - `Contract.test_valid_recipes_and_refusals`: `KeyError: 2` at `schedule_from_config` (`first[h]`). A recipe at H2 without `main_window: false` raised KeyError instead of ValidityError. Fixed by a `main_window and h not in first` ValidityError guard.
   - `Route.test_fit_route_packages_and_replays`: `ValueError: 'oracle_prcp_anom_month_ensmean_o1' is not in list` at `run_contexts -> vf.oracle_completeness(...)`. The fit path still looked up legacy oracle names at H8. Fixed by `oracle_completeness(..., oracle=...)` with `oracle=d.arm != FINAL_ARM`, plus the label `not_applicable_oracle_free` for the final arm; the legacy label is unchanged.
2. Run 2: exit 1 at import. `IndentationError: expected an indented block after 'if' statement on line 374` (ipcch_validity_pooled.py:375), introduced by the guard edit, which dropped the leading indentation. The log /tmp/cp1/final-stage-tests.log was overwritten by run 3; the traceback was observed and is recorded here.
3. Run 3: Ran 18 tests in 12.462s, OK, exit 0. Log: final-stage-run3-ok.log.
