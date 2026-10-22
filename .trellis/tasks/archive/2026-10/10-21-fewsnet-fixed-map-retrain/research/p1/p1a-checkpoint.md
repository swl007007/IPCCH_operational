# P1a checkpoint: raw freeze, strict crosswalk, runtime preflight (2026-10-22 ~05:05Z)

Executor: Claude session bfb1fb18 (w1B:p2). Status: **evidence for supervisor review; no label is
accepted for fitting and nothing has been fitted.** Staging root
`S=/home/swl007007/projects/food-crisis-research/staging/fewsnet-fixed-map-retrain-20261022`.

## 1. Runtime and asset identities (verified locally)

| Item | Identity |
| --- | --- |
| Local runtime | `/home/swl007007/.venvs/ipcch-cloud-operator`, Python 3.12.3; `pip freeze` equals `cloud_pipeline/requirements.lock.txt` (sha `2f0a7251…`) on all 60 pins **except certifi**: venv has a CA-remediation wheel `certifi 2026.10.19` (from task 10-21-emsign-ca-asset-impact) instead of `2026.7.22`. Numerical pins (numpy 2.4.2, pandas 3.0.0, scikit-learn 1.8.0, imbalanced-learn 0.14.0, joblib 1.5.3, scipy 1.17.0) match. `ipcch-h5-202609` has the same numerical pins but lacks cloud/raster packages. imblearn import needs the existing shim in `core/training.py:62-116`. |
| Partition map | sha `4723cae5…` (matches config/discovery) |
| Feature contract | file sha `3779c6bc…` |
| Six frozen confidence CSVs | all six sha256 match `confidence-source-inventory.json` |
| Roster / geometry | `bootstrap/assets/fewsnet/roster.csv` `57c3ffae…` (5,718), `geometry.geojson` `4a491eae…` (matches pinned GCS assets) |
| Training panel | `…/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv` sha `510375f5…` (1,120,728 rows, 5,718 areas, features ≤2026-04, labels ≤2026-02) = source of packages `local-202604-57cb3b981198-510375f58cd8`. `bootstrap/assets/fewsnet/history_panel.csv` sha `ddcd30f2…` differs in bytes; remote-sensing columns are value-identical (scout check). |

## 2. HDX-registered CS raw freeze (supervisor hash-verified)

- Freeze `S/hdx/hdx-cs-20261022T043937Z` (04:39:38–04:39:56Z), receipt sha `57ccf3b6…`; 22/22
  roster countries, dataset `*_current_situation_fewsnet_ipc_classification` each; registered
  CSV (FDW `ipcphase/?preference=best&country=XX&scenario=CS&format=csv`) + registered GeoJSON.
  44 files, 176,548,777 bytes. Pinned scientific input.
- Second attempt `S/hdx/hdx-cs-20261022T044133Z` is a false-failure artefact (decoded vs
  Content-Length check); preserved, not used. Script fixed to compare wire bytes.
- Content: 226,100 CS rows, all `Published`, `preference_rating` 90, scales IPC 2.0/3.0/3.1.
  **Every country reaches reporting month 2026-06** while catalog `dataset_date` ends 2024-06…2025-10
  (stale). **No 2025-02 or 2025-06 CS record exists for any country** (true source gap).
  Recent month records: 2024-10 5,893; 2025-10 5,573; 2026-02 5,589; 2026-06 5,871.
- Registered GeoJSON resources are phase-dissolved maps (no fnid; AF empty) → unusable for
  unit-level mapping.

## 3. Geometry evidence (crosswalk only; labels still from the HDX CSV)

FDW `ipcphase.geojson?scenario=CS&preference=best&start_date=…` per month (same official host as
the HDX URLs): `S/fdw-geometry/fdw-cs-geom-20261022T044741Z` (receipt `8cb527b3…`; 2026-06
`219d2bba…`, 2026-02 `d03b4056…`, 2025-10 `303136c6…`, 2024-10 `3a1e2e59…`; 2021-07 empty because
CS months are Feb/Jun/Oct). 2021-06 in `fdw-cs-geom-20261022T045143Z/CS_2021-06.geojson` sha
`cb5dcef8…`, 251,274,547 bytes: download completed (file renamed only after success) but the run
was interrupted by the tool rejection before its receipt; recorded as complete-but-unreceipted.

## 4. Strict crosswalk method

