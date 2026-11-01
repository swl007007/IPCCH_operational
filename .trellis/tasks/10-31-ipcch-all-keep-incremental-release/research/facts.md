# Planning evidence

Inspected 2026-10-31 local / 2026-11-01 UTC, source HEAD 013a679.
No cloud calls or product edits were made during this planning turn.

## Terminology

Archived 10-30-ipcch-real-e2e-integration/prd.md:182-190 defines DA1 as the real
production-to-current increment and DA2 as live tasks/assets/PATCH32/VI/field
evidence. Initial inspection found no unique relevant G1/G2 definition; older
tasks reuse those labels for unrelated gates, and G00..G24 are spatial partitions.
The user subsequently confirmed the wording was a memory slip and explicitly
requested the original names DA1/DA2. PRD D1 records this decision; no aliases
or renamed gates are introduced.

## Asset-access evidence

Original diagnostics:
 /home/swl007007/ipcch-operator/food-crisis-test/diagnostics/ee-access-20261101T000446Z/

Selected copies: access-preflight/. Successful execution:
ipcch-v2-runtime-preflight-20261031-rpsqj, completed 2026-11-01T00:09:21Z,
actual monthly-runtime SA, 151/151 metadata reads, G00 size 250, CHIRPS M01 33
bands. The old 487a probe image does not establish a v2 pipeline replay.
A first probe failed before asset reads due to SDK initialization ordering;
the original report preserves that unsuccessful attempt and the corrected success.

## Source anchors

Paths below are relative to cloud_pipeline/.

| Fact | Evidence |
|---|---|
| 11 explicit choices; no implicit keep | cloud/orchestrator/submit_v2.py:93-105,128-143 |
| Local structural preview vs actual freeze/request-last submission | cloud/orchestrator/submit_v2.py:241-271,284-339 |
| Automatic acquisition remains active | cloud/ipcch/generation.py:188-217 |
| ACLED warning vs actual A=O-1 | cloud/ipcch/generation.py:236-243; cloud/ipcch/vendor/ipcch_validity_feature_blocks.py:159-167 |
| Optional-missing sources do not block | cloud/ipcch/generation.py:333-343 |
| GPP availability and retry semantics | cloud/ipcch/gpp.py:96-149; cloud/ipcch/retained.py:130-142 |
| No published climate source at O blocks | cloud/ipcch/climate.py:288-305 |
| Seasonal/nightlight gaps | cloud/ipcch/climate.py:378-393; cloud/ipcch/nightlight.py:47-78 |
| Demand helpers vs export execution | cloud/ipcch/table_producers.py:313-353,465-512 |
| Seven-table September monthly fixture, not live demand | tests/cloud/test_ipcch_table_producers.py:181-187 |
| Actual produced IDs in saved records | cloud/ipcch/climate_tables.py:333-336; cloud/ipcch/climate.py:192-193,299-304 |
| Batch retained and production receipts | cloud/ipcch/generation.py:384-418; cloud/ipcch/run_v2.py:94-101 |
| Offline incremental lineage assertions | tests/cloud/test_ipcch_production_e2e.py:71-91 |
| Publication ordering and CAS | cloud/ipcch/run_v2.py:80-101,185-188; cloud/ipcch/publication.py:152-194 |

## Existing helpers and contracts

Archived 10-30 task research/cp4/cp5/readback_v2.py:39-138 supports pre/current
snapshot and parameterized M/O/features/roster checks. Lines 130-133 merely carry
generation/retained data; they do not assert nonempty production or link produced
IDs. store_inventory.py:20-48 supplies HEAD/version/record inventories.

Foundation: .trellis/spec/backend/monthly-delivery-contracts.md:151-277 and
archived research/cp6/operator-handoff.md (read in full). The handoff's han denial
is historical and superseded by the new runtime-access evidence.

The AGENTS-linked specs/001-cloud-base-input/plan.md is absent at that referenced
path. Current Trellis contracts and the completed v2 handoff supply this plan;
no additional deployment contract is inferred from the stale reference.

## ACLED last-date clarification and read-only live check

