# Legacy runtime-image compatibility: disposition for the CP3 gate / CP4 packet

> **Superseded in part (Supervisor gate, 2026-10-31).**
> - A is acceptable only as a TEMPORARY cutover hold, not as final compatibility. "Recommended for this round" and "not required for this round's AC" below are withdrawn.
> - PRD AC3 (existing consumers preserved) requires C.
> - B stays rejected.
> - See `../cp4/compatibility-transition-plan.md`.
> - The body below is kept unedited as the CP3 investigation record.

Read-only investigation. Nothing changed:
- no guard was patched;
- no `initialized.json`, acceptance report or model registration was edited or created;
- no retraining or cloud call was made.

## Bindings found (source at this checkpoint)

| Where | What is bound | Effect of a new image digest |
|---|---|---|
| `pipeline.destination` / `load_initialized` (`pipeline.py:515-525`) | the top-level `project.json` `image_uri` is part of the operator destination of `initialized.json` | changing it breaks every legacy operator command (`run`, `models`, `promote`, …), including FEWS-only ones |
| `pipeline.validate_model` (`pipeline.py:232-236`), `initialize` (`:369-376`) | the model acceptance and the baseline must match the configured runtime digest and lock | existing packages cannot be registered for another digest |
| `pipeline.publish_model` (`:316+`) | rebinding evidence is literally "identical package member hashes and runtime image digest" | the only supported rebinding is to the SAME digest (registry copy); a rebuilt image inherits no acceptance |
| `delivery_job.prepare_inputs` (`delivery_job.py:228-229`) | job image == request `runtime.image_uri` | legacy v1 requests built with `487a2315…` fail on a new job image |
| `delivery_job.check_environment` (`:163-169`) | the environment manifest names the job image and the exact dependency lock | likewise |
| `delivery_job.check_acceptance` (`:148-160`) | every model's acceptance report names the request runtime image and environment sha | FEWS (and legacy IPCCH) acceptance reports bound to `487a2315…` cannot pass under a new digest, on the v1 route or the v2 FEWS route (which scores through the same delivery job checks) |
| `pipeline maintenance apply` | only (re)deploys the configured resources | it is not a migration |

The deployed legacy image `487a2315…` (2026-10-22) predates the v2-era guards now in source:
- `delivery_job.bind_current` with the R37 activation rule (`:650-674`);
- v2-record-aware legacy publication;
- `reject_new_contract_candidate`.

## Dispositions considered

**A. Recommended for this round: one runtime image (the v2 image) for the `oct-delivery` and prepare jobs and the Workflow, with the existing maintenance hold during cutover.**

Consequences:
- **v2 IPCCH requests run.** Their `runtime.image_uri` comes from the new, separate `project.json v2.image_uri`. `submit_v2` now refuses to execute without it, and the top-level `image_uri` stays the legacy destination digest.
- **The FEWS member of current is preserved literally.** The v2 IPCCH current publication inherits it unchanged; CP3 publication change and tests.
- **Legacy operator state is untouched**, and `load_initialized` still passes.
- **Legacy v1 requests fail closed** on the new job: job image ≠ request runtime, and the acceptance reports name the old digest. This happens before any scoring or publication, and their admission and remote-update paths run the new code, which includes the R37 guards. Nothing is published by a legacy request.
- **Cutover safety without new code.** The existing `pipeline.py maintenance hold --admit <v2 run id>` makes the Workflow refuse every other run before any job. This avoids a legacy remote-update intent being admitted and prepared (Batch cost) and only then failing at delivery. Release the hold after the v2 run and its readback.
- **Rollback:** record the current job image, the Workflow revision and env, and the current pointer generation before deploying; redeploy those to roll back. Retained data writes are not rolled back (design).
- **Limitation, stated explicitly:** after the new image is deployed, legacy and FEWS rescoring (v1 or the v2 FEWS route) is unavailable until FEWS packages are accepted for the new runtime (option C). This round needs no FEWS rescoring: FEWS is inherited, not rescored.

**B. Rejected: two jobs (keep `487a2315…` for legacy, add a new v2 job).**
- `487a2315…` lacks the v2 current and activation guards.
- After the first real v2 publication activates current, a legacy FEWS publication by that image could write a v1-style release record over a v2 current. That would drop the v2 IPCCH member and its activation, and break the literal FEWS/IPCCH continuity this task requires.
- Separating jobs does not fix code that predates the guards.

**C. A new bounded action if legacy/FEWS rescoring must stay available under the new image (Supervisor/user scope decision).**
- Re-accept the unchanged FEWS packages (and, if wanted, the legacy IPCCH packages) for the new runtime from REAL compatibility evidence. Precedent, 2026-10-09: the `cp5-confidence` image was accepted because its real-cloud rerun reproduced every prediction of the earlier image.
- Then register them via the existing `models register` path and re-initialize a new legacy destination (new `work_dir`/`initialized.json`) for the new digest.
- This needs cloud compute and new acceptance reports. It is not a CP3 code change, and it is not required for this round's AC.

## Changes made for disposition A (CP3)
- **`submit_v2`:** `runtime.image_uri` = `project.json v2.image_uri`, digest-pinned. Execute refuses without it; preview falls back visibly (`image_uri_pending`).
  - Test: `test_the_v2_runtime_image_is_separate_from_the_legacy_destination_image`.
- **`project.json`:** backed up (`.bak-cp3-20261031T015945Z`); the pending note now states the top-level `image_uri` stays legacy and `v2.image_uri` is added after the CP4 build (new sha `a078f0e5…`). The legacy `load_initialized` still accepts baseline `b77cb29b…`.

## For the CP4 packet
1. **Build** the v2 image from the staged context in `build-context/`; the build runs `install verify`. Record the digest in `v2.image_uri`.
2. **Before deploying,** record the old job image (`487a2315…`) and its args, the Workflow revision and env, and the current pointer generation and FEWS member. Then place a maintenance hold admitting only the v2 run ID.
3. **Deploy** with `setup.py`, which carries `--v2-config` and `DELIVERY_V2_CONFIG`, with `image_uri` = the v2 digest for the jobs. The operator's top-level `image_uri` stays legacy.
4. **After the v2 run:** read back current; verify the FEWS member is byte-identical to the pre-deploy member; release the hold.
5. **State to operators:** legacy/FEWS rescoring needs option C before it is available on the new image.
