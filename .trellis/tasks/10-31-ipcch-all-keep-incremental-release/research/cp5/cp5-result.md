# CP5 result: D5 all-keep retry ipcch-real-fe7282ef75e747fd SUCCEEDED and was published; readbacks recorded

Executor session 6a490ae1 (claude-opus-5-5[1m]); 2026-11-01 UTC.
- ONE D5 submission, no resubmission or third attempt.
- Product 115798f, image acc3e467; no code, config or deployment change.
- Every local step ran under the archived guard (child exit 0 unless stated). Hashes are in `SHA256SUMS.final`.

## Terminal status (`cp5-final-status.json`, 537b04df)

- **Outcome:** poll 03:30:37Z: `succeeded`; ipcch `succeeded`, no failed operation; `lock_release_problems: []`.
- **Months:** M 2026-11, O 2026-09; H2 → 2026-11, H8 → 2027-05, H14 → 2027-11.
- **Request:** `requests/ipcch-real-fe7282ef75e747fd/run_manifest.json#1793500174046456` (b0f8b507). Execution `oct-delivery-625sk`. Deadline 06:30:34Z, not reached.

## Actual immutable refs (bucket `gs://food-crisis-test-ipcch-data` unless stated)

| Artifact | Ref | sha256 |
|---|---|---|
| Batch manifest | `ipcch-v2/real/feature_batches/ipcch-2026-11-ipcch-real-fe7282ef75e747fd-a02e27ee805d/manifest.json#1793503525485328` | a2a844e1…2359 |
| Batch feature_provenance | same dir, `feature_provenance.csv#1793503525109414` (373,560 rows) | e92b1361…f66c |
| Delivery manifest | `deliveries/ipcch-real-fe7282ef75e747fd-ipcch/manifest.json#1793503722221391` | 461b292b…4b2e |
| Delivery IPCCH fill audit | `reports/ipcch_feature_fill_audit.csv` (declared in the delivery manifest) | e92b1361… (= sidecar) |
| Release record | `monthly-staging/releases/ipcch-real-fe7282ef75e747fd-ipcch/release.json` | (verified by readback_v2) |
| Current pointer | `monthly-staging/current.json#1793503777656101` (previous = pre gen 1793461128385732) | — |
| Shared pins (verified_references) | envelope #1793457267476070, lock #1793457280557418, country ref #1793457294730935 | 03b93842 / 2f0a7251 / 0823e418 |
| Producer assets (7, completed) | `projects/feisty-flames-511718-d4/assets/<job>__M202611_ipcch-real-fe7282ef75e747fd_165617d8` | EE assets (no sha) |

## Readbacks

| Step | Output (sha256) | Result |
|---|---|---|
| 1 Generic product readback | `post-real.json` 7fd0d102 | PASSED, 27/27: verify_delivery, fewsnet_member_full_equal, inherited_fewsnet_from_pre, previous_is_pre, pointer_moved, record_is_this_run, raw_headers_equal, M/O/527 features/6226 roster, etc. |
| 1b Activation | `activation-compare.json` | Post activation dict == pinned pre-real dict (run 522b…, 2026-10-31T15:37:56Z, contract ipcch-validity-h2h8h14-v2, M 2026-10). **Carried contract activation, not a new activation event** (publication.py build_record sets it only when absent) |
| 2 Post inventory | `inventory-post-real.json` 98fd0aa3 | read |
| 3 Lineage (11 keeps) | `lineage.json` 3d94969d | PASSED, 11/11 (detail below) |
| 4 Climate witness | `witness-climate.json` ff851521 | PASSED for all 13 bases (detail below) |
| 5 Links | `witness-links.json` d8918b43 | PASSED (detail below) |
| 6 DA2 witness | `da2-witness.json` d055d703 | Local operator EE credentials (caller identity NOT established); NOT runtime-SA evidence. See DA2 |
| 7 ACLED cutoff (AC6) | `acled-cutoff.json` 4b35a838 | PASSED for 18 `acled_agg_*` sections (detail below) |

**Step 3 lineage:**
- The eleven keeps are unchanged, including `acled_agg_weekly` v2.
- Receipts equal the 7 jobs, and the receipts join the completed task records.
- Each table base appends O from this run, and batch `retained_inputs` equals the post HEADs.
- Unconsumed assets are explained (`all_assets_consumed=false`, with dispositions).
- Warnings, optional-missing NaN per R65: GPP_mean coverage ends 2025-12 (GPP unpublished 2026-01..09); bbg_soybean_oil coverage ends 2026-07.

**Step 4 climate witness:**
- Roster 6226 (sha-verified `fixed__roster`); every base went v1 → v2.
- Each base keeps its 871,640 old rows byte-identical (0 missing, 0 changed). The new keys are exactly roster × 2026-09 (6,226).
- Blank new values (NaN, not filled):

