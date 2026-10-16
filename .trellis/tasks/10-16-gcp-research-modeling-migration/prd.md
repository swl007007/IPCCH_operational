# GCP research modeling migration — specification

Status: **approved for execution by the user's active goal on 2026-10-16; lifecycle start pending**. This specification, `design.md` and `implement.md` define the approved scope. See `execution-authorization.md` for the supervisor/executor protocol and superseding in-scope cloud authorization. No deployment, training or upload has occurred at approval.

## Goal

Move FEWS NET and IPCCH research experiments, versioned inputs and MLflow to `food-crisis-modeling-enso`. Researchers must be able to change data, model architecture and feature engineering, train/tune their own code, compare results, and download complete model packages for local geographical analysis. Active development and small tests run in native WSL. Once acceptance is complete, the user can make the relevant Dropbox research archive cloud-only.

## Background and evidence

- The inspected MLflow database has 196 registered names, 242 versions and 242 external LoggedModels across IPCCH and IPCCH forecasting. No FEWS NET registration was found. External descriptors are not loadable packages; some historical weights were intentionally deleted. Evidence: `research/local-baseline-discovery.md:7-14`.
- FEWS NET research inputs and manifest hashes are recorded at `research/local-baseline-discovery.md:25-33`. The identified run demonstrates H4/H8 and four actual cases, not every horizon or complete regional-model portability. The separate operational FEWS NET inputs at lines 37-40 are not the research default.
- IPCCH raw identity, supplemental inputs and feature-recipe distinctions are recorded at `research/local-baseline-discovery.md:18-21,53-56`. A single CSV is insufficient for every family.
- Existing MLflow helpers, persistence/URI limitations, assistant restrictions, training entry points and historical locks are documented with source anchors in `research/migration-mechanics.md`. Some historical environments are Windows-only; AlphaEarth already uses Linux. FEWS NET's ordinary downstream pipeline has an explicit scientific alignment guard.
- AGENTS references a missing `specs/001-cloud-base-input/plan.md`; it was not used as design authority (`research/local-baseline-discovery.md:57`). Cloud resources, prices, IAM and billing linkage remain unverified.

## Requirements and confirmed decisions

| Requirement | Confirmed decision / required behavior |
|---|---|
| R1 / D1 | Migrate **all historical model versions with retained weights, plus future models** in the FEWS NET/IPCCH research scope. Preserve tracking records when weights are gone; disclose missing/incomplete packages. Retraining creates a new version and cannot substitute for original weights. Inventory registry-linked sources and identified unregistered research runs; retain all discovered in-scope versions, including experimental/oracle arms with their labels. |
| R2 / D2 | Migrate research workflows and MLflow. Existing monthly data-refresh, scheduled prediction and delivery services remain outside scope. |
| R3 / D3 | Each retained historical version must download as a complete inference package, load in native WSL and match a fixed small sample of saved predictions under a declared numerical contract. Include preprocessing, feature order, partitions/calibrators and environment information. Full historical retraining is not required. |
| R4 / D4 | Base platform **at most USD 100/month**, including SQL, MLflow, data/models, assistant calls and supporting services. This is a spending constraint, not a verified quote or guaranteed billing stop. |
| R5 / D5 | Training and tuning receive **a separate USD 100/month**. Resource/trial/runtime limits and aggregate estimates must be checked before submission; shared-project charges must not be silently omitted. |
| R6 / D6 | Owner manages/writes; invited authenticated collaborators read; dedicated training identities write their experiments. No unauthenticated experiment, dataset or model content access. |
| R7 / D7 | Migrate Gemini assistant and keep it **read-only**. Preserve command restrictions and permitted MLflow queries; include calls in R4. No cloud administration, arbitrary shell/file access or experiment/model mutation through the assistant. |
| R8 / D8 | **Vertex AI Custom Training + Hyperparameter Tuning for the user's code**; no Google AutoML. Record trial parameters, validation objective, code/image and data/feature identities in MLflow. Never choose hyperparameters on held-out test outcomes. |
| R9 / D9 | FEWS NET default: GeoXGB source set from `scen-b43ef6a-v1/prepared/manifests/sources.json` plus `scen-b43ef6a-v1.actual-inputs-v1/extension_manifest.v2.json`. Verify hashes before transfer. This choice does not restrict future horizons or replace historical input identities. |
| R10 / D10 | IPCCH default: `IPCCH_2026_completed.csv` plus required supplemental sources; generate features **per experiment**. rich561, compact296 and future recipes remain versioned transformations. Keep prepared tables supplying otherwise unavailable static inputs. Separate reported-phase/share-derived truth and ordinary/oracle information. |
| R11 / D11 | User accepts **looser numerical tolerances for historical Windows-to-Linux inference**, and selects **Linux containers as the future experiment baseline**. Preserve original runtime provenance and locks. Cloud Run hosts services; Vertex AI runs training/tuning; WSL uses the corresponding training image. Exact proposed tolerances are in `design.md` for final review. |
| R12 | Cloud SQL/PostgreSQL + PostGIS holds structured base data and spatial references; GCS holds immutable inputs/experiment snapshots and artifacts; Cloud Run hosts MLflow; Artifact Registry holds Linux images. No raw raster migration or new feature-store platform. |
| R13 | Native WSL owns active code, temporary subsets and small tests. Accepted research workflows operate without Dropbox access. The user performs the cloud-only archival change; source deletion, cleanup and Dropbox availability changes are not authorized. |
| R14 | Project is `food-crisis-modeling-enso`. The active goal authorizes all cloud operations within this spec until goal completion. Identify and record operations individually with target, purpose, impact and cost; do not repeat permission requests within scope. Outside-scope cloud actions require approval. Budget and technical gates remain binding; do not change the global gcloud default. |

