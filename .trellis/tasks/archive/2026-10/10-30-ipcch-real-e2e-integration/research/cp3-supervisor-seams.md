# CP3 implementation seams (read-only scouting, not acceptance)

Current-source inspection 2026-10-31. PRD/design remain authoritative. No cloud
calls, build, or CP3 changes were performed by the scouts.

- Operator `cloud_pipeline/pipeline.py` currently creates v1 requests. Reuse
  `Cloud.put`, `put_json`, state-before-final-upload/resume patterns. `Cloud.pin`
  requires a supplied generation; `Cloud.latest` parses JSON and cannot pin CSV.
  Routine v2 needs automatic generation/hash resolution for all selected objects.
- Preserve legacy CLI/config. Its required month/cutoff/deadline and ACLED/WFP
  converters cannot become v2 business semantics. v2 validator already defines
  all 11 explicit choices and exact wire keys; no raw-JSON plumbing for operators.
- Derive routine M and prepared_at from one UTC submission instant. Reuse
  `delivery_request_v2.derived_months`; its returned `derived` field is NOT legal
  in the exact raw request. Existing explicit-M rerun validation stays available.
- Persist immutable request body before final upload to
  `requests/<run_id>/run_manifest.json`; that object alone triggers execution.
  Preview cannot claim remote pins verified without reads. v2 status is
  `v2_run_status.json`; current operator status reads only the v1 filename.
- `build_context.sh` currently stages four runtime directories only. Dockerfile
  has no /opt/ipcch artifacts or deployment JSON. Stage the accepted artifacts
  into the temporary context and verify inside the built image without networking.
- `binding.verify_combination` hashes package members. `verify_handoff` only
  verifies manifest/identity, NOT every payload. Use the existing streaming
  `sha256_file` for every required handoff member; do not call mutating store
  initialization as an installation validator.
- Runtime smoke provider cannot import `tests.cloud.ipcch_smoke_fixture` because
  it imports other test modules and the image omits tests/pytest. Extract only the
  narrow fixture provider behavior and install its isolated prebuilt bundle.
- Workflow `run_job` overrides the whole argv and currently omits --v2-config.
  Only delivery_job's `run` parser accepts it. Wire deployment setup/defaults and
  Workflow consistently; admit/resolve/release are separate legacy commands.
- Expected current URI is exactly
  `gs://food-crisis-test-ipcch-data/monthly-staging/current.json`. Real/smoke
  output roots must be nonnested. A real bucket root excludes smoke in that bucket.
- Review FEWS preservation against the PRD: current `publication.build_record`
  copies inherited member payload but changes inherited_from_pointer_generation.
  Pin the accepted meaning and test the requested preservation; do not silently
  claim byte equality of an object that changed. No FEWS retraining/generation.
- Avoid image-digest self-reference in installed config: FEWS image_uri is only
  required if its operations are selected. Existing legacy flow receives its
  image digest externally. Maintain that compatibility while installing v2.

Relevant existing tests: test_operator_cli.py, test_operator_release.py,
test_deploy_setup.py, cloud/test_delivery_request_v2.py,
cloud/test_workflow_dispatch.py, cloud/test_runtime_image_contract.py and
cloud/test_ipcch_entrypoint_v2.py. Add only missing operator date/pin/trigger and
installation cases; reuse the validators and existing request tests.

All local tests remain under the CP2 isolated memory guard (4 GiB, no swap).
No accepted keep/refresh choices or initial ACLED input refs have been inferred.
