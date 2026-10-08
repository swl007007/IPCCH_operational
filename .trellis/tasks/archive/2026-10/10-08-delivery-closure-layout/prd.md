# Two-entry delivery closure and repository cleanup

## Goal
Hand over the same GitHub repository to operators who will use their own GCP project and buckets. Expose exactly two public entrypoints: the final September manual delivery and the ongoing cloud pipeline (including migration and October fallback). Each documented operation must be supported entirely by its deliverable plus explicitly configured external services/dependencies.

## Confirmed decisions
- User requested grilling before implementation and approved task creation.
- Archive unrelated content in sibling `../legacy_archive/`, preserving a move inventory rather than deleting it. Archival changes organization, not total disk use.
- September entrypoint means final delivered results and independent offline replay; the original raw-to-delivery manual assembly workflow belongs in the external archive.
- Cloud entrypoint serves ongoing monthly operations and migration to an operator-owned project/buckets. Keep the shared GitHub repository. "CI/CD" means the existing manifest-triggered Eventarc -> Workflows -> Cloud Run automation, not a new GitHub Actions/Cloud Build pipeline.
- Initialize accepted models, fixed variables and required historical baseline into the destination bucket once. Recurring operations specify month and independent ACLED/WFP keep/refresh choices; the system updates remote sensing and generates/submits the manifest without hand editing JSON.
- Use one destination configuration file and a unified CLI for initialization, monthly runs, status, downloads, model registration and selection. Model updates accept already-trained packages compatible with existing features/runtime; retain old versions.
- Keep accepted October output as cloud-entrypoint fallback. Do not rerun or repeat numerical acceptance of September/October outputs.
- Preserve existing feature construction, normalization, fill and prediction semantics. Do not investigate historical source lineage or shrink historical baselines by changing those semantics.
- Use Windows Git/native Windows filesystem operations when WSL/DrvFS reads fail. Do not launch close/spot audits.

## Requirements and acceptance
| ID | Requirement | Observable acceptance |
|---|---|---|
| R1 | Two clear public entrypoints: `september_manual/` and `cloud_pipeline/` | Root README routes operators only to these two; necessary Git/developer metadata is not a public run entrypoint |
| R2 | Closed operational dependencies | Documented commands and supported imports work from relocated delivery folders with original repo, hidden task paths, old /tmp paths and external legacy archive unavailable; schemas and package assets are included |
| R3 | September handoff and October fallback are preserved | Keep accepted archives/results and their small replay evidence byte-identical; change only wrapper navigation/inventories when needed; do not rerun model replay |
| R4 | Destination bootstrap and ongoing operation | One config supplies project/buckets/region/identities/runtime/baseline/model selection; init records actual destination refs; monthly command builds and validates requests, starts preparation, waits for success, and submits the existing delivery event path |
| R5 | Source updates are operator-friendly | Independent keep/refresh flags; refresh accepts compatible raw files, checks converter format, uploads immutable refs and builds correct source entries without manual JSON; keep uses the explicitly selected retained history |
| R6 | Safe new-model selection | Complete compatible packages are validated, assigned immutable versions and selected for future manifests; keep exactly six system/horizon slots, preserve old packages, reject incompatible schema/runtime, and do not reuse old model-specific diagnostic evidence |
| R7 | Reversible external archival | Written keep/move/archive map covers changed paths; no destination overwrite, no deletion, no movement of active Git/Trellis controls or unrelated dirty metadata; archive entrypoints and material unavailable in Git remain recoverable locally |
| R8 | Clear handover documentation | English README/Quickstart document bootstrap versus monthly usage, raw formats, model changes, fallback and download locations with runnable public paths; Chinese entry summary stays consistent |
| R9 | Focused verification without unnecessary replays | Local/fake-service tests cover CLI/config, pinned refs, failure/retry/idempotency, raw choice combinations, model changes, closure and relocation; packaging checks member identity; no real cloud work or repeat accepted model scoring |

## Evidence and constraints
- `deploy/october_delivery/README.md:52-53,93-96` invokes archived hidden request makers; lines 104-105 mention prior /tmp environment. Replace these operational dependencies, not merely rename links.
- Runtime currently spans cloud, fewsnet_partitioned_rf_pipeline, model_pipeline and tools; package-local schemas and feature assets must accompany Python source. Some cloud-used statistics are mixed with old hand-run entrypoints; see research/closure-findings.md.
- Current migration baseline is approximately 3.49 GiB unpacked. This is one-time initialization data, not monthly acquisition. Full historical panels account for ~2.38 GiB; lag/rolling features and full-history climate normalization explain the current dependency. Aggressive data minimization is not this task.
- No destination credentials/project are supplied for execution. Package/setup commands may be implemented and tested locally, but actual migration and live provider access remain operator actions.

## Out of scope
Training, changing feature/model/scoring semantics, a new web UI, GitHub build CI, live deployment/cutover, historical provenance tracing, replaying accepted September/October predictions, deleting legacy data, and close/spot audits.

## Planning status
User approved the final summary with "执行". Implementation is authorized; actual cloud operations remain out of scope.
