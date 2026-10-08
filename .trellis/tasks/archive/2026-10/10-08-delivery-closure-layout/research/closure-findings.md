# Closure and archive findings

Read-only code/path research for this task; no cloud calls, moves, or model replay. Native Windows IO and Git were used. The two delegated probes covered runtime paths and shallow archival inventory.

## Supported runtime closure
- cloud/orchestrator/delivery_bundle.py:29,61-71 defines/copies the four runtime packages. deploy/october_delivery/Dockerfile:5-14 copies the same four into /app.
- delivery_job.py:38 and deliver_job.py:24 derive root via parents[2]; root requirements.lock.txt is preferred at delivery_job.py:142-143. Keeping four packages directly under cloud_pipeline preserves these relations.
- build_context.sh:4-8 assumes deploy depth and old repo-relative paths; revise for the new root.
- cloud/common/manifest.py:66-68 and fewsnet_partitioned_rf_pipeline/schemas/__init__.py use importlib.resources; include JSON schemas. FEWS config.py:25-34 needs package assets/partitions and assets/feature_contracts.
- delivery_inputs.py:26 and delivery_job.py:240,272 call tools.refresh_h5_inputs; delivery_outputs.py:21-23 imports both country aggregation tools and revise_h5_country_v3.
- revise_h5_country_v3.py:19-20 imports run_h5_model_delivery helpers. Its unused legacy prepare() at 194-196 reads hidden task specs and its constants at 24-25 point at another repository. Retain/extract cloud-used calculations; archive old workflow entrypoints. Do not copy all tools blindly or keep hidden runtime requirements.
- base_input_validation.py:16 imports tools.validate_ipcch_schema. No AST import from the four packages to workflow_config was found, but dynamic/file dependencies still need targeted closure tests.

## Existing operations to reuse
- prepare.py:744-761 exposes plan/extract with immutable request/plan refs, destination EE/Batch arguments and deadline.
- delivery_job.py:395-429 exposes run/system, subprocesses itself by module name. Preserve module import paths within new runtime root.
- delivery_manifest.py:210-248 validates keep/refresh shape and exactly six model slots. delivery_job.py:270-278 converts raw at the selected origin.
- Existing migration_destination.py rebuilds package manifests from a frozen source_request. Replace the runtime dependency on that old request with an explicit operational baseline/model descriptor.
- Existing Vertex registry serves FEWS-only RF parents, not the current dual-system local model packages. Do not add a Vertex Model Registry dependency; reuse GCS immutable package refs and existing loaders.

## Archive candidates and controls
- Windows Git reported only the primary worktree; .worktrees was empty. The sibling legacy_archive directory did not exist at inspection. Recheck at execution before moving anything.
- tools/.git exists but was empty; avoid preserving a phantom nested repository in public delivery code.
- Root developer metadata is unrelated dirty state from earlier work. Leave Git/Trellis/agent controls in place and exclude them from standalone operational exports.
- tests/cloud/test_monthly_assembly_wrapper.py:16 references Final_harmonise/00_build_monthly_ipcch_base_input.py. Either retain the required active implementation and update imports or archive that legacy-only test together with the old path; do not hide an operational dependency.
- test_delivery_outputs.py:8-9 uses the September fixture and skips if absent. Update its path and require that existing comparison fixtures remain available; do not let directory moves silently skip coverage.
- test_delivery_workflow.py:10, test_migration_package.py:9, test_wind_down_rest.py:7 reference the old deploy layout.
- Frozen migration runtime/deploy are copies separate from maintained source. Assemble one authoritative runtime; do not merge by overwriting same-named files from different inventories.
