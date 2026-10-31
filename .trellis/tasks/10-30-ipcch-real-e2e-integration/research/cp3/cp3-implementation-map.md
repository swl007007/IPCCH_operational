# CP3 early implementation map (Executor p8, before product edits)

The Supervisor pane was blocked on an approval dialog when this was sent, so it is saved here.

## Impact
- `pipeline.status`: **HIGH** (6 direct callers). It is **not modified**. A new `status_v2` is dispatched from `main` only when a v2 run state exists.
- `publication.build_record`, `setup.commands`, `pipeline.main`, `Cloud`: LOW.

## Docker
- Windows client 29.5.3 is installed.
- The daemon is not running (`npipe dockerDesktopLinuxEngine` absent), and Docker Desktop WSL integration is off.
- So there is no local build or pull in CP3. Build-path evidence is tests plus an offline staging dry-run.

## Plan
1. **v2 submission.** `cloud/orchestrator/submit_v2.py` plus a `pipeline submit` subcommand.
   - Input is a selections JSON: the 11 explicit keep/refresh choices, each refresh with a local path or `gs://` object plus its declared interval and regions.
   - Structural validation with provisional refs happens before any upload.
   - One UTC instant fixes both M and `prepared_at`. It is persisted in `work_dir/runs-v2/<run>/state.json`.
   - Uploads and pins are create-only.
   - The expected pointer generation and the R39 month are read from current.
   - The full `v2.admit` runs locally: trusted prefixes and every reference's sha256.
   - The body is persisted locally; `run_manifest.json` is uploaded last and create-only.
   - Resume re-uploads the identical stored bytes and never takes a new instant.
   - `status` reports v2 runs from `v2_run_status.json`, `v2_reservation.json` and the claim.
2. **Deployment config and wiring.**
   - Concrete deployment JSON with `verification.status` pending live checks.
   - Exact current-URI test.
   - The installed config omits the FEWS `image_uri`, so the image never references its own digest.
   - `project.json` is backed up, then gets the `work_dir` fix and the v2 keys.
   - Workflow `DELIVERY_V2_CONFIG` env var, and `--v2-config` in `run_job`'s argv.
   - `setup.py` job args and env.
3. **Installation.** `cloud/ipcch/install.py` stages and verifies the artifacts and writes `INSTALL.json`.
   - `build_context.sh` stages only verified artifacts.
   - Dockerfile: `COPY` plus an offline `RUN install verify`.
   - A self-contained `cloud/ipcch/smoke_providers.py`.
   - A hash-bound smoke fixture bundle generated at staging time; never the real handoff.
4. **FEWS preservation.** Inherited members are copied literally. Per-run inheritance is recorded in a top-level `inherited` field. The activation guard is unchanged.
5. **Tests.** Focused tests per item, run as one guarded unit per file.
