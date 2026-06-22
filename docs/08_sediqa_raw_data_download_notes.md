# Sediqa Raw Data Download Notes

These notes describe the raw exports that are compatible with the current
ACLED and WFP scripts. They are operator instructions for refreshing source
data before running `docs/03_workflow_runbook.md`.

## ACLED

Script that consumes the export:

```bash
python3 ACLED/00_add_acled_features.py
```

Compatible example archived in this repo:

`archive/example_raw_inputs/ACLED/ACLED Data_2026-05-11_ipcch.csv`

Use the ACLED export interface to download event-level CSV data with these
filters:

- Geography: countries in the IPCCH production scope.
- Time period: the months needed for the refresh.
- Disorder type: `Political violence`.
- Event types: `Battles`, `Explosions/Remote violence`, and
  `Violence against civilians`.
- Do not include `Protests` or `Riots`; the current script does not create
  protest-specific features.

The script requires these columns:

`event_date`, `event_type`, `year`, `country`, `admin1`, `admin2`, `admin3`,
`location`, `latitude`, `longitude`, `fatalities`.

The archived example also contains additional ACLED metadata columns. Extra
columns are fine because the script selects only the required columns above.

After download, set `acled_raw_file` in `config/paths.ini` to the refreshed CSV
path and run the ACLED workflow section in `docs/03_workflow_runbook.md`.

## WFP

Script that consumes the export:

```bash
python3 WFP_indicator/00_add_wfp_price_features.py
```

Compatible example archived in this repo:

`archive/example_raw_inputs/WFP/Prices-Export-Thu Mar 27 2025 11_30_42 GMT-0400 (Eastern Daylight Time).csv`

Use WFP Analysis Builder to download prices with these rules:

- Download only ALPS-compatible commodities.
- Do not mix in other commodities. The current script reads `Commodity` but
  drops it before aggregating by country, year, and month.
- Include the countries and months needed for the refresh.
- Keep the export at a country/month-compatible grain; the script aggregates
  `Trend` by country, year, and month.

The current example contains ALPS commodities:

`Maize`, `Rice`, `Wheat`, `Oil (cooking)`.

The script requires these columns:

`Country`, `Admin 1`, `Admin 2`, `Market Name`, `Commodity`, `Price Date`,
`Trend`.

The exported file may include additional fields such as `Price`, `Unit`,
`Currency`, `ALPS Phase`, and confidence intervals. Extra columns are fine.
`Trend` must be present because the current script derives `WFP_Price` and
`WFP_Price_std` from `Trend`, not from the raw `Price` column.

After download, set `wfp_raw_file` in `config/paths.ini` to the refreshed CSV
path and run the WFP workflow section in `docs/03_workflow_runbook.md`.

