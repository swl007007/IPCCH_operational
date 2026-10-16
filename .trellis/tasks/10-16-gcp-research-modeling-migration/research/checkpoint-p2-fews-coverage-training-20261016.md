# Checkpoint: FEWS package coverage and FEWS training adapter, 2026-10-16 06:54 EDT by `date`

Native HEAD is `713e350`. Everything here is local; there is no cloud operation.

## FEWS package receipts (current)

| Group | Code | Result | Receipts |
|---|---|---|---|
| Ordinary D35/37/38/46/47/48/51/52 | 066a09a (completion-bound, loader length) | 8/8, 10,752 rows; source probabilities scanned: 0 non-finite (NaN-safe builder check added later, no rebuild needed) | `p2-packages/replay-fews-ordinary-066a09a` |
| Map transfer D42/D43 | 8d779ff (cap scope metadata) | 2/2, 11,356 rows | `p2-packages/replay-fews-map-8d779ff` |
| Stage-1 candidates v1, D26-D31, D34 | 78ae83f (completion binding, content checks, explicit system/root) | 8/8, 12,912 rows; all 1,614 served units have rows | `p2-packages/replay-fews-stage1-78ae83f` |
| v1 global screen (72 globals) | 1cde8f6 (horizon key validation) | 1/1, 1,152 rows; 390,408 rows checked at build | `p2-packages/replay-fews-globals-1cde8f6` |
| scen actual (8) | 22150fe (exact width) | 8/8, 3,200 rows; supersedes `replay-fews-scen-1a7e207` | `p2-packages/replay-fews-scen-22150fe` |
| confirm-onset pooled S0/S3 | 22150fe (exact width) | 2/2, 800 rows; supersedes `replay-fews-confirm-3bee169` | `p2-packages/replay-fews-confirm-22150fe` |

- **confirm-onset system arm:** not packaged. The user's disposition is pending, and nothing is substituted.
- **Preservation-only records** (minirun-1/2, smoke-2, d34/d37/d38 replay evidence, failed_stage1): byte manifests only; no references are invented.
- **Per-root manifests** for all 27 roots, plus the loose top-level files, are being written to `scratch/preservation/` (code 991e27a).

## FEWS training adapter (713e350): `p2-training-fews-713e350`

- **Feature snapshot.** `fews_features` rebuilds Availability on Linux from hashed base inputs for H4 2019-02, k=0, strategy A.
  - The fitting cohort (81,979 keys) and target cohort (5,365) equal the original scen root membership exactly.
  - The pool's keys, labels and full feature matrix equal the original k0/A global's recorded digests.
- **Trial adapter.** `fews_fourclass`:
  - default trial: crisis F1 0.7916 on the target cohort; second trial (max_depth 2, rounds 150): 0.7835; tuning `objective` is refused;
  - the trial package replays 200/200;
  - 3 boundary tests pass.
- **Platform finding.** The default trial booster equals a Linux fit with `plan.G_CONFIGS['G1']`, and Linux refits are repeatable. It does NOT equal the Windows-trained original (max |Δp| 0.115, 43/5,365 argmax), despite identical inputs and parameters. Cloud training is therefore a new research identity, never a historical substitute; historical inference replays exactly through the packages.

## Cost ledger (ccd1fd2 + e79ccad)

- Atomic separate-pool admission.
- Reservations are held until the provider reports a terminal state.
- Transitions are atomic, and caps and reservation inputs are validated.
- Not yet wired to a submission; it comes before any job.

## Next

1. Pinned images (service and training, both families).
2. Final regional quote and cost ledger entries.
3. G5-G11 cloud operations with receipts.
4. Merge native commits before close.
