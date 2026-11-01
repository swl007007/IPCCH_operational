# Executor handoff (same session 6a490ae1; written before any compaction) — task 10-31 CP4/CP5

**The D5 attempt was SUBMITTED ONCE. NEVER resubmit. There is no third attempt.**
- Run `ipcch-real-fe7282ef75e747fd`, frozen M 2026-11 / O 2026-09, prepared_at 2026-11-01T02:29:33Z, all 11 keep (selections `8092421f`).
- Request `gs://food-crisis-test-ipcch-requests/requests/ipcch-real-fe7282ef75e747fd/run_manifest.json#1793500174046456` (`b0f8b507…`); expected pointer gen `1793461128385732`.
- Claim 02:29:35Z. Execution `oct-delivery-625sk` (created 02:29:36Z, running). Reservation 02:30:34Z, DEADLINE `2026-11-01T06:30:34Z`.
- Frozen copies are in `run/frozen-state.json` and `run/frozen-run_manifest.json`. The preflight hashes are frozen as `SHA256SUMS.preflight-frozen`.

**Active process:**
- Background status poll, Claude task `bwb50a6er`: 120 s loop over `pipeline.py status`. On a terminal status it writes `/tmp/cp4-final-status.json`.
- Do not start a second poll if it is alive; check its output file first.

**Monitoring rules:**
- Durable progress uses `progress_read.py RUN 2026-11-01T02:29:00+00:00 OUT`, ALWAYS under guarded.sh.
- The guard needs `env PATH=<gcloud dir>:/usr/bin:/bin` for gcloud. The gcloud binary is `/mnt/c/Program Files (x86)/Google/Cloud SDK/google-cloud-sdk/bin/gcloud`.
- Sample 1 was unguarded and is recorded in `run/guard-omission-note.md`.

**On terminal:** run the CP5 readbacks per `cp4-packet.md` section "CP5 readback", all guarded with env `PYTHONPATH=cloud_pipeline` and `GOOGLE_CLOUD_PROJECT=feisty-flames-511718-d4`:
1. `readback_v2.py post real …` with `state=…/runs-v2/ipcch-real-fe7282ef75e747fd/state.json` and expectations 2026-11, 2026-09, 527, 6226;
2. `store_inventory.py`;
3. `lineage_readback.py` (eleven keeps; pre `inventory-pre-cp4-real.json`);
4. `witness_readback.py climate|links`;
5. `da2_witness.py` (local-credential identity label; never counted as the runtime SA).

**On failure:** reconcile current, locks, partial writes and export task records (including cancellations). Stop with no further mutation.

**Hard limits:** guards; no product, config, build or IAM change; CP0-CP3 stay frozen.

## Update (Supervisor CP5 helper spotcheck): use research/cp5/ helper copies for final acceptance
- Revised copies live in cp5/: witness_readback.py, da2_witness.py, da2_asset_readback.py. The cp4 copies stay frozen.
- Fixes: (1) climate witness: unique (admin, month) keys, one_to_one joins, new key set == bound roster x O, all 13 bases; (2) links: nonempty required table set (13 climate + 11 kept), batch id bound, delivery-manifest sha checked before parsing; (3) VI: empty sample => pending under D2, finite values with tolerance, inventory sha verified before parsing; (4) summarize: declared expected fields with omitted/null/finite status, PATCH32 rows/distinct/duplicates; (5) PATCH32 fill per input month with selected = isnan(primary) & isfinite(patch).
- Gitnexus: the task-local research scripts are not indexed product symbols; fallback recorded in cp5/gitnexus-fallback.md.
- Last run state: 7 asset exports and 1 raster export COMPLETED (sample 3 plus the EE task-state query); poll bwb50a6er is still running; NEVER resubmit.

## Update 02:52Z: CP5 helpers final (Supervisor-reviewed); USE cp5/ for the witnesses
- cp5/SHA256SUMS. The tests (test_cp5_helpers.py efd6d8b2) pass 7 under the guard, including the links() integration with fake bytes (required refs pass; empty or missing required refs fail; a corrupt delivery-manifest sha fails).
- On terminal, run guarded with env PYTHONPATH=cloud_pipeline and GOOGLE_CLOUD_PROJECT=feisty-flames-511718-d4 (add PATH with the gcloud dir if gcloud is needed):
  1. cp4/readback_v2.py post real ipcch-real-fe7282ef75e747fd cp4/pre-real.json CTX cp5/post-real.json STATE 2026-11 2026-09 527 6226
  2. cp4/store_inventory.py gs://food-crisis-test-ipcch-data/ipcch-v2/real cp5/inventory-post-real.json
  3. cp4/lineage_readback.py RUN cp5/post-real.json cp4/inventory-pre-cp4-real.json cp5/inventory-post-real.json cp5/lineage.json
  4. cp5/witness_readback.py climate cp4/inventory-pre-cp4-real.json cp5/inventory-post-real.json 2026-09 cp5/witness-climate.json (all 13 bases by default)
  5. cp5/witness_readback.py links cp5/post-real.json cp5/inventory-post-real.json cp5/witness-links.json
  6. cp5/da2_witness.py cp5/lineage.json cp5/inventory-post-real.json 2026-09 cp5/da2-witness.json (LOCAL credential identity label)
- Scientific honesty: PATCH32 source-level candidates plus saved values do NOT prove an independent SPEI numerical replay.
- GitNexus: before any further existing-helper symbol edit, make an actual impact request and record the response.
- The poll bwb50a6er was alive at 02:51:43Z (running). NEVER resubmit.

## Update 02:53Z: monitoring
- Sample 4 (guarded): 4 climate HEADs moved (prcp_anom, prcp_z, rainy_days, cdd); raster GCS export tasks 5 completed + 1 submitted; 7 asset exports completed.
- Background sampler: Claude task bugw76m8f, one guarded progress_read every 300 s, one line per sample in its output file. It stops when /tmp/cp4-final-status.json exists (the poll bwb50a6er reached terminal).
- Both processes must keep running across a compaction; check their output files, do not restart duplicates. NEVER resubmit.

## Update 03:02Z: Supervisor AC6 ACLED cutoff check added to final evidence (provenance/cutoff only, no replay)
- New standalone cp5/acled_cutoff.py (no existing symbol edited) + cp5/test_acled_cutoff.py (1 passed guarded, lock venv; the first try used the operator venv, which lacks pytest: INTERMEDIATE log kept).
- On terminal success, after step 5 (links), run guarded with the operator venv, PYTHONPATH and project env:
  7. cp5/acled_cutoff.py cp5/post-real.json cp5/inventory-post-real.json 2026-09 cp5/acled-cutoff.json
  - It writes or reuses the sha-verified cp5/batch-manifest.json and cp5/batch-feature_provenance.csv.
  - Every acled_agg_* section must have: polygons == bound roster, month_lag1, feature_month 2026-09, dependency_end 2026-08, nonblank latest <= 2026-08 (blank counts reported), source acled_agg_weekly at v2 with the post HEAD sha (== batch retained_inputs), and the fill-audit declared sha == the sidecar.

## Update 03:50Z: TERMINAL SUCCESS; CP5 readbacks done
- The run SUCCEEDED and was published (current #1793503777656101). See cp5/cp5-result.md and cp5/SHA256SUMS.final.
- Steps 1-7 all ran guarded with child exit 0; steps 1, 3, 4, 5 and 7 PASSED. Step 6 DA2 was observed under the local-credential label.
- The poll and sampler ended normally. No further cloud action is pending. NEVER resubmit.
