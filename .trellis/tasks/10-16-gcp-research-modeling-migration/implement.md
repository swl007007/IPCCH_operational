# Research migration implementation plan

Status: approved for supervised execution by the active goal. `execution-authorization.md` supersedes repeated per-operation approval gates for in-scope cloud work; preserve operation-level records, budget and technical gates. This is one migration task with independently verifiable phases. If later split, each child must explicitly name predecessor artifacts and acceptance, not rely on tree order.

## Scope and ownership

Planning artifacts live in this task directory. Proposed integration code lives in `research_cloud/` in the native-WSL control-plane checkout; source checkouts supply scientific functions and existing MLflow helpers. Prefer adapters to changes in historical scientific modules. Read the exact code and run GitNexus upstream impact before any symbol edit; report HIGH/CRITICAL results. Run detect_changes before commits. Do not reindex unrelated source repositories just to inspect them.

The main session coordinates, clarifies, updates specs, verifies and commits. Implementation/check dispatch follows the configured Trellis workflow after approval, with curated JSONL context. Respect the enrolled audit executor identity; do not have a substitute session start/close an enrolled run.

## P0 — approval, task lifecycle and isolated workspace

- [x] User's active goal authorizes the reviewed `prd.md`, `design.md`, `implement.md`; execution authorization is recorded separately.
- [ ] Reconcile direct Git status and the existing PROGRESS ledger; preserve unrelated modifications. Commit only approved task planning files before implementation.
- [ ] Recheck `trellis-audit status`. The current repo was enrolled and controller running at planning time. Verify the actual bound Claude executor, exact registered path, task identity and durable state before register/start. Do not reset another run or auto-enroll WSL copies. Start via audit wrapper, then verify base SHA, executor and in_progress state.
- [ ] Create the native-WSL workspace with required filesystem permission; preserve source commits and any intentionally included working diffs. No GitHub push, source deletion or archive availability changes.
- [ ] Record phase receipts in task research and append this task's progress to the repository operational ledger without overwriting others.

Exit: approved spec commit and verified lifecycle/workspace identity. No paid resource creation.

## P1 — concrete inventory and local portability evidence

Depends on P0; satisfies AC1 and prepares AC3/AC6.

- [ ] Inventory the consistent MLflow tracking schema and relationships, artifact locations, registry-linked source paths, all known FEWS research runs and relevant IPCCH source families. Record inspected roots and version/component coverage so "all" has a reviewable boundary.
- [ ] For each version, classify complete weights / retained weights with missing dependencies / missing weights / non-parametric comparator. Include model hashes, fit block/arm/horizon, required maps/transforms, package size and saved-prediction keys.
- [ ] Build FEWS D9 and IPCCH D10 input manifests, using the existing source manifests and actual dependency references. Hash before transfer; do not broaden to the whole source-data archive. Preserve historical oracle/target/vintage distinctions.
- [ ] Freeze reference samples and tolerances before Linux comparison. Assemble package candidates in scratch and test one representative per runtime/family first, then every retained version/component. Do not silently shrink the inventory when one fails.
- [ ] Apply the user's explicit `scen-b43ef6a-v1` exception only to its 18 documented missing regional boosters and affected 3,746/22,872 rows. Preserve all extant materials; keep the run incomplete with missing keys/components and the exception reference, without substituting a full-replay pass.
- [ ] Measure data import/index size, largest package, temporary RAM/disk, source/target row/schema/geometry invariants and minimal training fixture cost. Retain source files and original locks untouched.
- [ ] If an asset is an unavailable Dropbox placeholder, report the exact required file and obtain the appropriate download authorization; do not sweep/hydrate the archive incidentally.

Exit artifacts: `research/input-inventory.json`, `model-inventory.json`, `portability-fixtures.json`, `capacity.json` (proposed future outputs, not present evidence).

## P2 — Linux containers and local integration rehearsal

Depends on P1; prepares AC2-AC5/AC7.

