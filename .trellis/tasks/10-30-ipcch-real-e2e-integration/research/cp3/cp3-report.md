# CP3 — v2 submission, deployment wiring, verified installation, FEWS continuity (Executor report for gate)

**Executor.** Opus 5.5, session 6a490ae1, pane w1A:p8.

**Boundaries.**
- No cloud call, upload, commit, Audit, branch change or task-state edit.
- Not edited: AGENTS.md, PROGRESS.md, specs.
- Docker: Windows client 29.5.3 is installed, but the daemon is not running (the `dockerDesktopLinuxEngine` pipe is absent) and WSL integration is off. Nothing was started or pulled, and no image was built. Image building is a CP4 packet item (§6).

**Final source.** Hashes are in `final/SHA256SUMS`; `py_compile` and `bash -n` exit 0 (`final/py-compile-exit.txt`); `git diff --check` is clean.

## 1. v2 operator submission (R9 / AC9 / D3 / D5)

**Surface.** `cloud/orchestrator/submit_v2.py` (final sha in `final/SHA256SUMS`) and `pipeline.py` (`030591aa…`):
- `pipeline.py submit --config project.json --selections FILE [--execute] [--run-id ID]`;
- `status --run-id` dispatches to the v2 status only when `work_dir/runs-v2/<id>/state.json` exists. The legacy `status` (GitNexus HIGH, 6 callers) is untouched.

**Selections** (`ipcch-v2-selections-v1`):
- exactly the 11 explicit choices (ACLED, WFP, history_snapshot and the eight research families); keep is never implied, and keep entries pass verbatim so `v2._choice` rejects any extra field;
- a refresh file may be a local path, a `gs://` object pinned at its current generation, or `gs://…#generation`;
- the declared interval and regions follow the existing per-family contracts;
- operations are IPCCH generation, optionally with inference; publication is current or candidate.

**Order** (AC9 boundary corrected per Supervisor):
1. **Structural preflight** with provisional refs and a provisional, never persisted, time. It includes lexical trusted-namespace admission of planned upload URIs and of the mode's configured country reference. An invalid selection uploads nothing and writes no state.
2. **Asset preparation.** The run ID is date-free. Files are uploaded create-only under `inputs_prefix/<run>/<choice>/`, or pinned, and each reference is saved as soon as it exists. The shared envelope and environment manifest and the mode's country reference are pinned.
3. **Freeze.** One UTC instant is captured, giving M and `prepared_at`. The current pointer is re-read fresh (expected generation, and the real R39 month). Full `v2.admit` runs locally: structure, namespaces, and every reference's generation and sha256. The request bytes and the instant are persisted together.
4. **Trigger.** Those exact bytes are uploaded create-only to `requests/<run>/run_manifest.json`, last.

**Resume.**
- Before the freeze, a resume continues the uploads, and the later freeze takes its own instant (no request existed yet).
- After the freeze, a resume re-uploads exactly the persisted bytes and timestamp; a lost response is safe.
- A changed selection, or changed local file bytes, under the same run ID is refused.

**Tests:** `tests/test_operator_submit_v2.py`, 24 passed. The 24th is `test_the_v2_runtime_image_is_separate_from_the_legacy_destination_image` (§7).
- Preview makes no cloud call.
- Seven invalid selections, keep-with-extras (×3), a missing 11th choice, and an untrusted upload prefix or country reference: each yields zero uploads and zero state.
- Month crossing: preflight and upload on 2026-10-31T23:58Z, freeze at 2026-11-01T00:01Z gives M 2026-11. The pointer moved during the uploads, and the fresh generation is used.
- Workstation UTC+2 01:30 on Nov 1 gives M 2026-10.
- Lost upload response, resumed a month later: same bytes, same instant, one object.
- Failure before freeze, then a later freeze at its own instant.
- Admission failures at freeze (R39 current month; a reference changed after pinning): nothing triggered.
- Smoke namespace; status from claim, reservation and final status; the CLI preview through `pipeline.main`.

