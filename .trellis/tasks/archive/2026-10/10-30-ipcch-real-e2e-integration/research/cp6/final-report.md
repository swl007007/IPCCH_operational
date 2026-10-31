# Task 10-30 final report: IPCCH real E2E integration and cloud configuration

Executor: Claude session 6a490ae1-ee00-43f9-bdfc-c887c9816c09 (claude-opus-5-5[1m]); 2026-10-31.
- **Status:** the Supervisor accepted the CP5 real readback, and step 5g is done. Final acceptance, the commit and the task state are owned by the Supervisor.
- No commit, archive or audit was performed by the Executor.

Evidence index: `evidence-matrix.md` (AC1-AC9, DA1-DA2) and `operator-handoff.md` (commands, pins, rollback, gaps).

## Outcome

- **Production current** (`gs://food-crisis-test-ipcch-data/monthly-staging/current.json`, gen `1793461128385732`) points to the v2 release `ipcch-real-522b30030f944868-ipcch`:
  - a real full-roster IPCCH v2 member: M 2026-10, O 2026-08, H2/H8/H14 → targets 2026-10/2027-04/2027-10, 6,226 areas each, 527 features;
  - activation at 15:37:56Z;
  - the FEWS NET member inherited literally from the C compatibility release.
- **Route:** the run went through the deployed route with no manual action after `pipeline.py submit --execute`: request → Eventarc → Workflow → `oct-delivery` (image `acc3e467`) → `entrypoint_v2` → generation → inference → publication.
- **Readback:** the guarded readback with the product verifiers passed 27/27.
- **Warnings:** two known R65 optional-missing warnings. GPP_mean coverage ends 2025-12 and bbg_soybean_oil ends 2026-07, both before O 2026-08, so those features at O are NaN.
- **Phase counts:** the aggregate `overall_phase_pred` counts per horizon equal those of the 10-29 local same-M/O replay. This shows a matching aggregate distribution only. It does not show keyed (per-area) prediction equality, and it is not a numerical replay. It is not evidence of model accuracy.

## What was done in CP4-CP5 (cloud), grouped by phase

The phases are listed in dependency order, but they overlap in time. The store initialisation (3) ran while the C candidate (2) was executing.

1. **Image.** Cloud Build `ea1cbe1c` from `115798f`: install verify, runtime imports, and six-slot evidence in the pushed image (FEWS predictions equal the exact-lock reference).
2. **C compatibility transition.** Existing FEWS consumers were preserved:
   - runtime-only rebased baseline `f0481ca1` (only `baseline.json` changed);
   - new config and work_dir, then `init`;
   - maintenance hold, gate (hold probe refused), apply;
   - FEWS-only candidate on the new image, byte-identical on 121/121 required members to the current release;
   - guarded verify (receipt `8026d65d`), promote, release.
   - Old operator state and baseline are unchanged (hash evidence).
3. **Store initialisation.** One dedicated job (4 CPU/16 GiB/3600 s/0 retries), real then smoke. The pairings are recorded.
4. **Smoke run:** `ipcch-smoke-2dd1148b8c274496`, published only to the smoke namespace; readback 24/24.
5. **Real run:** `ipcch-real-522b30030f944868`; readback 27/27; R37 offline check (legacy IPCCH rejected, FEWS-only admitted).
6. **Normal config v2 finish (5g, 15:47Z).** The normal `project.json` gained ONLY `v2.image_uri` = `acc3e467` (diff in `5g/diff.txt`; backup `project.json.bak-5g-20261031T154715Z` 13b9deb3). It is now byte-identical to NEW_CFG (3be606ea). Validation was guarded, child 0 each:
   - `submit` preview shows the `acc3e467` image and no `image_uri_pending`;
   - real `status` reports succeeded;
   - direct `load_initialized` returns baseline `f0481ca1`.

   The older backups (8eddc1bc, de801c35, the operation backup a078f0e5) are unchanged.

## Source actions in the real run (from records, not inferred)

- **ACLED:** refresh `7bcb051f`, appended as `acled_agg_weekly` v1 (242,341 rows; coverage end 2026-08).
- **GPP:** 2026-01..08 got real HTTP 404s from `data.globalecology.unh.edu` in-job and are ledgered `unpublished`. GPP history is unchanged; features at O are NaN (R65 warning).
- **Climate and table production:** demand empty, jobs [], recorded `skipped`. All 26 climate tables and nightlight are unchanged. No asset was produced, and no han read was needed.
- **EE calls, stated precisely:** the run constructed the real providers, so `ee.Initialize` ran. The table-producer demand was empty (`jobs []`, `skipped`). Climate gaps were empty, so no fetch was scheduled. No export, `getAsset` or EE text appears in the job logs. There is no RPC-level EE telemetry, so the TOTAL number of EE API calls was not measured. The claim is 'no demand and no jobs', not 'zero EE calls'.
- **Kept:** WFP, history_snapshot and the 8 research inputs. bbg_soybean_oil coverage ends 2026-07 (R65 warning).

## Deviations and corrections (stated)

- **Fallback staging path.** The packet staged on ext4. Promote's `Path.rename` cannot cross into the `/mnt/c` mount (EXDEV), and it runs after the pointer CAS. The fallback was re-staged byte-identically beside the active fallback, as the precedent did, before promote.
- **Init sizing.** The local guarded init measurement hit the 3 GiB AS cap. The local cap was not raised; the cloud init job was sized from this evidence.
- **Readback invocation.** Two readback attempts failed before any cloud read (no `PYTHONPATH`; no project in the guard environment). Both are kept INTERMEDIATE, and the packet commands are fixed.
- **Ledger.** Direct (non-cloudop) reads are recorded with evidence-based times. One early minute estimate was corrected.

## Deferred and known gaps (not passed)

- **DA1/DA2 are deferred.** There is no live incremental month yet; the first natural case is M=2026-11/O=2026-09.
- **han read access.** The runtime SA `monthly-runtime` is CONFIRMED DENIED `getAsset` on the han-sandbox inputs. The user identity's metadata reads succeed, its ACL reads are denied, and its sharing capability was not established. Upstream-owner sharing (or an owner-approved copy) is required before any run with unsaved climate or table periods.
- **Rollback.** There is no dedicated post-publish v2 rollback helper. Containment is a new, reviewed maintenance operation, then forward recovery (see `operator-handoff.md` §4).
- **Retained artifacts.** The fallback directories are git-ignored local artifacts, recorded by path and hash. The init and probe job definitions are retained as evidence.