The user accepted D2 and offered a newer ACLED export. The guarded check in
acled-date-check/ completed with CHILD-EXIT 0. It stream-hashed and scanned the
imported source CSV and read the live retained HEAD with a generation precondition.
No cloud objects or source histories were changed.

- Raw source sha256: 7bcb051fb3569f09cdec7f840c67d4666e586cbffd77b0d3b4a8feaf95e2fce6;
  291,240 raw rows, 14 regions, week labels 2016-12-31..2026-10-10.
- Latest week spans 2026-10-10..2026-10-16 (Saturday-Friday).
- Live acled_agg_weekly HEAD generation 1793460193863710, version 1, 242,341
  converted rows; declared coverage 2016-12-31..2026-10-16 and source hash match.
- cloud/ipcch/acled.py:231-238 explicitly computes the last complete month no
  later than the supplied through/O. The old 2026-08 report therefore does not
  mean raw history stops in August. The prior preparation check already proved
  complete coverage at O=2026-09 (archived cp3/real-selection log:31-38).
- Actual feature cutoff remains A=O-1. An October-only refresh will extend saved
  history but not the November run's August ACLED feature window. It also cannot
  provide DA2's EE export/schema/units witnesses.

The user subsequently accepted ACLED refresh; PRD D3 supersedes the original
all-keep choice for ACLED only. All other ten choices remain keep.

## Supplied export copied and inspected

Source: /mnt/c/Users/swl00/Downloads/ACLED Data_2026-11-01_event_date_from_2026-10-16_event_date_to_2026-10-31.csv.
Copy: /home/swl007007/ipcch-operator/food-crisis-test/v2-inputs/incremental-20261101/raw/
with the identical filename. Full paths/hash are in acled-input/copy-receipt.json.

- Byte-for-byte copy: 104,921 bytes, sha256
  b480d2654f69a5aa27ff50207e3fdcfdaec3b5a5de0ebcf6767ca0020f17ea90.
- 826 rows, expected 12-column regional-aggregate schema, 17 observed regions.
- Week 2026-10-10: 209 rows, overlapping old history. Filename filter starts Friday
  2026-10-16, so a complete replacement for that earlier week is not established.
- Week 2026-10-17: 617 rows. No 2026-10-24 rows. Structural parse of this candidate
  interval 2026-10-17..23 passed under the memory guard (CHILD-EXIT 0); 470 modeled
  rows retained, 147 rows from countries outside the accepted map dropped normally.
- Guarded log and candidate-validation.json distinguish format/mapping validation
  from independent proof of provider completeness. No derived upload CSV, source
  mutation, cloud operation or monthly submission was performed this turn.
- The user accepted D4: use the available 2026-10-17..23 week. Never extend coverage
  over the absent week solely from the filename's end date.

## Prepared input and preview after D4

research/acled-input/prepared-input.json records the approved derived CSV, 617
rows / 74,134 bytes / sha256 e660c7e8eb126c102145069441805bf55314914cb6297601bd5a150a87e47e8a.
All selected field values match the original copy; 209 overlap rows remain solely
in the original/raw copy. Input preparation preserves both original hashes.
The existing parse_export retained 470 modeled rows and excluded 147 outside-map
country rows. The exact selections file contains ACLED refresh for 2026-10-17..23
and ten keeps; its sha256 is 7ab733d8c0e22bc866ae0ddb8cdfce63b3c5621e749b6ec2316f8fdaf58af4a7.

Existing submit(execute=False, cloud=None) passed under the memory guard; CHILD-EXIT
0. Preview uses the acc3e467 image and provisional M=2026-11. No upload, reference
freeze, cloud call or monthly submission occurred. This is a local structural
check, not live readiness or proof of provider completeness.

Read-only trellis-audit status is preserved in audit-lifecycle-status.json. The
registered repository path is the lowercase WSL spelling, filesystem identity
verified. Controller is running and there are no active runs for this repository.
Its stored executor belongs to a historical session; it is not treated as a live
executor. No audit registration/start/close or job was performed in planning.