D1-D11 were agreed on 2026-10-16. The subsequent goal request authorizes executing the reviewed design, including its technical defaults, subject to validation and the stated budgets.

### Confirmed historical exception and spending baseline (2026-10-16)

- The user explicitly accepts `FEWSNET/scen-b43ef6a-v1` as an incomplete historical-run exception to full inference acceptance: 18 original regional continuation boosters are missing, affecting 3,746 of 22,872 predictions in four H4/H8 × June/October 2025 cases. Preserve all extant weights, inputs, code, tracking and saved outputs; migrate a clearly labelled incomplete record with the affected keys and missing-component receipt. Do not report full replay or replace the missing weights by retraining under this identity. This exception is limited to these documented missing components; all other retained materials remain in migration scope. See `research/fews/missing-local-boosters-receipt.md`.
- The user confirms current-month actual spending in `food-crisis-modeling-enso` is **USD 0 to date**. This is user-supplied evidence, not independently verified billing API data. The earlier approximately USD 3 belongs to `manuel-remote-sensing` and is unrelated to this project's budget. Account-level billing visibility remains unavailable; itemized quotes, usage/reservations and both USD 100 monthly envelopes still apply.

## Acceptance criteria

| ID | Observable outcome | Requirements |
|---|---|---|
| AC1 | Inventory identifies retained/incomplete/missing historical packages in the bounded source search, selected input files/hashes, versions, recipes, targets and dependencies. Every retained-weight version stays in the acceptance ledger. | R1, R9, R10 |
| AC2 | Cloud MLflow preserves tracking/registry identities, histories, values, datasets, metric-model links, descriptions and permissions from a consistent snapshot. URI changes are mapped and original references preserved. Existing models and newly registered FEWS NET entries are navigable; retained packages download and hash correctly. | R1, R6, R12 |
| AC3 | Every retained package passes keyed Linux/WSL sample inference with declared tolerance; boundary-only classification differences are enumerated. Missing assets or unexplained discrepancies remain incomplete/failed. The specifically approved `scen-b43ef6a-v1` exception above may migrate as a disclosed incomplete historical record while every extant material is preserved; it is never counted as a full replay pass. Future models include the same portable package contract. | R3, R11 |
| AC4 | Owner/job writes and collaborator reads succeed; collaborator writes and anonymous content access fail. Permissions/data survive a new Cloud Run revision. Assistant answers a research query and rejects prohibited mutations/tools; it cannot start unrestricted. | R6, R7 |
| AC5 | Each data family produces a small research feature set, trains/evaluates through a Linux adapter, logs MLflow results and downloads/reloads its package. A bounded two-trial HPT smoke demonstrates trial metrics/links. This tests platform wiring, not scientific improvement. | R8-R11 |
| AC6 | Before provisioning, an itemized regional quote with volume/usage assumptions fits R4; before jobs, aggregate usage/reservations and conservative job estimates fit R5. Runtime/trial/concurrency and assistant limits are tested. Missing billing visibility is disclosed; estimates are not actual charges. | R4, R5, R7 |
| AC7 | Cloud Run uses durable tracking/auth/artifact storage; future training uses pinned Linux image digests. Cold start, restart, representative largest-package download and small jobs meet service limits. | R3, R11, R12 |
| AC8 | A clean native-WSL checkout fetches inputs, runs a small test, reads MLflow and downloads/loads a historical package with Dropbox paths unavailable. Cutover/fallback instructions name the research archives eligible for cloud-only and exclude unrelated/monthly workflows. | R2, R13 |

## Out of scope

Google AutoML; always-on prediction endpoints or Vertex online inference; migration/rewriting of the monthly operational chain; new EE/AlphaEarth extraction or raw-raster ingestion; full historical training replay; replacing deleted weights by retraining; changing frozen scientific definitions or FEWS downstream review guards; repository cleanup, GitHub publishing or storage deletion; multi-region/HA infrastructure and a new workflow orchestration platform.

## Technical gates and remaining risks

No unanswered user-owned scope questions remain. Execution must resolve retained-weight completeness/size, fixtures, Linux compatibility, PostgreSQL integrity, auth/assistant behavior, project permissions/provider availability, measured capacity and regional costs without weakening acceptance. If a gate cannot fit scope or budget, report the concrete blocker and propose a revised plan before changing behavior or spending.

The design proposes a single-region, non-HA research service with cold starts, brief migration downtime and explicit cost limits. Public documentation was read; no target-project operation occurred. Planning does not establish actual feasibility.

## Workflow and authorization

The user authorized task creation, completed grilling and then authorized supervised execution through the active goal. `design.md`, `implement.md`, `implement.jsonl`, `check.jsonl` and `execution-authorization.md` accompany this specification. Unrelated dirty files are excluded. Use the enrolled Trellis audit lifecycle and verified Claude executor; task status changes only through its start/close workflow. Never substitute another session identity or start an unrelated run.
