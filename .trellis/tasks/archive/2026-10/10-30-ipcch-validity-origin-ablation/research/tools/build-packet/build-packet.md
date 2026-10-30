# Origin-ablation build-only packet r1 — task 10-30 (NOT released; prepared locally, no cloud command run)

Why: the original-label fit ablation changes training code (`ipcch_validity_pooled.py`, `dataset_input.py`), so the
formal jobs need a new overlay image (RUNBOOK build rule; CH task 10-28 precedent). One build, new tag, no rebuild.

`W=/home/swl007007/projects/food-crisis-research`, `B=/home/swl007007/projects/food-crisis-research/staging/ipcch-origin-ablation-20261030/build-packet`, `PY=$W/envs/mlflow-svc/bin/python`, cwd `$W/control-plane-origin-ablation` (clean, HEAD 868db9f),
`PYTHONPATH=.`, `PYTHONDONTWRITEBYTECODE=1`. Every packet file is pinned in `$B/SHA256SUMS` (`cd $W && sha256sum -c $B/SHA256SUMS`).

## Image (context generated locally, not built)

| | CH-final (task 10-28, job image of the baseline) | this packet |
|---|---|---|
| base | `training-ipcch-validity@sha256:fd921dd7…ca939` (control-plane 439a488) | same digest |
| overlaid | dataset_input a6d05b24…, features eace18fd…, pooled d7f78e3a… | dataset_input **2b74098a…**, features eace18fd… (identical), pooled **d2c07d7d…** (commit 7023d10; HEAD 868db9f adds tests only) |
| Dockerfile | FROM + 4 COPY + 1 ENV (no RUN) | same structure (no RUN, no dependency install) |
| tag | gosifv3-chvalidity-20261028 → digest 2b18cf72… | **gosifv3-chvalidity-originfit-20261030** (new; precheck must be NOT_FOUND) |
| context record | 2b391f4e… | **c98e85577ce655e3f5243306d9ee6c85a400dec3513044fe219140b0f18f0266** (9 files; `image-overlay-origin.context-record.json`) |

Lineage proof (`check/lineage-proof.json`, passed; tool `tools/lineage_proof.py`): the CH-final job image is itself
FROM fd921dd7 + its three modules + /app/overlay + ENV (CH context files re-hashed equal to its record, record sha pinned by
the CH build summary; CH build SUCCESS with in-image selfcheck and overlay_check as uid 65534 without network; digest/tag
readback). The new context has the same base digest, instruction list, overlaid paths, base-context manifest, expected
runtime (python 3.12.3, numpy 2.4.4, pandas 3.0.3, scikit-learn 1.8.0, xgboost 3.2.0, mlflow-skinny 3.17.0,
cloudml-hypertune 0.1.0.dev6), declared base hashes and build steps; the features module is byte-identical; the only module
differences are pooled and dataset_input. Every other /app file and every installed dependency is the base image's in both.
FROM 2b18cf72 is not used because it would inherit the CH /app/overlay and break the single-BASE overlay check.

In-image checks (unchanged r1 CHECK + one added assertion that the adapter carries ORIGIN_KIND and FIT_LABELS), simulated
locally on the BASE 439a488 tree + the three modules in the pinned venv: `overlay_check: ok`, 237 files, derived-vs-BASE
exactly the three modules, runtime and composite source id equal (`logs/overlay_check_sim.*`). `selfcheck --image
training-ipcch-validity` simulated: every code-dependent step passed (overlaid-module imports, AlphaEarth, tiny XGBoost fit,
direct four-class, HPT controller + check_config of the three tuning recipes with the new pooled module, parquet); it stops
at the final lock comparison on the LOCAL venv's certifi 2026.10.19 vs image lock 2026.7.22 — identical terminal condition
to the CH simulation (`logs/selfcheck_sim.*`), an environment difference of the local venv only.

## Ledger (read from a temporary copy; real ledger sha bd506297… unchanged)

Current month 2026-10: platform 98.90 / 100 (**headroom USD 1.10**), training 146.58 / 200 (headroom 53.42). These committed
amounts are earlier tasks' reservations; none is reused or counted for this task. Dry run of this packet on a copy
(`reserve-dryrun-on-copy.json`): platform 98.90 → 99.09 (headroom after 0.91); second run refuses; real ledger unchanged.

Proposed fresh task cap USD 7.00: build 0.19 (this packet) + job-phase platform line ≤ 0.90 (job packet) + training
3 × 1.9073 = 5.72 (job packet; n1-standard-16, 7,800 s bound each) = 6.81. **Platform pool will be left with ~0.01 headroom
after the job packet; if anything else reserves platform money in between, the job packet's platform line will not fit and
needs a smaller line or a user cap decision.**

## Steps (each needs release; receipts under the operational task dir research/cp2/build/)

1. **Platform line (local ledger write)** —
   `IPCCH_ORIGIN_PLATFORM_RESERVE_CONFIRM=r1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $PY -B $B/reserve_platform.py --plan-sha256 05fa53ffb3356d8ce76618ffbac277160b933c1a6bd024590721623c39165af8 --out "<task>/research/cp2/build/01-reservation.json"`
   (prechecks: line absent; pool headroom; one `ledger.reserve` of `ipcch-origin-ablation-r1-build` USD 0.19).
2. **One build (paid)** — `bash $B/build_step.sh > "<task>/research/cp2/build/02-build.log" 2>&1; echo "rc=$?" >> "<task>/research/cp2/build/02-build.log"`
   — the CH build_step.sh with only paths, record sha, tag and receipts dir changed (`build_step.diff`): local
   re-verification of the 9 context files; tag precheck NOT_FOUND (read); ONE `gcloud builds submit` (one source tarball;
   build SA research-build@; us-central1; 1,800 s; CLOUD_LOGGING_ONLY; selfcheck + overlay_check as uid 65534, no network;
   pushes ONE image with the new tag); `builds describe` every 30 s; AR describe by digest and tag (must equal) → `02-digest.txt`.
3. Stop and report the digest. No retry/rebuild/tag move without release; an uncertain submit is reconciled read-only.

## Next (job packet, separate release after the digest)

Cloud configs = `candidate/final-r2` recipes with only `provenance.code_overlay` restated from this build; create-only
uploads of three byte-equal copies of the CH-final retained predictions (artifacts bucket → inputs store) + 3 manifests (the
CH uploaded manifests, every other role by generation) + 3 configs; job-phase platform line + 3 training lines; occupancy;
H0/H6 submit once each, H12 gated; poll; harvest; package replay (retained holdout package AND temporary annual package);
annual-package cleanup only after replay receipts; MLflow readback; Dashboard UI check.
