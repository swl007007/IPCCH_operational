# Two-entry handover design

## Public layout

```text
IPCCH_monthly_operational/
  README.md
  LICENSE
  september_manual/
    README.md
    webapp_model_bundle.tar.gz
    fewsnet/  ipcch/  inputs/  reports/  original_metadata/  inventory.json
  cloud_pipeline/
    README.md  QUICKSTART.md
    pipeline.py
    project.example.json
    requirements.lock.txt
    cloud/  fewsnet_partitioned_rf_pipeline/  model_pipeline/  tools/
    deploy/               # current October definitions and bootstrap instructions
    tests/                # supported cloud/runtime/CLI tests and fixtures
    bootstrap/            # one local copy of frozen assets/models/descriptors
    fallback/october_2026/ # accepted October artifacts, no rescore
    dist/                 # generated standalone handover archive + checksum
  .git/ .trellis/ ...      # existing developer controls, never operational dependencies
../legacy_archive/IPCCH_monthly_operational/<cleanup-id>/<original-relative-paths>
```

The README is navigation, not a third runnable entrypoint. A unique project/cleanup subdirectory under sibling legacy_archive avoids collisions and retains original paths. Preserve Git, active Trellis and agent metadata; no indiscriminate movement of hidden directories during an active session. Public payloads exclude them. Root control documents may remain for developers without being operator commands.

Keep Python module names unchanged by placing the four required packages at cloud_pipeline root. Runtime starts with that directory on its module search path. Carry package JSON/CSV assets and schema files. Separate only the small cloud-used functions trapped in old standalone modules when needed to archive old execution paths; preserve arithmetic and signatures. Do not refactor model architecture.

## One configuration, one CLI

Use a documented JSON configuration with destination project, region, buckets, service accounts, image digest, release namespace, immutable baseline/model selection refs and an operator work/state directory. Exclude secrets and filled configuration from Git. Choose current standard library parsing and existing GCS clients rather than adding a framework.

Proposed public commands (final spelling may simplify without changing behavior):
- `python pipeline.py init --config project.json --baseline bootstrap/`: validate closure/config, initialize assets/models in the destination, record actual refs. Provide setup commands/templates for APIs, IAM, EE registration, image and Run/Batch/Eventarc/Workflow resources; never claim resources already exist. Default preview for cloud mutations; explicit --execute applies when the operator is ready.
- `python pipeline.py run --config project.json --month YYYY-MM --acled keep --wfp keep [--acled-raw FILE] [--wfp-raw FILE]`: validate choices, create a unique run/prepare identity, discover/extract remote observations, wait for successful preparation and submit a complete pinned run manifest. Supply cutoff/deadline explicitly or from documented configuration; provider lag keeps its existing disclosed behavior.
- `status --run-id ID`: distinguish preparation, submission, scoring, failed and succeeded states; show durable status/result locations.
- `download --run-id ID --output DIR`: retrieve exact accepted release members to a fresh directory and check transport/declared file identity, without model replay.
- `models register --package PATH --system ... --horizon ...` and `models select ...`: register complete compatible immutable packages and update future model selection explicitly. Expose old version selection for rollback; never overwrite old releases.

Read commands do not trigger compute. A running invocation may attach to recorded state rather than resubmit; failures retain evidence and require a new attempt ID. Persist enough local/cloud refs that a terminal disconnect does not lose the submitted job identifiers. Reuse existing create-only sentinels, run-status and release CAS instead of a parallel execution engine. Status success requires the delivery's durable succeeded result, not workflow submission alone.

## Bootstrap versus monthly state

Use the already local validated payload as initial assets/models; no source tracing. Extract reusable metadata into an explicit supported baseline descriptor rather than depending on reference/source_request.json, hidden archived scripts or old cloud URIs. Each immutable baseline describes the exact panel/history/geometry/roster/model refs. Upload is one-time; future operations read destination refs.

For recurring months, preserve the selected keep baseline and all months needed by existing lag/normalization calculations. Retain completed preparation/refresh products as versioned assets. Do not silently make a new raw upload the meaning of future keep or discard prior input coverage: the selected baseline/source version must be explicit and persisted. Existing full-history semantics are authoritative; performance optimization is outside scope.

Remote refresh and ACLED/WFP conversion reuse current functions. Required columns, date formats, cutoff rules and coverage reports are documented beside the CLI. WFP needs adjacent calendar observations for FEWS changes; ACLED refresh needs complete covered-month event exports. Bad input stops before request publication, without wiping existing source data.

## Models and acceptance

Model selection contains exactly FEWSNET/IPCCH x 0/6/12; individual replacement preserves unchanged slots. IPCCH shared root members must agree across selected scopes. New package IDs, thresholds/routing/imputation metadata and feature contracts travel with weights. Validate using existing loaders and feature contracts; no training, Vertex registry or automatic feature redesign.

Registration/integrity checks are distinct from scientific/runtime acceptance. Require real package-specific validation/evidence for a newly accepted model; do not inherit old model diagnostics or fabricate accepted status. Existing six packages retain their already accepted evidence. For an identical runtime image digest copied to another registry, preserve and rebind verified identity references without demanding repeated October scoring; a changed image/runtime is outside that equivalence claim and requires separate actual compatibility evidence. Test these rules with fixtures, not production replays.

## Closure and archival

Every supported entrypoint resolves files relative to its delivery root or explicit config/work paths. No import or command may require legacy_archive, .trellis, .worktrees, developer /tmp files, the old GCP project or a neighboring research repository. Dependencies installed from the lock and configured provider/GCP access are declared external prerequisites, not hidden files.

Generate an exact move manifest before execution, including ignored large files; checksum immutable handoff members without rerunning models. Stage the new entries, prove local dependency closure, then rename/move old paths into collision-free external archive. Preserve original files at one archive location and a restore map; do not add another full backup of every active payload. Rebuild the distributable from authoritative new paths, not archived builders with hardcoded initial sources. Update Git ignores, deployment build paths, test fixtures and operator docs in the same change.

## Validation boundary

Use CLI help/config/preview tests, mocked GCS/Run/Batch calls, temporary fake packages and local relocation/import checks. Run relevant current unit tests for moved converters/loaders and updated paths, with explicit assertions against silent fixture skips. Integrity-check copied result members and archive contents; do not rerun September/October inference, install a new cloud project, or claim a live handover passed. The receipt states exactly those limits.
