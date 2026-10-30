# CP3 real-mode LOCAL integration on the accepted handoff (Executor, 2026-10-30)

Scope: CP3 real handoff integration (distinct from the required CP5 fixture-only smoke; real-history reads here are NOT
smoke evidence). Local locked Python only (`fewsnet-test-lock-20261022`); the request's runtime image digest and
environment manifest are placeholders - this is not container/deployment validation. No cloud writes, no EE, no
production store or current; package/bundle bytes preserved.

Inputs: accepted envelope v2 (03b93842...), package 18b91d45..., bundle `out-r5-accepted-v1` (e6e3ebc6..., entries
cb14a956...), ACLED first refresh = research regional-aggregate exports f2+f3 concatenated byte-faithfully (f3 header
dropped), declared 2016-12-31..2026-10-16, 8 regions, sha256 7bcb051f... (BOM-prefixed, utf-8-sig decoding).
Request: real, M = 2026-10 (O = 2026-08), generation + inference, publication candidate (not published), through
`run_v2.run_request` (admit with trusted namespace + reference verification -> generation -> batch -> inference).

Run: `real_integration.py <R>/scratch/h2h8h14-final/cp3-real-integration/run2` (run1 stopped before any probe to add
probe timestamps/cap - log `run1-stopped-before-probes.log`, directory removed). Result `run2-result.json`
(= run2/result.json sha256 ba2bc4f8...), status succeeded, 299 s:
- initialise 52 tables + 57 delivered acceptance records; 9 runtime acceptance records after generation;
- climate/VIIRS providers refuse-on-call: 0 calls (delivered histories reach O); climate gaps none;
- GPP: exactly 8 public HTTPS HEAD probes (2026-01..2026-08) at 09:05Z, all 404 -> ledger unpublished, no download;
- ACLED coverage end 2026-08; warnings: GPP_mean coverage 2025-12 < O, bbg_soybean_oil coverage 2026-07 < O (R65);
- batch `ipcch-2026-10-local-real-integration-1-16f7c8ab4018` (manifest sha256 e1aa46b1...), mode/designation real.
Predictions (`save_predictions.py`: read-only reopen of the local store - fake store generations are in-memory, so
every existing object reports generation 1, exact for the create-only batch objects; reads sha-verified; run1 of this
step failed on that and is logged): `run2-predictions-receipt.json` ok = true; per horizon 6,226 rows, unique exact
roster, finite q2..q5, feature period 2026-08, targets 2026-10 / 2027-04 / 2027-10, mode real, package id
ipcch-validity-h2h8h14-final-20261030, thresholds 0.2, cummax:
| H | file sha256 | phase 1/2/3/4/5 | raw scores outside [0,1] |
|---|---|---|---|
| 2 | 42c01672ed52ebd0... | 201 / 2372 / 3537 / 111 / 5 | 4777 |
| 8 | c694155b0d4d3ec0... | 92 / 2356 / 3704 / 69 / 5 | 3869 |
| 14 | 41772efafc42f88f... | 115 / 1833 / 4130 / 147 / 1 | 3937 |
(Raw scores are unclipped by contract R61; counted, not clipped.) Full hashes: `run2-artifact-hashes.txt`; artifacts
(store, batch, predictions) kept under `<R>/scratch/h2h8h14-final/cp3-real-integration/run2/`.
