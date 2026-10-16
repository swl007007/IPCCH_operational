# Transfer-volume checkpoint, 2026-10-16

Read-only scout counted regular-file metadata in all27roots from `ledger/fews_run_catalog.json`; no large-file reads, hydration, cloud calls or transfer. Scan10:23:13–10:25:22UTC,128.52seconds. All roots complete; no parent/child overlap, traversal errors, symlinks or other file types. These are logical sizes, not fresh-byte integrity or placeholder-readability evidence.

Root: `/mnt/c/Users/swl00/geoxgb_runs/`.

| Run | Files | Bytes |
|---|---:|---:|
| confirm-onset-v1 | 65 | 62541229 |
| d34-hard-replay-evidence | 111 | 2307851 |
| d37-fitglobal-replay-evidence | 72 | 1267564 |
| d38-fitglobal-replay-evidence | 74 | 1356235 |
| geoxgb-d26-20261001 | 1915 | 1700755762 |
| geoxgb-d27-tb3-20261001 | 459 | 523748877 |
| geoxgb-d28-rootinc-20261001 | 548 | 629774993 |
| geoxgb-d29-confirm-20261001 | 502 | 587376340 |
| geoxgb-d30-recent-search-20261001 | 342 | 433674308 |
| geoxgb-d31-matched-search-20261001 | 1034 | 952987363 |
| geoxgb-d34-e1-brier-20261002 | 2706 | 2240528362 |
| geoxgb-d35-global-increment-20261002 | 109 | 82711100 |
| geoxgb-d37-recency-root-20261002 | 109 | 66903201 |
| geoxgb-d38-persistence-margin-root-20261002 | 109 | 78445076 |
| geoxgb-d42-map-transfer-20261002 | 390 | 343185926 |
| geoxgb-d43-temporal-map-refit-20261002 | 2037 | 1739105719 |
| geoxgb-d46-class-weight-root-20261002 | 130 | 239092192 |
| geoxgb-d47-stump-root-20261002 | 109 | 148861806 |
| geoxgb-d48-known-origin-fit-20261002 | 109 | 123546941 |
| geoxgb-d51-history-calendar-root-20261002 | 110 | 138413792 |
| geoxgb-d52-binary-root-20261002 | 109 | 113706068 |
| geoxgb-v1-20261001 | 3612 | 2634074664 |
| minirun-1 | 32681 | 8592920008 |
| minirun-2 | 32700 | 9147273559 |
| scen-b43ef6a-v1 | 55899 | 45341699278 |
| scen-b43ef6a-v1.failed_stage1 | 670 | 804609121 |
| smoke-2 | 65 | 218888447 |
| **Total** | **136776** | **76949755782** |

All-file FEWS volume exceeds the earlier UBJ-only catalog59,880,198,540bytes by17,069,557,242bytes (28.506%). Scenario root agrees exactly with the completed preservation manifest's file/byte totals. Failed-stage1 all-file volume is804,609,121bytes;406,514,277bytes was weights only.

## Native package snapshot

`/home/swl007007/projects/food-crisis-research/packages/*/package.json`,10:25:46UTC.210manifests;11,300declared member files;8,331,822,807declared bytes. Manifest files add5,224,210bytes, total8,337,047,017bytes. No parse errors, symlinks or detected changes during the0.07second final scan. Packages increased204→206→210while the scout worked: this is a timestamped quantity, not a final frozen transfer inventory.

| Runtime | Packages | Declared member bytes | Manifest bytes |
|---|---:|---:|---:|
| rt-alphaearth-x320 | 16 | 1069039279 | 244512 |
| rt-fews-x300 | 16 | 297543938 | 430876 |
| rt-forecast-x320 | 56 | 2660366754 | 978833 |
| rt-geoxgb-x300 | 28 | 1011714409 | 1541310 |
| rt-ipcchgeo-x320 | 70 | 2360501993 | 1305679 |
| rt-popv1-x300 | 24 | 932656434 | 723000 |

## Quote arithmetic and limits

FEWS all-files76,949,755,782 + existing unique input inventory14,870,642,554 + prior MLflow artifact inventory1,321,950,132 + current packages including manifests8,337,047,017 = **101,479,395,485bytes** before further package/source/environment/snapshot/image/retention additions. This deliberately preserves logical duplication between scopes. No content/hardlink dedup saving is claimed. Input inventory and MLflow totals were not rehashed by this scan; package files were measured from manifest declarations. Count any additional IPCCH original-material obligations separately. Use actual final transfer layout for the quote and fresh bytes for upload/download acceptance.
