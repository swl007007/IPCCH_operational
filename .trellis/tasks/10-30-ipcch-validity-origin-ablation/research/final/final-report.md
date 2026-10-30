# Final report — IPCCH validity origin ablation (task 10-30), Executor

## What was run
Three fixed-parameter formal refits (H0/H6/H12) of the CH-final runs of `validity_augmented_idp_202610_acledagg_lag1_uncal_hpt`
whose only intervention is the backbone fitting-label membership: every scoring context — the annual historical contexts AND
the 2026 holdout context (hHH_supp_2026) — keeps only the final CH-corrected `label_kind == original` rows of its CH-final
fitting pool (after the inherited cutoffs and family/alias exclusions). Frozen
parameters, seed, per-row 24-month half-life weights (not renormalized), features, histories, contexts, cutoffs and identity
calibration unchanged; no HPT, no extra seed; the full inherited cohort is scored; the CH-final runs are linked, not refitted.

| | H0 | H6 | H12 |
|---|---|---|---|
| Vertex CustomJob | 2842603222726606848 | 2596031143128072192 | 3377405678476853248 |
| provider start → end (UTC) | 18:20:31 → 18:35:07 | 18:20:21 → 18:30:55 | 18:36:36 → 18:46:10 |
| MLflow run (IPCCH dashboard, exp 2) | bd24976069ee4530bb97343c1ec6e730 | eb33b087fe314237ad1c6432bcfe140f | 8237e829dc4b42169ccb3136c19aafb2 |
| LoggedModel | m-055654f09a78436593ce720f4c52be10 | m-daad991238a5430eb504eaacd4046d36 | m-9f73aac99f444c91b8022ec9f6e41df3 |
| registered model (v1) | IPCCH Original-label fit ablation (GOSIF v3 + CH validity 20261028) \| …_hpt \| 0-month | … \| 6-month | … \| 12-month |
| linked baseline (CH-final run) | 298c4718b4d64e6f8a5c315e8c22d25d | 00d4e94c824343bf86a0c2b79d5b9ed0 | f436da15c71c469199784db065f3b63b |
| original-only fit rows per context (copies removed) | 19,169 / 24,197 / 28,551 / 37,759 (55,741 / 69,931 / 82,756 / 91,391) | 21,282 / 22,478 / 27,134 / 34,004 | 21,282 / 25,960 / 30,784 |
| contexts / scalar fits | 4 / 16 | 4 / 16 | 3 / 12 |
| scored rows (full inherited cohort) | 70,972 | 61,042 | 52,027 |

Image `training-ipcch-validity@sha256:b208b1320033473af374dc1e08fbdac36a0fbbda993f7831bb1f579f94a9d197` (Cloud Build
22176002-a56f-47df-ab67-ede2ba8c68da) = base fd921dd7 (control-plane 439a488) + features eace18fd (CH-final, unchanged) +
pooled d2c07d7d + dataset_input 2b74098a (worktree commit 7023d10; 868db9f adds a test). Lineage proof: research/cp2 + staging check/lineage-proof.json.

## TUI (independent recompute, research/cp4/final/recompute/tui.md; F1 = binary phase ≥ 3, R2 = phase-3+ share)
original = original-only model on the CH-final original rows; matched = CH-final augmented model on exactly those keys/truths;
total = CH-final model on all inherited rows; Δ = matched − original (positive = augmented training better on originals).

| H | period | N orig | F1 orig | F1 matched | ΔF1 | R2 orig | R2 matched | ΔR2 | N total | F1 total | R2 total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 2023 | 4,925 | 0.8210 | 0.8072 | −0.0138 | 0.5434 | 0.5356 | −0.0078 | 18,945 | 0.8168 | 0.6184 |
| 0 | 2024 | 4,295 | 0.8157 | 0.8161 | +0.0004 | 0.5418 | 0.5264 | −0.0154 | 17,033 | 0.8086 | 0.5401 |
| 0 | 2025 | 9,792 | 0.7812 | 0.7666 | −0.0147 | 0.3638 | 0.2915 | −0.0723 | 19,677 | 0.7378 | 0.3602 |
| 0 | pooled 2023-25 | 19,012 | 0.7976 | 0.7861 | −0.0114 | 0.4584 | 0.4180 | −0.0404 | 55,655 | 0.7853 | 0.5160 |
| 0 | holdout 2026-01..10 | 5,842 | 0.8167 | 0.7838 | −0.0329 | 0.3925 | 0.3245 | −0.0679 | 15,317 | 0.7572 | 0.2973 |
| 6 | 2023 (07-12) | 2,326 | 0.7902 | 0.7989 | +0.0087 | 0.5275 | 0.4859 | −0.0416 | 9,015 | 0.8223 | 0.6011 |
| 6 | 2024 | 4,295 | 0.7978 | 0.7996 | +0.0017 | 0.4395 | 0.4032 | −0.0363 | 17,033 | 0.7983 | 0.4772 |
| 6 | 2025 | 9,792 | 0.7795 | 0.7828 | +0.0034 | 0.3076 | 0.3231 | +0.0155 | 19,677 | 0.7639 | 0.3755 |
| 6 | pooled 2023-07..2025 | 16,413 | 0.7850 | 0.7886 | +0.0036 | 0.3799 | 0.3737 | −0.0062 | 45,725 | 0.7875 | 0.4634 |
| 6 | holdout | 5,842 | 0.8089 | 0.7837 | −0.0253 | 0.3802 | 0.3036 | −0.0766 | 15,317 | 0.7632 | 0.3145 |
| 12 | 2023 | 0 | NA | NA | NA | NA | NA | NA | 0 | NA | NA |
| 12 | 2024 | 4,295 | 0.7547 | 0.7415 | −0.0132 | 0.2389 | 0.1787 | −0.0602 | 17,033 | 0.7551 | 0.3134 |
| 12 | 2025 | 9,792 | 0.7730 | 0.7644 | −0.0085 | 0.2986 | 0.2598 | −0.0389 | 19,677 | 0.7476 | 0.3447 |
| 12 | pooled 2024-25 | 14,087 | 0.7681 | 0.7585 | −0.0097 | 0.2843 | 0.2392 | −0.0451 | 36,710 | 0.7510 | 0.3297 |
| 12 | holdout | 5,842 | 0.7913 | 0.7932 | +0.0019 | 0.2648 | 0.2694 | +0.0047 | 15,317 | 0.7633 | 0.2584 |