- [ ] Pin the MLflow 3.17 service image and family-specific Linux training images. Include actual scientific dependencies (FEWS requirements currently omit XGBoost). Use a new Linux runtime contract without rewriting historical locks.
- [ ] Add minimal runtime/input/output adapters and download/load entry points. WSL small tests and cloud training use identical image digests. Do not alter held-out cohorts or scientific targets.
- [ ] Rehearse tracking/auth SQLite-to-PostgreSQL copy in a disposable local database. Preserve IDs, full metric histories, relations, hashes/grants and sequences. Test interrupted migration, restart, no-duplicate resume and allowed URI mapping.
- [ ] Adapt existing local artifact/feature-list readers through SDK downloads or bounded staging. Reuse verification primitives; add checks for previously uncovered datasets/logged-model/registry links.
- [ ] Add Cloud Run foreground startup, durable DB/secret configuration, local assistant self-call and explicit read-only-patch startup gate. Tests must show patch/version failure cannot enable unrestricted tools.
- [ ] Implement FEWS/IPCCH small experiment adapters from existing fit/feature code; use a new HPT trial entry with explicit parameters, validation metric reporting, trial identity and failure handling. Keep the FEWS downstream scientific guard.
- [ ] Add only required cost submission/assistant controls and scoped access; avoid a new scheduler, feature store or general cloud SDK wrapper.

Exit: local integration/portability results plus a built, pinned deployment candidate. No claim of cloud compatibility until P4-P5.

## P3 — individually reviewed GCP preflight and resource proposal

Depends on P1/P2 where sizing/configuration is needed; satisfies the AC6 quote gate.

For each operation show project, exact command/request, resource, read/write effect, cost assumption and applicable authorization. All commands explicitly target `food-crisis-modeling-enso`; no global gcloud config change. The active goal already authorizes all in-scope operations; record each operation without repeated user consent. Request approval only if cloud scope would expand. Budget, identity and acceptance gates still apply.

| Sequence | Operation to prepare/review | Gate |
|---|---|---|
| G1 | `gcloud projects describe food-crisis-modeling-enso` | Read-only project identity/access; active-goal authorization applies |
| G2 | `gcloud services list --enabled --project=food-crisis-modeling-enso` | Read-only inventory; cannot infer billing rights |
| G3 | Read relevant billing link/permissions, region quotas and existing SQL/Run/GCS/Vertex resources individually | No broad credential/policy dump; if access denied record it and use administrator evidence |
| G4 | Quote concrete regional SQL/disk/backups, Run, GCS size/downloads, images/builds/logs/secrets and Gemini | Base estimate fits USD 100, including volume and access assumptions; no speculative price presented as quote |
| G5 | Enable each necessary service with explicit `--project` | Existing authorization; inspect already enabled state first |
| G6 | Create scoped identities/IAM and required secrets | Exact grants and secret handling review; no project Editor/Owner for jobs/assistant |
| G7 | Create the selected regional input/artifact buckets and image repository | Exact location, access, retention/soft-delete and capacity cost |
| G8 | Create SQL instance/databases/users/PostGIS | Explicit edition/type/storage/backup/network configuration and cost; no open CIDR access |
| G9 | Upload pinned images and stage data/artifacts; deploy Cloud Run revision | Manifests/digests, byte/cost estimates and authentication behavior |
| G10 | Rebind Gemini and run a bounded read-only query | New-project identity, supported model/region, read-only gate and token budget |
| G11 | Submit bounded CustomJobs and two-trial HPT | Per-job resource/duration/trial/reservation review |
| G12 | Final snapshot/cutover; optional old tunnel/DNS change | AC evidence, writer freeze, fallback and user-reviewed operation |

Candidate APIs: `run.googleapis.com`, `sqladmin.googleapis.com`, `storage.googleapis.com`, `artifactregistry.googleapis.com`, `aiplatform.googleapis.com`, `secretmanager.googleapis.com`, `iam.googleapis.com`; `cloudbuild.googleapis.com` only if cloud builds are selected, IAM Credentials only if the actual auth flow requires it. Service Usage/logging/monitoring prerequisites depend on actual project state. Do not enable unrelated EE, Compute workloads or new data pipelines.

Exit: `research/cloud-preflight.json`, `cost-estimate.md`, individually reviewable operation requests. Lack of billing-account access is a disclosed limitation, not permission to ignore the cap.

Spending baseline update, 2026-10-16: user confirms target-project current-month cost USD 0 to date. This satisfies the initial external spending datum; mark it user-supplied, exclude the unrelated `manuel-remote-sensing` USD 3, and continue quote/capacity and per-operation reservation gates without requesting in-scope permission again.

## P4 — provision and migrate into a staging endpoint

Depends on P2/P3 and corresponding operation approvals; validates AC2/AC4/AC7.