| Blank count | Bases |
|---|---|
| 2 | cdd, prcp_anom, prcp_z, rainy_days, spi03 |
| 9 | evi_anom |
| 18 | edd, gdd, hot_days_p95, tmax_anom, tmean_anom |
| 33 | sm_z |
| 384 | spei03 |

**Step 5 links:**
- All 43 retained inputs equal their post HEADs, and the 24 required tables are present.
- The batch ID is bound and the delivery manifest sha checks.
- The fill-audit declared sha equals the batch sidecar sha.

**Step 7 ACLED cutoff:**
- For each section: 6,226 rows equal to the bound roster; `month_lag1`; feature_month 2026-09; dependency_end 2026-08.
- `latest_max` is 2026-08. There are 96 blank values: the 6 spill sections × 16.
- Source `acled_agg_weekly` v2 (CSV serializes it as "2.0"), sha d3fb0a17. This equals the post HEAD and the batch retained entry.
- Bindings all true. The saved coverage 2016-12-31..2026-10-16 plus 2026-10-17..23 is context only.
- Claim scope: the features declare an ACLED dependency only through 2026-08. This is provenance and cutoff evidence; no numerical replay was done.

## DA2 (natural observation only; D2-pending cases stay pending)

**Raw produced properties** (operator EE read):
- 6 drought/VI tables have 6227 rows each (6227 distinct admin codes); PATCH32 has 32 rows.
- Per-row omitted keys: none. Explicit nulls are present.
- **Naturally observed wholly omitted field:** PERSIANN `prcp_202609_mean` is absent from all 6227 rows, the only wholly omitted O-month field (`omitted` ≠ explicit null). The PERSIANN chunk has exactly 3 wholly-omitted declared fields: `prcp_202107_mean`, `prcp_202608_mean` and `prcp_202609_mean`. Its `days_present_202609` is all finite.
- **O-month fields with explicit nulls:**
  - FAO56 `et0_202609_mean`: 32 nulls;
  - ERA5LAND `prcp_202609_mean`: 32 nulls;
  - CHIRPS `prcp_202609_mean`: 2 nulls;
  - VI composites: partial.

**PATCH32:**
- The set is exactly the 32 target codes (32 rows, 32 distinct, 0 duplicates).
- For input months 2026-07..09, 31 codes have a null primary and a finite patch, giving 93 natural fill candidates. Code 101275 has both the primary and the patch null, so it is not filled.
- Finite primaries are preserved.
- The saved spei03 at 2026-09 is finite for those 31 codes and NaN for 101275.
- This is a **SOURCE-LEVEL candidate witness plus saved values. It does NOT prove an independent SPEI numerical replay.**

**VI:**
- 3 admins (0, 1, 10) were recomputed with the product's `monthly_vi` and ensemble from raw current and han baseline parts.
- All equal the saved `evi_anom` within 1e-9 (max abs diff 9.0e-17).
- No extra scaling. This is a small sample, not a full-table proof.

**Still pending under D2 (not naturally encountered):** per-row omitted keys within otherwise-present fields, and any other field shapes not seen in this run.

## Artifacts kept locally (do not force-add large caches to Git)

| File | Size | Nature |
|---|---|---|
| `batch-feature_provenance.csv` | 77,799,786 B | Verified cache of the immutable sidecar `…/feature_provenance.csv#1793503525109414` (e92b1361). Re-fetchable; recommend NOT committing |
| `batch-manifest.json` | 99,443 B | Verified cache of the batch manifest #1793503525485328 (a2a844e1) |
| `da2-witness.json` | 375,462 B | Evidence output |

Everything else in cp5 is under 1 MB. cp4 totals 612 KB.

## Disclosures

- **acled_cutoff first run:** it failed only on the `source_version` string comparison ("2.0" vs 2). It is kept as `acled-cutoff.INTERMEDIATE-string-version-compare.*`.
  - The GitNexus impact request was made before the edit; the target was not indexed, risk UNKNOWN (`gitnexus-fallback.md`).
  - The fix is a numeric comparison with the raw values reported; the test passes. The rerun reused the verified local bytes.
- **acled_cutoff test:** the first try used the operator venv, which lacks pytest; that log is INTERMEDIATE.
- **Sampler and poll:** both ended normally on terminal. Progress samples are in `cp4/run/progress-5..11.json`.
- **Frozen sets:** cp0, cp1, cp2 and cp3 SHA256SUMS verify. In cp4 `SHA256SUMS.preflight-frozen`, every entry verifies except `cloud-operations.jsonl`, which is append-only.
  - Its frozen sha 583d6386 equals the exact first 10 lines (14,327 B) of the current file.
  - The 9 later records are: 5 pre-submit rechecks; the ONE submission, the only `scope=mutation` record; and 3 monitoring reads.
