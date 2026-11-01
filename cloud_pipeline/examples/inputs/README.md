# Manual input CSV examples

These **synthetic format examples** cover all eleven keep/refresh choices. None is a production export or a complete production replacement. The area IDs `900000001`/`900000002`, ACLED country/admin labels and all numerical observations are illustrative. KEN/SOM are real ISO3 codes, but their example stocks are invented.

The action names accepted by the CLI are `keep` and `refresh` (not `fresh`).

## Choose keep or refresh

For **keep**, no CSV is needed. The existing retained version is reused:

```json
{"action":"keep"}
```

Use the complete [all-keep selections](../../selections.example.json) as the starting point. For **refresh**, [refresh-choices.example.json](refresh-choices.example.json) provides one choice object per field, including the file, date interval and ACLED regions. This is a fragment reference, not a standalone submit request.

1. Copy the all-keep selections to your private working directory.
2. Prepare real CSVs using the exact headers in this folder; retain the accepted source definition and units.
3. Replace only the desired entries under `choices` with their refresh objects.
4. Set each `file` to your real input path. Relative paths resolve beside your private selections JSON, not beside this README.
5. Set dates and regions to the complete coverage you are supplying, then follow [preview and submission](../../OPERATIONS.md#3-preview-and-submit-once).

Do not submit the synthetic CSVs to production. An interval refresh replaces all saved rows in that declared interval (ACLED: interval × regions), including old rows absent from your file. `history_snapshot` replaces the entire snapshot. The few rows here demonstrate format only.

## One CSV per field

| Field / CSV | Contents and interpretation |
|---|---|
| [acled.csv](acled.csv) | Regional weekly aggregate export; examples show all three consumed event families. Use mapped production country/admin names and all required regions. |
| [wfp.csv](wfp.csv) | Processed IPCCH WFP_Price: 100 plus year-on-year local staple-price change; not the legacy raw WFP Trend export. |
| [history_snapshot.csv](history_snapshot.csv) | Reported IPC/CH phases and snapshot preparation metadata. |
| [nino34_anom.csv](nino34_anom.csv) | Research-prepared Niño 3.4 anomaly, expanded to the required area-month rows. |
| [bbg_staple_food.csv](bbg_staple_food.csv) | Research-prepared staple-food series. |
| [bbg_oilgas.csv](bbg_oilgas.csv) | Research-prepared oil/gas series. |
| [bbg_soybean_oil.csv](bbg_soybean_oil.csv) | Research-prepared soybean-oil series. |
| [bbg_global_food.csv](bbg_global_food.csv) | Research-prepared global-food series. |
| [food_price_index_WB.csv](food_price_index_WB.csv) | Research-prepared World Bank food-price series. |
| [idp_national.csv](idp_national.csv) | Country/report-month displacement stock, finite and nonnegative. |
| [idp_local.csv](idp_local.csv) | Research-prepared local displacement series on the fixed area roster. |

The sample magnitudes are not definitions of normalization, base years or units. Preserve the accepted research preparation for each family. A common/global series still uses `admin_code,month,value`; repeat the prepared value for the applicable roster, rather than submitting a two-column global series.

## Column meanings

**Area-month series** (WFP and seven research fields other than national IDP):

- `admin_code`: numeric area identifier from the fixed production roster.
- `month`: observation month, `YYYY-MM`; unique per area.
- `value`: prepared numeric value in that family's accepted definition. An empty cell means missing, not zero. WFP and local IDP examples include an empty cell; never insert an arbitrary zero to hide missingness.

**National IDP**:

- `iso3`: uppercase three-letter country code.
- `report_month`: report month, `YYYY-MM`; unique per country.
- `stock`: finite, nonnegative displacement stock.

**Reported-phase history**:

- `area_id`: fixed production area identifier.
- `report_month`: month associated with the reported phase.
- `phase`: reported food-security phase, integer 1–5.
- `availability_month`: month the record became available.
- `preparation_cutoff`: one common preparation month for the whole snapshot. Report and availability months must not exceed it.

Supply all retained history needed by the model, not only the newest reports. Each `area_id,report_month` pair must be unique.

**ACLED aggregate export**:

| Column | Meaning |
|---|---|
| `week` | Saturday starting the represented seven-day week, `YYYY-MM-DD` |
| `region` | ACLED region included in the declared export coverage |
| `country`, `admin1` | Exact names compatible with the installed ACLED mapping |
| `event_type`, `sub_event_type` | Original aggregate-export event classification |
| `events`, `fatalities` | Nonnegative integer counts |
| `population_exposure` | Finite, nonnegative exposure from the aggregate export |
| `disorder_type` | Original export disorder classification |
| `centroid_latitude`, `centroid_longitude` | Export centroid coordinates in degrees |

The example covers 2026-10-17 through 2026-10-30 (Saturday–Friday), with two weekly labels. Its single demo region is not the full production coverage declaration. Use the actual exported region list, covering every region required by the installed mapping. Do not convert raw events by inventing exposure values.

All files are UTF-8 CSV with exact case-sensitive header order and no comment rows. Full operating instructions and source caveats are in [OPERATIONS.md](../../OPERATIONS.md).
