# Supervisor acceptance of final v2 fitting input

At the 2026-10-22 S10 checkpoint, local full-history production-data fitting is released under the already approved specification. Candidate publication, deployment and promotion remain subject to their separate readiness and maintenance checks.

## Input and method evidence

- `p1b/input-freeze-v2.json` at commit `2af2a89` binds the normalized panel `02caeb8617507028943efee21a68066daded66857de0dff758062b2859fd583a`, normalization audit `65ea96d5e34315ea160b85c5ad20e995401e9d77234520380fff84529b04cdcc`, source panel `a83f5f4b5eb33022960e43606f32afaec0cb15c10110ad1b56564790d637b722` and keyed change ledger `9dffea614d1109f61115da380b81d30148b268938848096ac1885dcdc7c326f8`.
- `supervisor-v2-input-verification.json`: independently rehashed six frozen references and compared every cell of v1/v2. The 1149318-row key universe is identical. Only missing EVI September cells (5716) and WFP January price/std cells (3358 area rows, 6716 cells) changed. All labels and every other field are unchanged. Existing pandas CSV round trips introduce at most 1.36e-12 EVI / 1.42e-14 WFP absolute differences from their keyed sources; the recorded comparison uses absolute tolerance 1e-10, zero relative tolerance. No scientific transformation changed.
- `supervisor-wfp-boundary-verification.json`: original notebook cells 27-31 establish the MoM definition; independent source-file date scans establish the January 2025 boundary. Earlier unknown-definition gaps remain missing.
- `supervisor-evi-completion.json`: exact EE task COMPLETED, extraction hash/roster match, 5716 nonmissing areas. Source update time is within the agreed cutoff. The initial local post-export attribute error was recovered from retained shards, as recorded by the executor.
- Initial v1 label and calendar evidence remains applicable because labels/keys are unchanged: 273353 / 264005 / 254291 eligible rows, 54 / 52 / 50 target months and 4039 June 2026 targets per horizon. No holdout, threshold search or performance evaluation is authorized.

## Fitting identity and release boundary

Use the verified exact-lock Python 3.12.3 environment `/home/swl007007/.venvs/fewsnet-fit-lock-20261022` and clean worktree `S/fit-source-ff389b1`, commit `ff389b11af93f08e748ffdf86ab8cccae09fb3ff`. Supervisor verified that the fitting module tree is unchanged from current HEAD and the worktree is clean with the process-scoped partition-map checkout attribute. Preflight is `S/runtime/fit-preflight-ff389b1-v2.json`.

Run the existing full-history entrypoint with origin 2026-10, latest label 2026-06 and three horizon workers. Expected suite: `full-202610-ff389b11af93-02caeb861750`. Preserve fixed thresholds, feature/map identities, fit keys/counts/exclusions and runtime/package hashes. This is permission to execute the approved fit, not a claim that fitting or AC2/AC3 is complete.

The separate in-process preparation is acceptable for pre-release data building because it uses the actual existing production acquirer and truthfully records its execution source. It must still produce succeeded state, immutable compatible outputs and final overlay checks before release. It does not replace the required cloud Workflow dispatch implementation. Final delivery must use the refreshed FEWS source panel: prepared history alone is not loaded by `load_prepared_features`. Retain the inherited IPCCH panel and skip its inference.

The frozen-confidence component now additionally retains raw diagnostic evidence and original declarations under distinct portable paths (`82a4a0f`). Full candidate integrity, selective offline replay, six-slot new-image loading, maintenance and promotion checks remain pending.
