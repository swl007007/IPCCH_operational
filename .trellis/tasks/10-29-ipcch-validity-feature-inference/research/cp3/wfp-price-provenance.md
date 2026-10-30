# Research: provenance of the training-panel WFP_Price (IPCCH) vs the operational WFP converter

- **Query**: how the delivered `history/WFP_Price.csv` was built; why it varies within ISO3-month; whether `wfp_aggregates(...)["ipcch"]` + the IPCCH overlay reproduces it (prd R64)
- **Scope**: internal (research repo `/home/swl007007/projects/food-crisis-research` = FCR; operational repo = OPS)
- **Date**: 2026-10-30

## 1. How the training column was built (verified)

`WFP_Price` in the training interim panel was **redefined for the whole column on 2026-10-19** (task `FCR/.trellis/tasks/archive/2026-10/10-19-wfp-hdx-alps-replacement`). It no longer uses the WFP DataViz `Trend` export.
- Notes and decision: `FCR/staging/ipcch-update-202610/sources/wfp_price/NOTES.md:1-8` ("definition break ... models must be retrained"), definition at `:27-60`.
- Builder: `FCR/staging/ipcch-update-202610/tools/build_wfp_hdx.py`. Output: `.../sources/wfp_price/processed/wfp_price_monthly.csv`. Per-row match sidecar: `.../work/wfp_match_2026-10-19.csv.gz`.
- **Source**: HDX "Global - Food Prices" market-level `price` in local currency per kg/L. `usdprice` is not used. Filters: Retail only; priceflag actual/aggregate; countries = panel ISO3 + CIV (`build_wfp_hdx.py:58,167,359`). Staples: maize, sorghum, rice, wheat grain+flour, vegetable oil.
- **Formula** (`build_wfp_hdx.py:9-16` docstring):
  - Rolling-median outlier filter, centred 13 months, with the window clipped to the input window (`:245-247`).
  - Series yoy = `100*(p_t/p_{t-12}-1)`, exact calendar t-12 within (market, commodity, currency) (`:263-265`).
  - Staple = mean over its variants (`:296`).
  - `WFP_Price = 100 + mean over staples` and `WFP_Price_std = SD(ddof=1)`, blank when n_staples<2 (`:297-304`).
- **Spatial unit**: **nearest market** per admin-month among markets that have >=1 staple yoy that month. Distance is haversine from the panel admin lat/lon (R=6371.0088), ties go to the lowest market_id, and the match is accepted only if <100 km; otherwise the value is blank (`match()` `:310-337`, `MAX_KM` `:57`). There is **no country restriction** on the matched market.
- **Temporal rule**: no carry-forward, interpolation or year fill. A value exists only when the matched market has a t-12 pair in that month (NOTES.md:43-46).
- Merge into the panel: overwrite every row and append 2026-05..09 (NOTES.md:335-340; `FCR/.trellis/tasks/archive/2026-10/10-19-ipcch-202610-merge-retrain/research/inputs-merge.md:185`).
- Handoff: `control-plane-h2h8h14-pkg/research_cloud/packages/ipcch_handoff_inputs.py:55,302-306` copies the interim column unchanged (`grid_long` -> roster filter -> `method_id=delivered:interim@<sha12>`).

**Byte-level check (run 2026-10-30)**: delivered `out-r5/history/WFP_Price.csv` was joined to `processed/wfp_price_monthly.csv` on (admin_code, month).
- All 740,256 keys are present. The 619,806 non-null values match with max |diff| 5.7e-14.
- 0 values are non-null on only one side. The HDX file has 51 more non-null values, which belong to off-roster admins.

**Legacy (superseded) definitions, for contrast**:
- OPS legacy script `git show 4c9122d^:WFP_indicator/00_add_wfp_price_features.py:86-113,181`: country x year x month mean/std of DataViz `Trend` over all commodities and markets, joined by `country_code_3`, no +100 (CH scaffold).
- NOTES.md:264 says the old values "were country-level and spread to every admin".
- `build_wfp_hdx.py:531` records the old IPCCH column as "2010-2024 country-level local-currency price level; 2025 on 100 + mean(Trend) per ISO3-month (WFP DataViz ALPS); mixed currencies/units".

## 2. Source of the within-country variation (verified)

