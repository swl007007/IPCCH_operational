# CP0 — scope, environment, identities (Executor, 2026-10-30)

Executor: Claude Code, Opus 5.5 (`claude-opus-5-5[1m]`), session 6a490ae1, pane w1A:p2. `task.py current` =
`.trellis/tasks/10-30-ipcch-real-e2e-integration` (bound). No cloud calls, no product edits.
Loaded: execution-protocol.md, research/user-execution-protocol.md, prd.md, design.md, implement.md, implement.jsonl/check.jsonl,
research/grill-second-pass.md, research/automation-evidence.md, spec backend/index + monthly-delivery-contracts,
guides/index + cloud-handover-layout (single-repo; backend spec only).

## Local state
- Branch feat/ipcch-real-e2e-integration, HEAD 1faa6ae. Dirty, not mine (preserve, never stage): AGENTS.md, PROGRESS.md,
  task implement.md, task.json.

## Environment
| Item | Result |
|---|---|
| Frozen venv `/home/swl007007/.venvs/fewsnet-test-lock-20261022/bin/python` | Python 3.12.3; `earthengine-api` 1.7.36 (= `requirements.lock.txt:12`); google-cloud-storage 3.13.0 |
| docker / gcloud / gsutil | present (Docker Desktop and Windows Cloud SDK binaries on PATH); not exercised |
| node | v22.17.0 locally only; image is Python-only (Python port per design) |
| gcloud config | `food-crisis-test` configuration + ADC file present; live validity not checked (no cloud in CP0) |
| Upstream scripts (sibling `IPCCH_shared_folder/seasonal/`) | `01_vi_prcp_et0_update.js` 892 lines, sha256 `b0d64ac0…3c549`; `02_et0_patch32_update.js` 716 lines, sha256 `841ae7f8…7e47`. Both read `INPUT_ROOT=projects/han-sandbox-505315/assets/`, `OUTPUT_ROOT` placeholder, Code-Editor `Export.table.toAsset` (01:146, 02:698) |

## Accepted identities (re-hashed locally in CP0)
| Artifact | Path (R=`/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final`) | Check |
|---|---|---|
| Envelope v2 | R/envelope/ipcch-combination-envelope-v2-accepted.json | sha256 `03b93842…89596` ✔; status accepted; combination `ipcch-validity-h2h8h14-final-20261030`; 527 features; feature order `0ef1ffec…3d69`; scopes 0/6/12 = H2/H8/H14, cutoffs 2025-11/2025-05/2024-11 |
| Package | R/package-build/out-r1/package (93 MB) | package_manifest.json sha256 `18b91d45…5f22` ✔ (= envelope); members not yet rehashed (CP3 via verify_combination) |
| Handoff bundle | R/handoff-build/out-r5-accepted-v1 (2.2 GB) | handoff_manifest.json `e6e3ebc6…97b4` ✔; envelope binds acceptance entries `cb14a956…` and roster `9ff2c420…`/6226. Full large-file rehash not done yet (design requires before install; CP3) |
| Operator config | /home/swl007007/ipcch-operator/food-crisis-test/project.json | project feisty-flames-511718-d4, us-central1, bucket food-crisis-test-ipcch-data, requests food-crisis-test-ipcch-requests, namespace monthly-staging, runtime/workflow SAs as design; image `runtime@sha256:487a2315…7fae` (local record, unverified live) |

## Code anchors confirmed (all match PRD/design)
- `climate_tables.py:191` `_wide_month_matrix` calls `require_admins` on every frame, including PATCH32 (monthly `:233`, seasonal `:366`); `:197` keeps the first same-named column; `TableRefs` `:46`, `YEAR_CHUNKS` ends `(2020, 2026)` `:37`.
- `climate_run.real_providers` `:81` / `real_provider_factory` `:101`: asset_root only, no run-bound table map.
- `entrypoint_v2.real_providers` accepts `deadline_utc` but `context()` (`:173-175`) never passes it; no asset map; no v2 admission reservation (only `os.makedirs(exist_ok=False)` + create-only final status).
- `ee_transport.export_table` is `toCloudStorage` only (`:218`); reservation, durable task id, bounded wait, cancel and deadline reserve are reusable.
- `delivery_job._main` requires `--v2-config` for v2 bodies (`:1041`); `workflow.yaml` run_job argv (`:280-300`) omits it; v2 bodies with no `execution` block route straight to run_job.
- `deploy/Dockerfile` installs code only; `build_context.sh` (9 lines) copies code only; `setup.py` 4h/zero retries (keep).
- `pipeline.py` run/submit builds v1 requests (`:684`, `:769`); status reads `run_status.json`.
- `delivery_request_v2`: `execution_month` explicit; R39 future/older-than-current checks `:152-163`; `derived_months` gives O/targets.

## Planned affected files (unchanged from implement.md table)
climate_tables.py, climate_run.py, entrypoint_v2.py, ee_transport.py, new producer module(s) (Python port of 01/02 + source
hashes), generation.py/climate.py as needed for completeness receipts, delivery_request_v2 builder helper, pipeline.py
(v2 submit/status), workflow.yaml, Dockerfile, build_context.sh, setup.py/deploy_delivery.sh (args), a runtime smoke
fixture provider, deployment JSON; tests alongside.

## Test commands
From `cloud_pipeline/` using the frozen venv:
`PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider <tests>`.
- Focused: tests/cloud/test_ipcch_climate_tables.py, test_ipcch_climate_run.py, test_ipcch_entrypoint_v2.py,
  test_workflow_dispatch.py, test_ipcch_ee_transport.py, test_delivery_request_v2.py, test_ipcch_run_v2.py,
  test_delivery_workflow.py, test_deploy_setup.py, test_operator_cli.py.
- Full: `tests` (from the prior task's final run: 957 passed).
- Later checkpoints keep the full log and exit code.

## Findings / blockers
1. **Smoke config (CP3).** `load_config` requires a smoke section, but the only fixture provider is
   `tests/cloud/ipcch_smoke_fixture.py:171`, which is not in the image. Per Supervisor: add a minimal isolated runtime fixture provider/build path, with no copied tests and no real-history aliasing.
2. **Wrong operator `work_dir`.** project.json `work_dir` points at `…/food-crisis-test-fews-retrain-20261022/operator-state`. The v2 deployment JSON (roots/store_roots/trusted_prefixes/installed/export_root/smoke root) does not exist yet and must be authored in CP3. Smoke needs a non-nested existing location: open until preflight (CP5).
3. **han-sandbox dependency.** Producer dependency reads under the Cloud Run identity and current deployed job/Workflow/current pointer are unverified (CP5 live).
4. **Handoff bundle in the image.** It is 2.2 GB, so the build context and image will be around 2.5 GB or more. The local Docker Desktop build/push is feasible but untested; if a limit hits, report and revise (design).
5. **Stale AGENTS pointer.** `specs/001-cloud-base-input/plan.md` is missing; already noted in implement.md.

No scope or permission blocker for CP1.

## Baseline offline suite — PENDING
Full `tests -x` run started before any edits (PID 230330), output `research/cp0/baseline-tests.txt` (tail-only; the
pipeline masks the exit code, so the result is the pytest summary line). Result appended when it settles.

Settled: PID 230330 ran to completion (warnings summary printed, no short failure summary in the tail), but `-q -q`
suppressed the pass-count line, so that run is **inconclusive**, not a pass. A single rerun (no `-x`, single `-q`) now
keeps the full log `baseline-tests-full.log` and exit code `baseline-tests-exit.txt`.