Scripts in this directory: `crosswalk_cs_labels.py` (stage 1), `crosswalk_decide.py` (stage 2),
`test_crosswalk_selfcheck.py` (10 unittest checks, all pass).

1. Record gate (per month): FDW record `id` unique in FDW month, HDX month and whole freeze;
   one-to-one FDW↔HDX join; same country, reporting month, fnid and value. Result: 100% pass in
   every month (2021-06 5,718; 2024-10 5,893; 2025-10 5,573; 2026-02 5,589; 2026-06 5,871); 0
   unjoined. Failing records could never be accepted.
2. All unit types kept (camps/urban/parks reported, not dropped). Strict equivalents by type
   2026-06: fsc_admin_lhz 3,971, fsc_admin 79, national_park 1 (park phase missing → gap).
3. Overlap in EPSG:6933 with same-country units; reciprocal = min(|P∩U|/|P|, |P∩U|/|U|).
4. **Measured tolerance** τ = 0.999999: production polygons equal the 2021-06 units (exactly
   5,718 records); best 1−r is ≤1e-6 for 5,637 areas (median 0, p80 1.6e-9), only 16 areas fall
   in 1e-7…1e-3. 2026 months show a separate mode at 1e-3…1e-2 (re-digitised/redrawn units),
   which is not accepted.
5. Accept only if exactly one unit is equivalent at τ, that unit is equivalent to no other area,
   the record gate passed and the HDX phase is 1–5. 90%/95% rules removed (diagnostic only).
6. Persistent ID: the 2021-06 equivalent fnid of each area (5,637 links). In every month,
   whenever that vintage fnid is reported it is also strictly equivalent (0 exceptions).

Counts of areas whose best reciprocal ≥ threshold:

| Month | .99 | .999 | .9999 | .99999 | .999999 | strict accepted (valid phase) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024-10 | 5289 | 4600 | 4556 | 4547 | 4539 | 4528 |
| 2025-10 | 4971 | 4282 | 4238 | 4229 | 4221 | 4210 |
| 2026-02 | 4927 | 4189 | 4115 | 4078 | 4043 | 4032 |
| 2026-06 | 5065 | 4238 | 4141 | 4090 | 4050 | **4039** (21 countries; 3,115 persistent vintage fnid; 3,685 name-equal) |

Competing units: 7 accepted areas (KE 2746/2755/2756, ZW 4238/4270/4274/4331) have a second
overlapping unit covering ≤7.1e-6 of the area (edge slivers or phase-less national park); in
2026-02/06 three KE slivers carry a different phase. Disclosed; supervisor may exclude them.
Non-strict areas with ≥2 distinct overlapping phases: 571 (2026-06). Missing/invalid phase on an
equivalent unit: 11–13 per month (MW 11, ZW 1) → stay missing.

## 5. Validation against production labels and lineage

- Wherever a strict label meets a source-backed production label they agree **100%**: 2024-10
  4,178/4,178; 2025-10 3,859/3,859; 2026-02 3,663/3,663; zero differences.
- **Proven imputed targets in the current training panel.** Code:
  `Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/assemble_latest_FEWSNET/01_extract_invariables_and_scaffold.ipynb`
  (sha `49ea1acc…`) cell 37 left-merges `FEWS_2025.csv` (sha `4987356a…`) on
  (admin_code, year, month); cell 38 sets `fews_ipc.fillna(1)` and `fews_ipc_crisis.fillna(0)` for
  2025-10 and 2026-02; output `FEWSNET_forecast_unadjusted_bm_2025.csv` (`5c8aefc1…`) is
  concatenated by `02_preprocess_and_combine.ipynb` (`0583c74c…`) into the combined panel.
  Keyed check (`fill_lineage_check.json`): every key lacking a FEWS_2025 value is exactly
  phase 1/crisis 0 (2025-10: 1,259; 2026-02: 1,373) and the training panel equals that
  intermediate for all 5,718 keys in both months. These rows are imputed, not observed labels.
- 2025-10/2026-02 keys with a FEWS_2025 value (name-only merge in `append_2025_2026.ipynb`) but no
  strict geometric match: 600 / 682 → **unverified mapping lineage; old values preserved**, reported
  separately.
- 2024-10 historical labels without strict match: 1,158 → preserved unchanged.

## 6. Candidate credible additions (pending supervisor acceptance)

