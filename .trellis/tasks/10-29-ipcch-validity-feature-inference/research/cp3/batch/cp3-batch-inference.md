# CP3 R52 feature batches and R19 batch inference (Executor, 2026-10-30)

`cloud/ipcch/batch.py`: `new_batch_id` (`ipcch-<M>-<run_id>-<uuid12>`, unique per call, bound to run id and M);
`write_batch` validates (mode == binding mode, mode namespace root, H2/H8/H14 exactly, columns = identity + bound
527 order, rows == roster (real full / smoke declared subset), unique keys, no inf) then writes h02/h08/h14.csv,
summary.json and manifest.json (LAST) create-only under `<root>/feature_batches/<batch_id>/`; existing objects refuse
(never overwritten, never cleaned). Manifest: M, O, mode/designation, combination reference (envelope id/sha, package
manifest, feature order, handoff manifest, per-scope cutoffs), per-horizon file generation/sha256/rows/target month/
public lead/missing counts, generation report (methods, coverage ends, gaps, warnings), acceptance consumed, retained
input refs, generated_at. Returns the manifest ref {uri, generation, sha256}.

`cloud/ipcch/batch_inference.py`: `load_batch` (pinned generation + sha of manifest and each file; schema/batch id;
mode + designation (real rejects dummy); M and O = M-2; exact combination match incl. per-scope cutoffs (R19); roster
sha; header duplicate names rejected; missing required columns rejected; extras dropped; reorder by model names; strict
numeric parse: blank/NaN missing, unparseable text or +/-inf fail with area + column; roster-exact unique rows).
`score_batch`: unchanged runtime path load_scope_package -> apply_feature_contract (must pass) -> score_scope
(thresholds, cummax, phase decoding, no clipping); nonfinite raw outputs located per target first (area/horizon/field,
R18); raw scores outside [0,1] counted; predictions carry mode and batch_id (R36).

Tests `tests/cloud/test_ipcch_batch.py` (10) with a loadable synthetic package (tiny XGBoost models on the 527 order,
real contract/metadata formats): round trip bit-exact + scoring through the runtime for 3 horizons; immutability and
unique ids; write refusals (dup keys, missing row, inf, order); load refusals (another combination with same 527 names,
M, batch id, roster, manifest sha, tampered file); parse reorder/extras/dup header/missing column/unparseable/-inf;
nonfinite model output -> area '12' H2 phase2_worse_score; real request rejects dummy batch. Regression
`batch-tests-run1.log`: test_ipcch_*.py + population 155 passed. Real accepted package scoring is CP5 integration.
