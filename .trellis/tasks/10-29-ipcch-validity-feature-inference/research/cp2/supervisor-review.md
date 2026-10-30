# CP2 supervisor review — ongoing

Training release and image/spec pins: ../cp1/supervisor-review.md. CP2 is not accepted yet.

## Package review at f6822b5

Read `control-plane-h2h8h14-pkg/research_cloud/packages/operational_ipcch.py` in full.

- Blocking portability issue: main lines 225–242 wrote evidence to OUT/evidence while the package manifest in OUT/package referenced evidence/name. write_combination hashed only package files. A standalone relocated package therefore omitted its runtime diagnostics. Requested evidence inside package/evidence with manifest hashes, plus a relocation test without siblings and tamper rejection.
- Weight integrity gap: load_boosters lines 56–68 accepted missing weight hash entries. Requested mandatory weight hash verification and binding caller-supplied run identities to harvested publication records.
- Positive checks: exact fitted matrix/key/label digests and backbone membership checked; all actual fit rows retained; raw quartet used for threshold errors and residuals; JSON/UBJ comparison uses the full fit matrix; NaN passthrough and default 0.20/cummax metadata retained. These observations do not substitute for actual new-weight replay.

Executor was notified; fixes and tests pending independent review. Frozen training worktree must remain unchanged.

Follow-up: reviewed fix `3c8c4d6` diff and `c6c7-tests-run4-ok.log` (9 tests, OK). Runtime area/residual CSVs now reside under package/evidence and are hashed; row-level audit sidecars remain outside. Relocation/tamper/missing/unlisted tests cover the path fix. Weight loading requires whole-source package verification and each weight hash; supplied run identity binds to publication/package identity. These code findings are resolved, subject to actual three-model package replay. Minor test-layout note sent: move unittest.main guard below the added Portability class so direct script invocation includes it.

## Harvest

Reviewed read-only `staging/ipcch-h2h8h14-20261030/job-packet/harvest_final.py`, SHA256 `eb329e17b1ba3ee504cb2c73029151ab80910680a2ed66cc2fa46fa5a05f2caf`. Released after successful job termination: generation-pinned GCS download into new local destinations, pinned old transport helper, package/config/source/fitting identity checks. Local publication records are not independent live MLflow readback; that remains required.
