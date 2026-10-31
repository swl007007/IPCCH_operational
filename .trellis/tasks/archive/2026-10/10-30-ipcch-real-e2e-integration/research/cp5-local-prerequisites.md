# CP5 local prerequisites (not live evidence)

Supervisor inspection 2026-10-31 UTC. No cloud calls or execution. The user has
now explicitly selected the previous local integration's action combination:
ACLED=refresh; WFP, history_snapshot and all eight research input families=keep.
The input bytes and declared coverage still require validation before submission;
this choice does not replace the concrete cloud-operation packet gate.

## Recoverable ACLED source

Archived task `10-29-ipcch-validity-feature-inference/research/cp3/real-integration/real_integration.py:21-35`
locates the source under:

`/home/swl007007/projects/food-crisis-research/staging/ipcch-update-202610/sources/acled_agg/raw/aggregated_2026-10-20/`

The source manifest and both payloads still exist. Supervisor streamed SHA256
checks (no CSV load, no mutation) and reproduced the original concatenation hash:

| Role | Filename | Bytes | SHA256 |
|---|---|---:|---|
| f2 | ACLED Data_2026-10-20_event_date_from_2016-12-31_event_date_to_2025-10-17.csv | 33558481 | 659def07e7961757dbd85ce086333924d55a7f933068027c696ceab8d36f4227 |
| f3 | ACLED Data_2026-10-20_event_date_from_2025-10-18_event_date_to_2026-10-16.csv | 5207184 | 5bb1d4b5167d33c7fd569a59c1cdd5d36aba815c18f98ad37767e723a0e08ffa |

Concatenation: f2 unchanged, then f3 after its first newline (BOM/header removed),
with a joining newline only if f2 lacks one. SHA256:
`7bcb051fb3569f09cdec7f840c67d4666e586cbffd77b0d3b4a8feaf95e2fce6`.
This matches the earlier local integration's pinned input; no physical joined file
or upload was created by this inspection. Declared span 2016-12-31..2026-10-16;
derive regions from the union of the two source manifest region maps. The old
human report says eight regions, but its executable construction uses that union
(14 names). Do not copy the report's region count into a new request.

The accepted handoff explicitly seeds no ACLED initial history. If live v2 history
is absent, a valid first refresh is required. The existing local processed
acled_agg_weekly store is not an interchangeable raw refresh input. Reuse the
current converter/admission and full O-12..O coverage check; metadata/hash matches
alone are not a new row-level validation or permission to choose refresh.

## Cloud state remains unknown

The historical operator operation.json records the prior production pointer as
`gs://food-crisis-test-ipcch-data/monthly-staging/current.json`, generation 0,
then a FEWS release on 2026-10-22. That 0 is a pre-publication snapshot; never use
it as today's expected generation. Read live pointer and member before mutation.

Old `gs://ops-delivery-smoke/v2`, `gs://ipcch-store/ipcch-v2/smoke` and
`gs://ops-smoke/inputs/` are local fixture-store names, not verified real buckets.
Deployment's real/smoke roots still need concrete permitted, nonnested locations.
The current project.json snapshot points work_dir to the FEWS retrain directory;
CP3 owns a backed-up correction, not a shared-history overwrite.