H12 2023: "no evaluation rows: 2023 precedes the H12 historical window starting 2024-01". Observed months of the original
subsets end before the declared window ends (2024-11, 2025-10, 2026-09: no original labels in the last months); declared and
observed windows are listed per cell in tui.md. Point estimates and paired differences only (one seed; no interval/test).

Reading: on the original-label evaluation rows the original-only model is at least as good as the augmented model in most
cells — clearly so on the 2026 holdout at H0/H6 (ΔF1 −0.033/−0.025, ΔR2 −0.068/−0.077) and on H0/H12 historical R2 — while H6
historical F1 slightly favours augmented training (+0.002…+0.009) and H12 holdout is near zero (+0.002/+0.005). "Total vs
matched" mixes copies into the population and is not a model effect.

## Verification (all receipts in research/)
- CP0 pins/preservation (cp0/); CP1 no-fit gates, independent verifier, A2 pre-fit pairing (cp1/); full pinned-code regressions
  before/after (cp1/regression/: 159 numerical tests + 72 tooling passed).
- CP2 build once (cp2/build/); CP3 jobs once each, no retry (cp3/jobs/): harvest 17/17 checks per horizon, holdout + annual
  package replays passed and bound to the current packages.
- CP4 final read-only packet once (cp4/final/, final_pass true): identity chain, independent recompute (A4 baseline
  reproduction), 3 job logs, MLflow readback 6/6 (incl. CH-final baselines unchanged), real headless-Chromium UI with 14 targets
  and the Dashboard Experiments tab listing all six runs, ui_pass true.

## Reproducible tools
Pinned sources of every released packet (recipes, verifier, builder, lineage proof, job/final/cleanup tools, independent
recompute and tests) are copied byte-for-byte into research/tools/ (MANIFEST.tsv: origin path + sha256, 103 files); the runtime
modules are in the research worktree commits 7023d10/868db9f (branch task/ipcch-validity-origin-ablation).

## Cost
Reserved (ledger, 2026-10): build 0.19 + platform 0.90 + training 3 × 1.9073 = USD 6.81 of the USD 7.00 task cap (reservations,
not billing). Compute-only estimate: provider start→end 876 + 634 + 574 = 2,084 s; rate = n1-standard-16 USD 0.8739954/h + 100 GiB
pd-standard 100 × 6.3014e-05 USD/GiB-h = USD 0.8803/h (the reservation rates in job-packet/reservations.json, price source
"preflight Q1 2026-10-26 (task 10-26; via 10-28)"); 2,084 / 3,600 × 0.8803 ≈ USD 0.51. Excludes queueing/boot, the build,
storage, logging, MLflow/Cloud Run and egress; billed actuals are not asserted. Platform pool 99.99/100, training 152.30/200.

## Limitations
Inherited: nominal CH reference-start availability (retrospective convention, not strict real-time), oracle weather features at
H6/H12, retrospective input vintages, tuning on the reported historical years, 2026 outcomes previously inspected. Specific: the
original-only fits use ~26 % of the CH-final fitting rows with unchanged (not renormalized) weights, so the contrast combines the
absence of copy supervision with a smaller fitting sample; final label_kind is the CH-final classification. One seed; no
significance claim; no performance-improvement gate.

## Retention (R9 / A6)
Cleanup packet r1 executed once after the final read-only packet passed: the fresh plan equalled the reviewed dry run
(a0b255c8…, 32 targets); 32 annual booster files (H0 12, H6 12, H12 8) deleted with generation match, each read back as absent,
and the 32 local copies removed (research/cp4/cleanup/01-execute.json). Post-check (02-post-verify.json): every other trial
object unchanged at its harvest generation (78/78/74), every retained local file present, the three holdout packages
(published LoggedModels) verify, annual package.json/records/routing/reference kept as evidence. Retained long-term: the three
final holdout weight sets, all keyed annual/holdout predictions, configs/params/pins, memberships/histories, metric/report
files and receipts. Nothing in MLflow and no baseline object was touched.

## Acceptance
Supervisor final acceptance recorded in research/final/supervisor-final-acceptance.md (against ad34381 / research 868db9f):
R1-R11 and A1-A6 met.
