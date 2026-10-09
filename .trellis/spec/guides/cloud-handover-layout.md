# Operational handover layout

The supported runtime root is `cloud_pipeline/`; run cloud tests and module commands with that as the working directory. Public operational docs must resolve from this directory or the exported archive. The separate `september_manual/` is an accepted result/offline replay handover. Its root h5 files stay byte-identical. September-origin 6m/12m results live under `september_manual/scopes/`, which has its own inventory.

- Keep module names `cloud`, `fewsnet_partitioned_rf_pipeline`, `model_pipeline`, `tools` unchanged under the runtime root. Include package schemas and CSV contracts.
- Developer/task paths, the sibling legacy archive and another repository must never be runtime inputs or public command dependencies.
- `pipeline.py` owns init/run/status/download/models; setup consumes the same private JSON config. Real cloud actions require explicit scope; local tests use fake services.
- Preserve the destination work directory. A preparing run needs the same run command to continue to manifest submission; status is read-only. Do not resubmit an ambiguous launch automatically.
- Keep/refresh choices are independent. Keep binds initialized source snapshots. A refresh does not implicitly promote a future keep baseline.
- Compatible model registration requires a complete package, matching feature schema, original environment and real package-specific acceptance. Rebinding an identical image digest to another registry preserves identity, but rebuilding does not inherit acceptance.
- Preserve accepted result/archive bytes during layout changes. Verify hashes and relocation; do not repeat accepted model replay without a reason in task scope.
- Handover archives are create-only and dated (e.g. `dist/cloud_pipeline-20261009.tar.gz` after the baseline gained diagnostic evidence). Never overwrite an earlier archive.
- `deploy/handover_package.py` owns the code/data archive. Keep credentials, private config, state, tests and developer controls out. Shell scripts use LF. Large bootstrap/fallback/dist payloads are local handover artifacts, excluded from Git.
- Current legacy originals are outside the repo at `../legacy_archive/IPCCH_monthly_operational/2026-10-08-two-entry-handover/`; MOVE_MANIFEST.json and DELIVERY_MOVES.json describe inverse moves. They are recovery materials, not operational dependencies.

Run supported tests from a relocated runtime with the frozen Python environment. The accepted container is transferred separately by registry/OCI; it is not embedded in the local archive. A fresh destination deployment remains a live operator action.
