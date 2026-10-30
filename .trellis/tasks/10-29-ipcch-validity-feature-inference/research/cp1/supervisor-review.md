# CP1 supervisor review — in progress

Status: discovery builds reviewed; CP1 is **not yet accepted**. No paid training/build or cloud mutation released by this review.

Executor remains Herdr `w1A:p2`, Claude session `6a490ae1-ee00-43f9-bdfc-c887c9816c09`. Operational goal remains active under execution-protocol.md; no Trellis Audit.

## Independent checks, 2026-10-30

Reviewed the current research diff in `control-plane-h2h8h14`: mapped frozen-winner validation, final supplement-only schedule, input/schema/cohort gates, oracle omission, and GPP availability masking before derived features. No additional blocker identified in this spot-check; this is not final implementation acceptance.

Read actual discovery outputs under `/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-cp1/gate-unpinned-h{02,08,14}/equivalence.json`. Independently compared each generated ordered feature-name list against `scratch/ch-validity-20261028/harvest/formal-h00/trial-0/package/deps/feature_order.csv`: all 527 names and their order match exactly.

| Horizon | Fit rows | Fit copies | Fit cutoff/max target | Scored rows |
|---|---:|---:|---|---:|
| H2 | 128090 | 90331 | 2025-11 | 15317 |
| H8 | 121096 | 87588 | 2025-05 | 15317 |
| H14 | 110762 | 81950 | 2024-11 | 15317 |

Each discovery output records unique area/target keys in fit and score, no overlapping row indices, and true temporal/excluded-family checks. These are inspected builder assertions, not an independent recomputation of every membership. All three commands correctly exited 1 against placeholder cohort/digest pins. They are discovery evidence, **not passing final gates**.

H2 GPP summary has all-NaN origin value and origin same-month z columns; retained NaNs are consistent with the accepted release-log timing. This review does not authorize imputing or deleting those features.

## Required before CP1 acceptance

- Fixed recipes must pass real unmocked builds with exact measured cohort/digest pins.
- Post-change regression must finish successfully; 18 focused tests include mocked builder route tests and alone are insufficient.
- Supplementary tooling-environment tests must be labelled separately from locked numerical-environment tests.
- Review concrete immutable image/input/output identities, cloud commands, quota/concurrency and bounded cost packet before releasing any paid operation.
- Preserve failures and exact exit codes; update checkpoint and PROGRESS.md with actual outcomes.

## CP1 accepted; CP2 build release — 2026-10-30

All three pinned real builds exited 0. Supervisor directly loaded each `gate-pinned-hHH/{gate,equivalence}.json`: passed=true, 527 features, 15317 scored rows. The earlier discovery counts/cutoffs and feature order remain valid. Core regression: 139 tests OK, exit 0; direct four-class: 21 tests OK. Supplementary DatasetInput: 27 passed; HPT control: 107 passed after selecting the existing mlflow-svc environment with google.api_core. Original missing-dependency failure is preserved. Tooling test environments remain distinct from the numerical lock.

Supervisor ran `verify_packet.sh` successfully: 34 packet files, external helper pins, clean research commit `9aa9e5427ffb3d21d7ccb5fc833c119b12de3ac9`. Packet root: `/home/swl007007/projects/food-crisis-research/staging/ipcch-h2h8h14-20261030`. SHA256SUMS hash: `6405b73b130ec19768807d69840794aef8a3d3a8d64db1ab7545bf2b619e5060`; reservation plan hash: `9e36cb1979f4ffb82a185570df608031e83d9d5f3d870b66645c0474122862c2`.

Under existing user cloud preauthorization, release packet steps 0–3 only: verify pins, reserve the USD 0.19 build line, one bounded Cloud Build in food-crisis-modeling-enso, and generate local specs from the successful immutable image digest. No retry/rebuild on failure or uncertain submission; reconcile read-only and return concrete evidence to Supervisor. No job submissions, six-object uploads or job reservations yet: those await inspection of the generated digest-bound specs and in-image checks. No deployment/live-current changes.

CP1 is accepted. CP2 remains in progress, not complete. The USD 6.9119 overall estimate is not a billing-enforced cap. In-image exact-lock checks must pass despite the disclosed local certifi drift. Executor should prepare C6/C7 evidence/package work locally while the build runs.
