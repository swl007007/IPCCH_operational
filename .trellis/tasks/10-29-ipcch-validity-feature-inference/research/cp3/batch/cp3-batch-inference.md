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

## Supervisor review of ced8e52/8e00c8a - repairs (all behaviour/contract class, fixed across producers + consumers)
1. Namespace admission before reads: `load_batch(..., batch_root=...)` validates the mode root (StoreRoot) and requires
   the manifest ref to be `<root>/feature_batches/<batch_id>/manifest.json` before reading; each horizon file must be
   its canonical path before reading. Spy test: /real/ manifest ref, real root for a smoke request, and a manifest whose
   horizon file points into /real/ -> refused, zero /real/ touches.
2. `score_batch` re-verifies the package itself (`binding.package_identity`: every member re-hashed, no unlisted
   file) and requires manifest sha256 + combination id == binding: an unrelated package with the same id/order/cutoffs
   and a tampered member are refused.
3. Roster bound to the store pairing in BOTH write and load (`bound_roster`: size + file-form sha256 == the
   initialisation pairing; real = the envelope's accepted roster): a 3-area caller roster against a 5-area bound real
   roster is refused before any batch file; smoke keeps its declared fixture subset.
4. Horizon metadata: exactly H2/H8/H14; per horizon H, public lead, O = M - 2 and T = O + H must equal the request
   (target 1999-01, lead 0 for H8, wrong O, wrong H all refused).
5. area_id must equal admin_code (write and load); duplicate column names refused at write; ragged rows (extra leading
   field or short row) refused at load via the shared `retained.strict_csv`.
6. `wfp.parse_refresh` uses `strict_csv` with the exact header: `9999,1,2026-08,123.5` under a 3-field header and a
   short row are refused before any write. The same strict parser now reads every refresh file in generation (research
   families via wfp.parse_refresh, idp_national, history_snapshot, ACLED export).
7. Initialisation = HEAD existence (`retained.require_initialised`) in wfp.apply, the generation research-family path,
   GPP and nightlight (append-only histories additionally refuse an empty frame explicitly). Test: valid empty
   replacement -> keep -> refresh recovers; a never-initialised table is refused.
Provenance: WFP/research-family/ACLED method, source and coverage stay in the generation report -> batch manifest.
Caveat documented in wfp.py: the research centred +/-6-month outlier filter can embed later prices in a historical
value; training compatibility is not an as-of/causal claim; no algorithm change or retraining.
Regression `batch-review-fix-tests-run1.log`: test_ipcch_*.py + request_v2 + population 197 passed (locked interpreter).
