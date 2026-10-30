# Requirements → evidence (task 10-30)

| Req | Status | Evidence |
|---|---|---|
| R1 baseline = CH-final runs, retained predictions, never refit | met | cp0/cp0-pins.json (runs/configs/predictions hashed); comparison = retained predictions (byte-equal copies, cp3/jobs/02-uploads.json); readback baseline-hXX all_checks_pass (unchanged run/model/version/card, metrics/params = retained trial) |
| R2 original-only fitting = final label_kind == original | met | origin_gate checks (cp1/cp1-final-gates.md); harvest fits: train rows == pins, 0 copies, memberships exact (cp3/jobs/06-harvest-hXX.json) |
| R3 single intervention, no HPT/seed/renormalization | met | configs = CH-final recipe + origin block + metadata only (make_origin_recipes CHANGED_TOP/CARD checks); weights/targets/histories equal on originals (origin_gate); frozen params (params_sha256 pin) |
| R4 inherited scoring contexts, S_E/alias exclusions incl. copy families, histories | met | origin_gate scored_rows/S_E/excluded_eligible/score_history_unchanged; CH contract passed on unfiltered plans; A2 pairing in-job + verifier |
| R5 calendar (H6 Jul-Dec 2023, H12 no 2023, holdout 2026-01..10) | met | tui.md declared/observed windows; H12 2023 NA with reason |
| R6 TUI three groups x five periods, F1/R2/N, delta matched − original | met | cp4/final/recompute/tui.md + tui.csv; job origin_tui.csv reconciled |
| R7 pooled from rows, no holdout in pooled, negative R2 kept, NA not zero | met | recompute (pooled = concatenated rows; annual sums == pooled); test_recompute_origin 15/15; real self-validation |
| R8 full standard MLflow publication, distinct identity, truthful dataset metadata | met | readback formal-hXX all_checks_pass (run/LoggedModel/version/card/tags/DatasetInput/metrics); own dataset name + fit-subset tags; UI ui_pass (Dashboard Experiments tab) |
| R9 retain final holdout weights + all keyed evidence; annual weights removed only after verification | met | published packages = holdout only; replays 07-replay-*-hXX bound and final packet passed before cleanup; cleanup cp4/cleanup/ (plan == reviewed dry run, 32 deletes confirmed absent, 02-post-verify ok) |
| R10 point estimates only | met | no bootstrap/CI/tests produced |
| R11 NA reasons; unexpected empty/duplicate/mismatch stops | met | NA reasons in tui.md; strict pairing (recompute, ch_pairing, origin_score_check) with refusal tests |
| A1 pins + CH-final classification | met | cp0/, cp1/ (CH contract on unfiltered build == CH-final self-consistency) |
| A2 no-fit subset/weights/features/histories/score keys/truths/exclusions | met | cp1/cp1-final-gates.md, verify-final-r2.json, in-job score_pairing |
| A3 three workflows, fixed params, no tuning/refit | met | cp3/jobs (one submit each, SUCCEEDED, 44 scalar fits) |
| A4 TUI tables exact; baseline metrics reproduced; undefined disclosed | met | recompute passed incl. CH-final metrics.json + scalars reproduction |
| A5 MLflow readbacks + package replays + new identities + baseline records preserved | met | cp4/final/final-verdict.json (final_pass true); 07-replay-* |
| A6 final weights + keyed evidence retained; removed annual weights with receipts | met | cp4/cleanup/00-dry-run.json, 00c-plan-equality.json, 01-execute.json, 02-post-verify.json, SHA256SUMS-cleanup |