- [ ] Provision only reviewed resources. Use Cloud SQL connector/auth proxy with TLS and scoped identity; no public DB allowlist for arbitrary clients.
- [ ] Import versioned data and geometry; validate source hashes, typed content and export/readback. Produce consistent GCS snapshots.
- [ ] Transfer the rehearsed tracking/auth copy and artifacts. Keep secrets out of evidence and rebind Gemini credentials to the target project.
- [ ] Start the staging MLflow revision with durable backend/auth stores and GCS artifacts. Use its HTTPS URL before any custom-domain change.
- [ ] Reconcile all source/target metadata and relationships, including original timestamps and external descriptors. Register FEWS research records with correct fit/import provenance; never invent missing historical metrics.
- [ ] Test owner/job/read-only/anonymous behavior, assistant allowed/denied calls, restart persistence, cold-start self-calls and largest-package downloads.
- [ ] Record resource IDs, image digests, object generations and verified statuses. A successful deployment alone is not migration acceptance.

## P5 — cloud research and all-version download acceptance

Depends on P4 and job-specific approval; satisfies AC3/AC5.

- [ ] Run one small Linux experiment per data family from approved data versions; log feature recipe/keys and results to MLflow.
- [ ] Run the bounded two-trial HPT smoke on one family. Verify Vertex/MLflow agree on parameters, metric, status and artifact identity. Missing metric or exceeded duration must fail/terminate observably.
- [ ] Download all retained historical packages through the intended user path and run fixed keyed sample inference in native WSL with cloud-pinned runtime; record errors and boundary-only drift.
- [ ] Independently check representative complete packages plus the all-version coverage ledger. Partial component coverage cannot become whole-version pass.
- [ ] Verify future model package download/load, dependency completeness and no Dropbox mounts.

## P6 — final cutover and finish

Depends on P1-P5, all ACs and any final operation approvals.

- [ ] Freeze local writers, create the consistent final snapshot/delta, reconcile again and set cloud as the sole writable tracking authority.
- [ ] Execute AC8 from a clean native-WSL checkout/container with only explicit inputs mounted. Publish a concise researcher runbook: add/change recipe, run local smoke, submit trial, compare, download/load, and recover.
- [ ] Write `research/acceptance.json`, `cutover.md` and final inventory status. Explicitly identify incomplete packages and archive exclusions; any unapproved required incomplete item prevents claiming full migration. The approved FEWS exception remains visibly incomplete and can satisfy migration only after preservation/download checks for all extant materials, never as a full-replay pass.
- [ ] Tell the user which research Dropbox paths can become cloud-only. The user performs that change; do not delete/move original data or stop unrelated operational workflows.
- [ ] Run focused checks and detect_changes, commit only relevant work/evidence, then close through the bound Claude audit session. Verify accepted audit outcome; queued/launched is not passed. Preserve any incomplete evidence.

## Validation commands and evidence

These are planned commands, not executed checks. `RESEARCH_SRC` means the explicit native-WSL source root; `MODEL_PY` the pinned family interpreter/container. Do not use historical Windows locks as permission to run new Linux artifacts under an old identity.

Existing focused tests to reuse where applicable:

```bash
MLFLOW_TRACKING_URI=http://127.0.0.1:TEST_PORT SERVICE_PY -m unittest discover -s RESEARCH_SRC/Food_Crisis_Cluster/IPCCHMLflow/tests -v
MODEL_PY -B RESEARCH_SRC/Food_Crisis_Cluster/FEWSNETGeoXGBExperiment/tests/test_baseline.py
MODEL_PY -m pytest RESEARCH_SRC/Food_Crisis_Cluster/IPCCHGeoXGBExperiment/tests/test_p5_e2e.py -q
MODEL_PY -m pytest RESEARCH_SRC/Food_Crisis_Cluster/IPCCHAlphaEarthExperiment/tests/test_e2e_synthetic.py -q
```

The placeholders above must be replaced with actual isolated test paths/interpreters; they are not ready-to-run commands and must never point to the live local store. Verify test setup before invocation. New integration tests under `research_cloud/tests/` must cover migration relations/history and corruption/resume, permission/assistant failure paths, dataset identity/no-test-set tuning, cost reservation/timeout behavior, and package sample/threshold comparison. Use local fakes/fixtures first; real cloud evidence is limited to explicitly reviewed smoke operations.

Evidence maps each AC to concrete inputs, command, environment/image, result and unresolved gaps. Do not label a skipped runtime, missing secret, unavailable asset or denied cloud API as pass. No full scientific retraining, broad repository test sweep or raw raster download is required.

## Recovery points

P1/P2 operate on scratch copies; originals remain intact. P4 writes a new staging target, so rollback retains local authority. Before final cutover snapshot both metadata and artifacts consistently. After cloud writes begin, preserve/export them before any rollback. Do not automatically delete cloud resources or data on failure; produce a scoped reviewed cleanup request and report continuing costs.
