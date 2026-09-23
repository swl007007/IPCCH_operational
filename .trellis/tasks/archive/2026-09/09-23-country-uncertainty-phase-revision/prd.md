# Country uncertainty and phase revision

Status: approved for execution by the user on 2026-09-23 ("按照落盘的spec执行"); execution plan in implement.md.

## Goal

Revise country-level diagnostics and outcomes for the September 2026 h5 delivery, using `Outcome/model_delivery/202609_h5/20260911_training_confidence_v2` as the unchanged parent and writing a new sibling `20260923_country_confidence_v3`, for downstream web application integration. Brainstorming and sequential grilling decisions are consolidated in design.md.

## User requirements

- The requested task creation and audit registration are already complete. Continue the existing task and exact registered repository path; verify current durable state and the bound Claude executor before start/close, without creating a duplicate task or registration.
- FEWSNET: locate saved Stage3 area predictions for 2021–2024, compute area error rates and then country error rates, and replace the previous training-error rate and confidence flag.
- Confirmed 2026-09-23: the historical Stage3 series may be called the h5 validation-error proxy, per meeting agreement. Export polygon-level confidence calculated from the historical data; preserve its actual source metadata.
- Confirmed 2026-09-23: `polygon_confidence = 1 - polygon_error_rate`; export historical observation and error counts alongside it.
- Confirmed 2026-09-23: FEWSNET country error is also population weighted: `sum(population * polygon_error_rate) / sum(population)`, matching IPCCH's aggregation rule. Both models reuse existing delivered polygon population snapshots and retain population dates and sources.
- Confirmed 2026-09-23: retain polygons lacking error evidence or valid positive population, but exclude them from country error weighting. Aggregate and classify eligible records; report coverage and exclusions without filling zeros or downgrading flags. If no eligible records exist, country error and flag are null. No additional coverage/sample-size cutoff is introduced.
- FEWSNET: add a binary country outcome-crisis flag using a 0.5 threshold.
- IPCCH: use population-weighted area errors for country error rates; replace the forced-relative-quota confidence flag with a threshold-based flag.
- Confirmed meeting decision, 2026-09-23: IPCCH retains the existing saved training-resubstitution Phase3+ binary error rates. Change country weighting and confidence policy without switching the error evidence source or event definition; do not re-request approval for this decision.
- Confirmed 2026-09-23: both models use the same three country confidence categories: `high` for error<=10%, `medium` for 10%<error<=20%, `low` for error>20%, evaluated before rounding. Read-only candidate impacts are recorded in design.md; delivered tables remain unchanged during planning.
- IPCCH: derive country overall phase using the cascading 20% rule.
- Confirmed 2026-09-23: add `country_maximum_phase` and its uncertainty only for IPCCH, using its area Phase1–5 predictions. FEWSNET has only the requested country crisis0/1 flag. The maximum-phase uncertainty must address predictive correctness (whether the maximum phase is wrong), not stability under polygon resampling. The user adopted transferring whole complete-month training residual fields to September cumulative scores, decoding stages and comparing maxima, with bootstrap by complete historical month. Label the result as a training-error-based probability proxy.
- Confirmed 2026-09-23: use10,000 bootstrap replicates, a fixed random seed and95% intervals. With only one complete historical month, output the point proxy but leave its interval null, explaining that month-to-month variation cannot be estimated; no complete months gives null point and interval.
- Confirmed 2026-09-23: country error rates remain population weighted, but maximum-phase uncertainty resamples whole country/month error fields without population weighting, retaining the full polygon roster and within-month error association. This supersedes the initial population-weighting preference for maximum-phase uncertainty only.
- Confirmed 2026-09-23: for full-phase errors, derive actual Phase1–5 from actual cumulative population shares with the same >=0.2 cascading rule used for predictions. Do not mix this target with the panel's alternative `overall_phase` labels.
- Confirmed 2026-09-23: only historical months covering the full delivered country polygon roster support maximum-phase uncertainty. Zero complete months gives null uncertainty (currently10 countries); at least one permits an estimate (currently43 countries), with month count and single-month bootstrap limitations disclosed. Country maximum phase itself remains available. Do not add a minimum-month cutoff or impute missing-area evidence.
- Keep methodology, evidence source, period, population basis and support visible in exported outputs.

## Constraints carried forward

- Existing model weights and September polygon forecasts remain fixed unless separately authorized.
- No TDD or regression suite; focused checks and independent verification only.
- No web application implementation, cloud deployment or remote push.
- Confirmed 2026-09-23: preserve existing v2 and write the full revised model package, country tables and uncertainty evidence to `Outcome/model_delivery/202609_h5/20260923_country_confidence_v3`.
- Do not replace FEWSNET's approved historical Stage3 proxy with final-model training replay. IPCCH's approved saved training errors and four-target residual replay remain in scope and explicitly labeled as training-based evidence. Do not equate spatial bootstrap stability with forecast calibration.

## Acceptance criteria

- [ ] Historical FEWSNET prediction source, date meaning, horizon and area threshold are explicitly approved and recorded; all joins and missing polygons are accounted for.
- [ ] Country errors reproduce independently from saved row evidence and area rates using the approved weighting basis.
- [ ] Confidence thresholds, exact-boundary behavior and insufficient-evidence handling are explicit and validated; no forced 20% low-confidence quota remains in the revised policy.
- [ ] FEWSNET country crisis flag follows the approved score interpretation and 0.5 boundary.
- [ ] IPCCH country phase and maximum-area phase are separately exported and verified.
- [ ] Maximum-phase uncertainty has an approved estimand, sampling unit, population-weighting rule and limitations; bootstrap settings and support accompany results.
- [ ] Original model and retained polygon forecast values are preserved; formal CSVs, README, runtime behavior, inventories and archive agree.
- [ ] Approved spec/plan are committed before the verified executor starts the audit run; completion includes accepted independent audit evidence.

## Planning documents

`design.md` is the consolidated spec and evidence inventory for final review. An execution plan follows written-spec approval; audit start follows approved and committed spec/plan.
