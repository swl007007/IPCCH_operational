# Supervisor acceptance — 2026-11-01 UTC

The bounded D5 recovery and single additional all-keep run are accepted. DA1 and
current publication passed. DA2 is partial under the explicitly approved D2;
unobserved behaviors remain pending. This is the Supervisor checkpoint required
by execution-protocol.md, not a Trellis Audit or an independent audit workflow.

## Published identity

- Run: `ipcch-real-fe7282ef75e747fd`; execution: `oct-delivery-625sk`.
- Request generation `1793500174046456`, SHA `b0f8b507e63c25be3b660827ab521ce3d7009f14f8d2d0a522f6003c73547d78`.
- UTC freeze `2026-11-01T02:29:33Z`; M=2026-11, O=2026-09.
- Current: `gs://food-crisis-test-ipcch-data/monthly-staging/current.json#1793503777656101`.
- Release: `monthly-staging/releases/ipcch-real-fe7282ef75e747fd-ipcch/release.json#1793503777593004`.
- Batch: `ipcch-2026-11-ipcch-real-fe7282ef75e747fd-a02e27ee805d`, manifest generation
  `1793503525485328`, SHA `a2a844e135c02860f3c940f1531ff57403ea8d30b0b63aa6518bad2f85c92359`.
- H2/H8/H14: targets 2026-11/2027-05/2027-11, 527 features, 6,226 areas each.
- The predecessor FEWS member is literally inherited. The October v2 activation
  dictionary is carried forward; this publication does not reactivate the contract.

## Acceptance matrix

| Criterion | Disposition | Evidence under research/ |
|---|---|---|
| AC1 bound submission | Accepted: original failed request retained; one D5 retry, 11 keeps | cp4/run/frozen-run_manifest.json; cp5/post-real.json |
| AC2 real production | Accepted: nonempty demand, 7 completed/readable table assets, 7 completed raster exports | cp5/lineage.json; cp5/da2-witness.json |
| AC3 consumption | Accepted: 6 assets consumed by saved SPI/SPEI/EVI versions, batch pins and current linked | cp5/lineage.json; cp5/witness-links.json |
| AC4 data contract | Accepted with D2 partial observation; never labelled full DA2 pass | cp5/da2-witness.json; cp5/corrections/da2-tally.json |
| AC5 publication | Accepted: 27 generic checks, targets/roster/order, literal FEWS and predecessor/current | cp5/post-real.json; cp5/activation-compare.json |
| AC6 source actions | Accepted: first refresh exact; retry keeps all 11; 13 exact-roster appends, old rows preserved | cp2/failure-source-checks.json; cp5/lineage.json; cp5/witness-climate.json; cp5/acled-cutoff.json |
| AC7 bounded outcome | Accepted: failure/recovery evidence kept, one retry, unchanged runtime limits, terminal success and reconciliation | cp3/; cp4/; cp5/runtime-final/ |

PERSIANN exported successfully but its September mean field was wholly omitted.
Its unavailable disposition explicitly explains why that seventh asset was not
consumed. CHIRPS/ERA5LAND supplied the drought consumers. Source availability is
distinct from export success and from legitimate spatial NaN.

## Corrected DA2 observations and limits

PATCH32 exactly matches 32 target IDs. Across July–September there are 93
primary-null/patch-finite candidates (31 codes); 101275 remains null in both.
Saved September SPEI is finite for 21 targets and NaN for 11. Ten codes with a
fill candidate still have NaN saved SPEI; the cause was not diagnosed here, and
this source-level witness is not an independent SPEI replay. All 96 sampled
primaries are null, so finite-primary preservation has zero natural samples and
remains pending. The original cp5-result.md sentences claiming otherwise are
superseded; its frozen original bytes are retained.

Wholly omitted declared PERSIANN fields and explicit nulls were observed.
Per-row key omission within an otherwise-present field remains pending, as do
other unseen shapes. VI recomputation matches three sample areas within 1e-9
(maximum difference about 9e-17); this is not full-table or independent-formula
validation. No model-accuracy validation or ACLED numerical replay was performed.

## Verification and closure boundaries

Supervisor verified all 54 CP5 frozen hashes, CP0–CP3 hashes, and the CP4 frozen
ledger prefix (first 10 lines, SHA 583d6386); its later entries are append-only.
All final readback/check CHILD-EXIT markers are 0, with the largest CP5 RSS about
1.1 GiB. Intermediate failures stay labelled, including CSV version `2.0` versus
integer `2`, wrong test venv and runtime-summary cwd. Source/helper and output
spotchecks confirmed the exact joins and the two corrected DA2 report claims.

The runtime execution completed successfully in 59m57s; logs report exit(0).
Final current matches readback; no live lock, hold or active work was observed.
The original image acc3e467, monthly-runtime identity and 8 CPU/32 GiB/14400 s/
zero-retry settings are unchanged. Nine November GPP probes returned 404; GPP
history and soybean-oil optional gaps remain disclosed. Nightlight appended O.
The final logs also contain httplib2 per-request-timeout warnings and pandas
fragmentation PerformanceWarnings. Terminal success does not independently prove
the absence of their effects; no transport/deadline or performance change was made.

Preserve the failed first attempt, initialized EE root and saved histories. No
third run or further recovery is authorized by D5. Commit task evidence and docs,
excluding the re-fetchable 77.8 MB provenance cache (see cp5/CACHE.md), pycache,
ignored fallback and the user's pre-existing AGENTS.md edit. Use native archive
and journal only, as the task-specific user protocol explicitly requires.
