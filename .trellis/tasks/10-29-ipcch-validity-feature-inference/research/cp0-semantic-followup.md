# CP0 semantic follow-up: S1 (ACLED override precedence) and C6 (evidence key multiplicity)

Executor, session 6a490ae1-ee00-43f9-bdfc-c887c9816c09, 2026-10-30. Local read-only only: no cloud, MLflow, training, Audit or product edits. Context manifests unchanged.
R = /home/swl007007/projects/food-crisis-research. W = R/staging/ipcch-update-202610/sources/acled_agg/work. H = R/scratch/ch-validity-20261028/harvest/formal-h{00,06,12}/trial-0.

## S1 — ACLED override precedence

### Evidence
- Code: `R/staging/ipcch-update-202610/tools/build_acled_agg.py` `map_admin1` (:226-294). For each ACLED admin1 the centroid rule is always computed: an intersecting polygon of the same country, where a strict "contains" hit wins and ties go to the lowest poly_id (:255-261); otherwise the nearest polygon (:262-268). Then `o = ovr_map.get(...)` (:269). If an override row exists, its target polygons are used unconditionally (:270-272). Otherwise the centroid result is used (:273-274). The 25 km guard applies only to final `method == "nearest"` rows (:288-289), so overridden admin1s bypass it. Docstring :23-26 states "Order: override table first".
- Decision record (user-accepted, archived research task `10-20-acled-aggregated-replacement/prd.md`):
  - :93 D19 says a small override table "takes precedence over the centroid rule" (Distrito Nacional, Dakhlet Nouadhibou, Central River, Bunyangabu/Rukiga).
  - :96 D22 adds the Libya East/West/South group overrides.
  - :100 D26 overrides Bishkek because of a centroid longitude typo; the 25 km guard stays. The Supervisor read D19/D26 independently.
- Override table `W/admin1_overrides.csv` (sha256 `916e5999…`) has 13 rows. Comparison against existing output `W/acled_admin1_to_poly.csv` (sha256 `f42c2c2c…`; 1,302 admin1: 1,289 centroid, 6 override_polygon, 7 override_group), which records `centroid_rule_poly_id` and `override_agrees_with_centroid` for every override:

| admin1 | override target | centroid rule | centroid method | outcome if override were fallback-only (centroid first) | events |
|---|---|---|---|---|---|
| DOM Distrito Nacional | DOM-DO0801 | same | centroid | identical | 24 |
| PAK FATA | KP PAK-…89717923239242 | same | centroid | identical | 3,397 |
| GMB Central River | group Janjanbureh + Kuntaur | Kuntaur only | centroid | **diverges**: one LGA instead of the group | 1 |
| MRT Dakhlet Nouadhibou | own polygon …42879511039945 | Inchiri …38857826595310 | centroid | **diverges**: wrong region | 3 |
| UGA Bunyangabu | UG4104 | UG4132 (Rukiga) | centroid | **diverges**: swapped districts | 9 |
| UGA Rukiga | UG4132 | UG4104 (Bunyangabu) | centroid | **diverges**: swapped districts | 1 |
| LBY East | 7-district Cyrenaica group | one district …89898169718474 | centroid | **diverges**: 1 district instead of 7 | 3,215 |
| LBY West | 9-district Tripolitania group | one district …39461050964926 | centroid | **diverges**: 1 instead of 9 | 5,577 |
| LBY South | 6-district Fezzan group | one district …53073192190863 | centroid | **diverges**: 1 instead of 6 | 705 |
| KGZ Bishkek | Chuy Region | Batken (nearest, 5,271 km) | nearest | same target, because the centroid misses and the override applies before nearest | 111 |
| SDN Bahr el Ghazal | 4 SSD states | SDN-SD19 (nearest 83 km) | nearest | same target (centroid misses) | 59 |
| SDN Equatoria | 3 SSD states | SDN-SD07 (nearest 566 km) | nearest | same target (centroid misses) | 111 |
| SDN Upper Nile | 3 SSD states | SDN-SD07 (nearest 27 km) | nearest | same target (centroid misses) | 103 |

Under a centroid-first, fallback-only reading of the R55 list order, 7 admin1s (9,511 events) would map differently: the Libya groups collapse to one district each, the Uganda pair stays swapped, and Mauritania and Central River go to the wrong polygon set. The 2 agreeing rows and the 4 centroid-miss rows map the same under either order.

### Resolution (Supervisor ruling, recorded as a disclosed planning correction)
Port the research semantics exactly: explicit override first (polygon or group, unconditional), otherwise the centroid rule (contains → intersects → lowest poly_id), otherwise the nearest polygon of the same country refused beyond 25 km. The guard applies only to nearest-fallback rows. R55's prose order "point-in-polygon, then override table, then nearest" is read as a list of conventions, not a precedence order; R55's governing clause is "reuses the research `build_acled_agg.py` conventions item by item".