**Legacy is unchanged:** `test_operator_cli` 11 passed, `test_operator_release` 32 passed.

## 2. Deployment config and wiring

**Config.** `deploy/ipcch_v2_deployment.food-crisis-test.json` (sha `c75b1172…`):
- real root `gs://food-crisis-test-ipcch-data`, namespace `monthly-staging`; the production current is exactly `gs://food-crisis-test-ipcch-data/monthly-staging/current.json`, the legacy pointer, and a test asserts this;
- smoke root `gs://food-crisis-test-ipcch-smoke/v2` with its store and trusted prefixes; this is a proposal and is non-nested;
- `producer_asset_root` `projects/feisty-flames-511718-d4/assets/`; `run_timeout_seconds` 14400;
- installed paths under `/opt/ipcch`; no FEWS image and no digest, so there is no self-reference;
- `verification.status: pending-live-verification` lists the live checks: smoke bucket, runtime IAM, han-sandbox reads and asset-root writes, and the deployed image.

**Workflow** (`deploy/workflow.yaml`): `DELIVERY_V2_CONFIG` is set, and `run_job`'s full argv passes `--v2-config`. v1 requests ignore it.

**Setup** (`deploy/setup.py`): the `oct-delivery` default args gain `--v2-config /opt/ipcch/deployment.json`; the Workflow env adds `DELIVERY_V2_CONFIG`; the job keeps the 4h timeout and 0 retries.

**Tests:**
- `test_workflow_dispatch` 45 passed: a v2 request takes `run_job` with `--v2-config` and the delivery job's parser accepts it; legacy requests also receive the flag.
- `test_delivery_workflow` 1 passed. Its earlier run failed only because the test's render map predated `v2_config`; that run is kept as `final/runs/test_delivery_workflow.INTERMEDIATE-stale-render-map.*`.
- `test_deploy_setup` 3 passed.

**Operator `project.json`.**
- Backed up to `project.json.bak-cp3-20261031T015130Z` (sha `8eddc1bc…`) and extended with an additive `v2` section only (new sha `de801c35…`).
- `work_dir` was **not** repointed. Evidence is in `project-json-workdir-evidence.md`: the current `work_dir` holds the only `initialized.json` whose destination matches `project.json` (baseline `b77cb29b…`, post-FEWS-retrain). The other directory is stale (image `7e6133f3…`), and repointing would break every legacy command. Legacy `load_initialized` still passes.

## 3. Verified installation and smoke isolation

**Installer.** `cloud/ipcch/install.py` (sha `970c546a…`):
- `stage` refuses a wrong envelope pin before copying anything. It then copies into the `/opt/ipcch` layout and writes `INSTALL.json`.
- `verify` checks:
  - the envelope pin;
  - `verify_combination` in both real and smoke modes (every package member re-hashed);
  - `verify_handoff`, plus a streaming re-hash of EVERY handoff manifest member, with no unlisted file besides the manifest and acceptance entries;
  - the smoke fixture bundle: `fixture: true`, every member re-hashed, and never equal to the real handoff;
  - the deployment config: validated, exactly matching the layout, no digest, no `fewsnet` section.
- `verify --against INSTALL.json` re-verifies an installed tree.

**Build path.**
- `deploy/build_context.sh` requires all install inputs and stages through the verifier.
- `deploy/Dockerfile` copies `ipcch` to `/opt/ipcch` and runs `install verify --against /opt/ipcch/INSTALL.json --envelope-sha256 $IPCCH_ENVELOPE_SHA256` offline at build time.
- `OPERATIONS.md` is updated.

**Smoke.**
- `cloud/ipcch/smoke_providers.py` is a self-contained runtime provider; a subprocess check shows no `tests` or `pytest` module is imported.
- The smoke fixture root is generated at staging by `tests/cloud/make_smoke_fixture.py` (build machine only) from the existing fixture builder, then hash-bound in `INSTALL.json`.