| Month | Candidate | Count | Note |
| --- | --- | ---: | --- |
| 2026-06 | new month, no production label | **4,039** | 21 countries; ET 0 |
| 2025-10 | strict label replacing a proven imputed fill | 351 | |
| 2026-02 | strict label replacing a proven imputed fill | 369 | |
| 2024-10 | strict label where production had none (truncation) | 350 | SD 348, KE 1, SO 1 |
| 2025-10 / 2026-02 | proven imputed fill without strict label → missing | 908 / 1,004 | removal, not addition |

2026-06 strict labels by country (accepted/areas): AF 509/509, BF 6/65, BI 46/46, CD 330/345,
CM 96/96, **ET 0/1040**, GT 353/353, HT 174/174, KE 640/640, MG 154/154, ML 5/115, MW 3/83,
MZ 233/233, NE 63/182, NG 284/284, SD 347/361, SO 199/199, SS 79/79, TD 56/93, UG 114/318,
YE 145/145, ZW 203/204. Phase counts 1:748, 2:1,693, 3:1,344, 4:254. Gaps are
`no_boundary_equivalent_unit` (ET whole country: `ET2023…` unit set redrawn) or invalid phase.

Horizon effect (no fit run): the 2026-06 labels add h=6 rows (features 2025-12) and h=12 rows
(features 2025-06) with existing features; h=0 rows for 2026-06 need appended 2026-06 features.

Decisions requested: (a) accept the strict rule/tolerance and the four candidate classes;
(b) treat the 2,632 proven imputed rows as missing targets (R4); (c) keep or exclude the 7
sliver areas; (d) keep 600/682 unverified-mapping 2025 labels as preserved old values.

## 7. Other sources — partial scout evidence (scouts stopped at ~11 min)

Stored under `S/sources/`: `remote/analysis/panel_coverage.json`, pinned snapshot copies
(`remote/pinned-full-window-20261008c/`: prepared_manifest, prepare_plan, status succeeded,
`source_coverage.csv`), `p1_wfp_acled/panel_family_inventory.json`, `hdx_wfp_explore.json`.

- Remote (panel): EVI, FLDAS (Rainf/Tair), VIIRS nightlight/sd to 2026-04 for 5,718 areas; GOSIF
  `gpp_mean` v2 to 2024-12. Pinned snapshot `full-window-20261008c`: FEWS EVI/FLDAS/VIIRS observed
  2025-10…2026-08 (min area coverage 5,716/5,131/5,619), GOSIF v2 2024-12 only. 2026-09 provider
  availability, GOSIF v3 2025 FEWS extraction and the overlay plan are **not yet verified**.
- ACLED in panel ends 2025-03/2025-04 by country (AF, GT 2024-12); no new API fetch made.
- WFP in the training panel: latest 2020-07…2026-03 for 11 countries, no value for the other 11.
  The bootstrap `history_panel.csv` has different (refreshed) WFP coverage, e.g. CD/CM/ML/NE/NG
  from 2025-02 — relation to the training panel unverified. HDX 2026-10-19 raw files partially
  inspected only. FEWS WFP/ACLED definitions not yet confirmed.

## 8. Cloud state observed by supervisor (no executor cloud call)

`live-workflow-before.json` (revision 000001-2cf forwarding-only), `live-monthly-prepare-before.json`,
`live-oct-delivery-before.json` (prior image, monthly-runtime identity), `live-current-absence.json`
(`monthly-staging/current.json` absent → expected generation 0 later; accepted
`oct-confidence-20261009b` archive remains separate rollback evidence).

## 9. Pending dependencies and next concrete operations

1. Supervisor acceptance of §6 before any label enters fitting.
2. Feature months 2026-05…2026-09: EVI/FLDAS/VIIRS 2026-09 extraction (prepare/Batch or EE) and
   overlay into the FEWS history; GOSIF v3 2025 FEWS-geometry extraction (local raw v3 files, no
   cloud needed if the existing extractor runs locally); WFP from local HDX raw; ACLED API fetch
   (account lag). Needed for h=0 2026-06 rows and for the inference snapshot.
3. Independent software work can start now: full-data runner/package schema, frozen confidence
   attachment, manifest step selection/Workflow dispatch, candidate download/promotion gates.
4. Cloud ops within the window (≤13:00Z) once data plan is accepted: read-only EE availability
   query for 2026-09; then the extraction/preparation run; later image build/push, workflow
   deploy/IAM, candidate run.