It is explained entirely by the **nearest-market match**. It is not explained by admin1 joins, carry-forward or year fill. Joining history to the sidecar and `out-r5/fixed/area_identity.csv` gives:
- Every valued row has `accepted=1`, distance <99.98 km. Every blank row (120,450) has `accepted=0`, meaning the nearest eligible market is >=100 km away.
- Value is a pure function of (market_id, month): **0 of 110,872 market-months carry >1 value**.
- Of the iso3-months with values (9,460; blank-iso3 groups dropped, so this count differs from the caller's 9,934), 8,184 are multi-valued. In 8,410, the number of distinct values equals the number of distinct matched markets.
- **Cross-border matches**: 69,541 of 617,891 valued rows (11%) take a market whose HDX `countryiso3` differs from the admin's ISO3.

| iso3, month | admins | valued / blank | distinct values = markets | range | largest market groups |
|---|---|---|---|---|---|
| SOM 2025-06 | 709 | 702 / 7 | 36 = 36 | 74.4..144.9 | Bakaara 46 admins 133.5; Burco 42 144.1 |
| SOM 2026-03 | 707 | 626 / 81 | 29 = 29 | 75.2..156.3 | Bakaara 69 141.9; Burco 42 103.0 |
| NGA 2025-06 | 173 | 171 / 2 | 43 = 43 | 62.7..187.7 | Magaria (**NER**) 18 69.8; Porto-Novo (**BEN**) 16 93.6 |
| NGA 2026-03 | 161 | 158 / 3 | 38 = 38 | 50.7..105.7 | Magaria (NER) 18 65.8; Porto-Novo (BEN) 16 81.1 |

## 3. Comparison with `wfp_aggregates(...)["ipcch"]` + IPCCH overlay (verified: not the same)

- `OPS/cloud_pipeline/tools/refresh_h5_inputs.py:93-127`: WFP DataViz export (`Trend`, `Data Type`=Aggregated) -> `groupby(["ISO3","period"])` -> `100 + mean(Trend)`; SD of Trend. Granularity is **country-month**.
- `replace_wfp` (`:173-184`) writes that value to every row with the same `source_iso3` (`:69-76`, ISO3, else `country_en`) and period. The IPCCH path reaches it through `delivery_inputs.py:141-147` -> `_source_choices` (`:460-465`) -> `apply_source_choices` (`refresh_h5_inputs.py:241-263`).
- The differences:

  | | Training | Operational |
  |---|---|---|
  | Source | HDX market prices | DataViz `Trend` |
  | Measure | local-currency yoy over 5 staples | DataViz `Trend`, all commodities |
  | Spatial unit | nearest market <100 km, cross-border allowed, blank beyond 100 km | country, every admin filled |

  The semantics of `Trend` are not verified here, so unit equivalence with the HDX yoy is unverified. The structural mismatch holds regardless.
- The OPS retained IPCCH history differs too. `OPS/cloud_pipeline/bootstrap/assets/retained_wfp.csv` (system=ipcch, 2010-01..2026-04, 598,864 non-null) is the **old definition**:
  - **0 of 334,956** overlapping non-null keys equal the delivered history.
  - The yearly median rises from 80 (2010) to 2,166 (2026), the price-level series.
- **What an append matching the history would need** (from the builder above):
  - HDX market price files, plus `wfp_markets_global.csv` and `wfp_commodities_global.csv`.
  - The same staple allowlist and unit parsing.
  - Dedup and the ±6-month centred rolling-median filter, which needs at least t-12..t, plus up to t+6 where available.
  - Exact t-12 yoy per (market, commodity, currency), including the ZWE ZWL->ZWG relabel (`:55`).
  - Staple mean and SD, then the per-admin-month nearest-market match (<100 km) on the panel admin coordinates.

## Caveats / unverified

- **Centred rolling window** (`build_wfp_hdx.py:247`): outlier decisions for months near the last input month were made with a truncated window. A later rebuild with more months could change those already-delivered values (e.g. 2026-04..09). The size of this effect is not measured.
- 2026-09 is partial (1,686 admins; NOTES.md:246-250). The HDX 2026-10 month was partial at build time.
- Whether DataViz `Trend` is a yoy, a month-on-month change or a smoothed index was not checked. I have not computed or compared any `wfp_aggregates` output for a new month, because no current DataViz export was found locally.