**Tests:** `test_ipcch_install` 11 passed.
- Concrete config and exact current URI.
- Altered, extra or missing handoff, package or smoke members are refused.
- The real handoff is refused as the smoke fixture.
- Config with a digest, a wrong layout or an over-cap timeout is refused.
- `build_context` refuses missing inputs.
- The full smoke route through the runtime provider succeeds.

**Actual accepted artifacts.** Offline evidence in `install-dryrun/` (child exit 0, 203 MB peak). Real artifacts were symlinked, nothing copied, and the concrete config used:

| Artifact | Result |
|---|---|
| envelope | `03b93842…`, accepted |
| package | `18b91d45…`, 527 features, order `0ef1ffec…` |
| handoff | `e6e3ebc6…`; **all 58 members re-hashed, 2,271,631,220 bytes**; acceptance `cb14a956…`; roster `9ff2c420…` / 6226 |
| smoke fixture | 56 members, 3 areas, different manifest |
| config | `c75b1172…` |

## 4. FEWS continuity (AC6)

`publication.build_record` (sha `e34472da…`):
- inherited members are copied literally, including any existing `inherited_from_pointer_generation`;
- this publication's inheritance is recorded beside them in a new top-level `inherited` {system: pointer generation};
- the activation guard and the delivery verifier are unchanged (they still compare members).

Tests:
- `test_ipcch_publication` 9 passed: the inherited member is byte-identical to the snapshot member.
- `test_ipcch_release_v2` 11 passed: the legacy FEWS member payload is identical across two inheritances and equals the legacy record's member.
- Unchanged and green: `test_ipcch_legacy_guards` 15, `test_ipcch_delivery_member` 11, `test_fews_adapter` 13.

## 5. Final focused suite (frozen source; one guarded unit per file; `final/runs`, totals in `final/final-totals.txt`)

- **Result:** 18 files, **285 passed**, 0 failed, 0 skipped; every child exit is 0; peak RSS ≤ 490 MB.
- **Intermediate runs (kept, not final):**
  - `test_delivery_workflow.INTERMEDIATE-stale-render-map`: an outdated test render map;
  - `test_operator_submit_v2.INTERMEDIATE-pre-v2-image`: 23 passed, before the §7 change.
- **Coverage:** test_operator_submit_v2, test_operator_cli, test_operator_release, test_deploy_setup, test_handover_package, test_workflow_dispatch, test_delivery_workflow, test_runtime_image_contract, test_ipcch_install, test_ipcch_publication, test_ipcch_release_v2, test_ipcch_legacy_guards, test_ipcch_delivery_member, test_ipcch_entrypoint_v2, test_delivery_request_v2, test_ipcch_run_v2, test_delivery_job, test_fews_adapter.
- **GitNexus: HIGH** (`final/gitnexus-detect-changes.txt`): the `pipeline.main` and `publish` flows; every one is exercised above.
- **Earlier bring-up runs** are in `nodes/`; the first `test_operator_submit_v2` run had 3 failing tests, all test-side, fixed before the freeze.

## 6. Prepared real selection and CP4 prerequisites (live; not done in CP3)

**User-confirmed real selection, prepared and validated locally** (`real-selection/`; files in `~/ipcch-operator/food-crisis-test/v2-inputs/real-20261031/`; not uploaded):
- **ACLED:** f2+f3 joined, 38,765,520 bytes, sha `7bcb051f…` (exact). Declared 2016-12-31..2026-10-16, 14 manifest regions, covering the 12 regions the accepted tables require.
- **Existing contract:** `strict_csv` and `parse_export` pass (291,240 rows; 242,341 kept; rows from 91 countries outside the accepted mapping are excluded by contract).
- **R44 first refresh:** passes for both candidate origins, O=2026-08 and O=2026-09.
- **Selections:** `selections.json` sha `2d8da49d…`; the offline `submit` preview passes with the real `project.json`.