Port tests (CP3), all on the delivered tables:
1. Parity: the ported mapping equals `acled_admin1_to_poly.csv` for all 1,302 admin1 (method and poly_ids).
2. Each of the 7 divergent rows maps to the override target.
3. Bishkek maps through its override despite the 5,271 km centroid distance, and the guard still rejects a non-override nearest match beyond 25 km.
4. An override row with no matching ACLED admin1 fails, as at :290-292.
5. Unlike the research script (CSV written before the failing check), nothing is persisted on any mapping failure (R27).

## C6 — Evidence key multiplicity

### Evidence (10-28 final contexts `h{00,06,12}_supp_2026`, the analogue of the planned H2/H8/H14 contexts)
- Label ledger `H/dataset/labels.csv.gz` has 147,268 rows. Arm rows `H/contexts/arm_rows.csv.gz` have one row per label. Row ledger `H/dataset/row_ledger_hHH.csv.gz` gives each row's origin. Fit membership is `H/contexts/memberships.npz['hHH_supp_2026|backbone|train']` (int32 row indices).
- **No duplicate (area, target) key exists**, for all three horizons, in labels, arm rows, row ledgers and the fit membership: `duplicated(['admin_code','target_ord'])` = 0. "Copies" are a CH report's label carried to later target months within its validity window, each at its own target month. They are not repeated keys.

| H | fit rows | originals | copies | dup (area, target) | copies' q2..q5 equal their source original | rows per (area, family) median/max | distinct origins per family max |
|---|---|---|---|---|---|---|---|
| 0 | 129,150 | 37,759 | 91,391 | 0 | yes (exact decimal strings; 0 sources missing) | 4 / 11 | 11 |
| 6 | 121,894 | 34,004 | 87,890 | 0 | yes | 4 / 11 | 11 |
| 12 | 114,390 | 30,784 | 83,606 | 0 | yes | 4 / 11 | 11 |

The fit_rows column matches the TI §7 train_rows exactly.

- Copies therefore repeat their source report's outcome at different target months, with different origins and features (up to 11 distinct origins per family). The fit treats every member row as a separate training row with halving-24 sample weights (VP:396-407).
- The runtime consumers need only unique `(polygon_id)` for area evidence and unique `(polygon_id, target_month)` for residuals (`cloud_pipeline/cloud/orchestrator/delivery_outputs.py:343-347, 351-390`). Both are satisfied by one evidence row per fit row, with no aggregation.
- The original method (archived `10-09-sept-6m12m-confidence/research/build_ipcch_resubstitution_evidence.py:1-17,107-138`) uses "the exact training rows" of the model, replayed with the saved regressors. Per polygon: training-row count and Phase3+ disagreements `(phase3_worse score >= 0.2) != (phase3+ share >= 0.2)`. Residual = actual cumulative share − replayed raw score, phase2..5 per `(polygon_id, target_month)`. Counts are unweighted.
- Maximum-phase proxy (`delivery_outputs.py:393-416`): per country, only target months where every current-roster polygon of that country has a residual are used ("complete months"); then whole-month bootstrap. Indicative count of complete country-months from the fit rows, with country from label iso2 (17 roster areas have no label iso, so this is approximate and not a final figure):

| H | all fit rows: total / countries ≥2 / countries 0 | originals only: total / countries ≥2 |
|---|---|---|
| 0 | 628 / 26 / 11 | 166 / 24 |
| 6 | 584 / 24 / 18 | 145 / 20 |
| 12 | 536 / 19 / 28 | 131 / 17 |

### Recommendation (no new aggregation policy)
The minimal faithful representation is one evidence record per fit row of the final context, keyed (polygon_id, target_month). That key is unique by construction; the builder asserts uniqueness and fails rather than dedupe or average.
- **Area evidence**: `sample_count` = number of fit rows of the polygon (originals + copies); `error_count` = Phase3+ disagreements over those rows. Unweighted, exactly as the existing method and R31 ("for each training row") state.
- **Residuals**: one row per fit row: actual q2..q5 − replayed raw booster score. Calibration is identity, scores are unclipped, and NaN passes through as in the fit.
- **Replay**: use the research loader/booster on the exact fit matrix rows (membership indices). Verify `train_keys_sha256` / `X_train_sha256` / `y_sha256` against the context `fit_ledger.csv`, so evidence binds to the actual fit and not a rebuild.
- **Audit sidecar** (not consumed by the runtime): per row label_kind, source_family, source_month, origin_ord and sample weight, so the copy structure and weights stay inspectable. Weights are recorded, not applied, because the existing formula is unweighted.
- **Excluded**: scored rows (15,317 per 10-28 context) and family-excluded rows are not fit rows.
- **Disclosure**: because copies repeat a report's outcome, area sample counts scale with report validity spans. This is the actual fit semantics and is documented in package metadata as a known property of training-resubstitution evidence. It is not corrected by reweighting.

Remaining CP1 measurement: the same multiplicity, equality and complete-month counts on the new H2/H8/H14 contexts (cutoffs 2025-11/2025-05/2024-11), with the runtime country lookup instead of label iso2. If any new context shows a duplicate (area, target) key, that is reported to the Supervisor before building evidence.