**CP4 packet items.**
1. **Image build.** No local daemon, so use a bounded Cloud Build (explicit machine type, disk and timeout).
   - The context comes from `build_context.sh`, re-staged from the final commit, with `--build-arg IPCCH_ENVELOPE_SHA256=03b93842…`; the build runs `install verify`.
   - Record the digest in `project.json` **`v2.image_uri`** and deploy it to the jobs and the Workflow with `setup.py`.
   - The EXISTING `project.json` top-level `image_uri` is NOT updated (§7): it stays the legacy destination bound by the existing `initialized.json`.
   - The new digest becomes a legacy destination only through C (§7): a NEW config with a NEW `work_dir`, initialized from a newly accepted baseline. The old config and state are preserved.
   - A is only the temporary cutover hold; the transition is `cp4/compatibility-transition-plan.md`.
2. **Create-only uploads of the shared objects:** envelope, environment manifest and country reference to the `project.json` `v2` locations. Then confirm, or replace, the proposed smoke bucket and prefixes.
3. **Live preflight under the runtime identity:**
   - read/write on the roots, stores and export root;
   - read on the trusted prefixes and the han-sandbox inputs;
   - create on the EE asset root;
   - read the current pointer and its FEWS member.
4. **Store initialisation:** `entrypoint_v2 initialise --mode real`, then smoke with an acceptor.
5. **Submission:** `pipeline.py submit --config … --selections …/selections.json --execute` (M fixed at freeze), then `status`.

CP5, the full 6,226-area real E2E run with current readback, is a mandatory part of this round. Only DA1 and DA2 (live new-month incremental acceptance) are deferred. No live claim is made here.

## 7. Legacy runtime-image compatibility (Supervisor seam)

Full disposition, with line evidence: `compatibility-disposition.md`.

**Facts.** The legacy operator state, the delivery job, the environment manifest and every acceptance report bind the runtime image. The only supported rebinding is to an identical digest. The deployed `487a2315…` predates the v2 activation guards.

**A, TEMPORARY cutover hold only (not final compatibility):** one v2 image for the jobs and the Workflow, with the existing maintenance hold admitting only bound runs during cutover.
- Legacy v1 requests fail closed; nothing is published by them.
- The FEWS member is inherited literally.
- Legacy operator state is untouched.

**Rejected (B):** keeping `487a2315…` for legacy beside a v2 job. The old code could overwrite an activated v2 current.

**Required final disposition (C; Supervisor, 2026-10-31):** PRD AC3 requires that existing consumers are preserved. Permanent fail-closed FEWS rescoring does not meet that.
- The unchanged packages are re-accepted from real compatibility evidence in the new runtime.
- They are initialized into a new destination; old state is preserved.
- A legacy FEWS-only candidate is verified before the hold is released.
- Plan and bounded packet: `../cp4/compatibility-transition-plan.md`.

**Code change for A.** The v2 request image comes from `project.json v2.image_uri`, and execute refuses without it. The top-level `image_uri` stays the legacy destination. Test 24 covers this. `project.json` was backed up again, and its pending note was corrected (sha `a078f0e5…`).

## 8. Real build payload (staged, no Docker / no cloud)

`build-context/` holds the evidence. The actual `deploy/build_context.sh` was run under the guard (child exit 0, 187 MB peak, 5.6 s). It used a fresh smoke fixture from the existing generator; the manifest `044c72f8…` is identical to the dry run, so generation is deterministic.

| Item | Value |
|---|---|
| Context | `/home/swl007007/ipcch-operator/food-crisis-test/v2-build/stage-20261031T015828Z/tmp.lACWLdxwS7` |
| Size and files | 2,370,588,224 bytes, 276 files (no `__pycache__`) |
| Per-file listing | `context-files.sha256` (sha `c74b4d6b…`) |
| `INSTALL.json` | `33d19119…` |
| Context Dockerfile | `c2edb50c…`, equal to the frozen source |

Staging re-verified the accepted envelope, package and handoff (58 members, 2,271,631,220 bytes), the smoke fixture and the config. Disk use is 2.37 GB on the root ext4 volume (604 GB free); no memory or disk limit was hit, and none was raised. The context code was copied before the §7 `submit_v2` change; the operator CLI is not part of the image's runtime path, but CP4 should re-stage from the final commit.
