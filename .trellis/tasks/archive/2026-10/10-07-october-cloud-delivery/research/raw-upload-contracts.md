# Existing raw-upload conversion contracts

Status: planning evidence, 2026-10-07. Code baseline: `4a42f1f666a4f2d5d2616069fe25ddd81f2662cb`. Read-only inspection and raw CSV summaries; no conversion pipeline, model, or cloud execution. This document describes reuse candidates and current behavior, not an implemented cloud upload interface.

## Local reference exports

Directory: `Outcome/model_delivery/202609_h5/20260923_country_confidence_v3/sources/`.

| File | SHA256 | Observed coverage |
|---|---|---|
| `ACLED Data_2026-07-22.csv` | `059e67538f52dce4a2b74e852074855910b336e8896d3c270d03da0c242cb105` | 56,725 rows; actual event dates 2025-05-01 through 2025-07-22, despite the filename. |
| `wfp_data_7.22.26.csv` | `371939492d5f380408c3fcb8f5145f7714f07ee04d0539fed7cc2f2dab9ee046` | 22,942 Aggregated rows dated 2025-01-15 through 2026-07-15. The 5,489 Forecast rows extend through December 2026 and do not establish observed coverage. |

These files match their copies in the September refresh/v2 directories. The v3 `reports/source_manifest.json:2-18` records upstream repository `IFPRI/MTI-GOOGLE-FOOD-CRISIS-MODEL`, commit `92b4fb20fc4f4b0a3fa69c89b2382ffd4b2b1ab6`, and retrieval time `2026-09-09T20:13:14.137339+00:00`, but no uploader. Sediqa attribution is supplied by the user; it is not independently established by this manifest. Existing download instructions are in `docs/08_sediqa_raw_data_download_notes.md`.

## Reuse path

1. Preserve operator-uploaded raw CSV and bind its version/hash.
2. Adapt the existing September conversion functions in `tools/refresh_h5_inputs.py` to explicit source references and origin/cutoff. Preserve their scientific semantics.
3. Independently retain or replace each selected source family in the baseline panels. The existing `replace_sources` currently accepts both sources together; independent choices need adaptation rather than blindly invoking `refresh`.
4. Feed updated history into the system-specific preprocessing and monthly assembly paths. FEWS still requires its own normalization/temporal-feature construction; IPCCH local and cloud assembly implementations need parity verification.

Relevant assembly evidence: `Final_harmonise/00_build_monthly_ipcch_base_input.py:398-503`, `cloud/orchestrator/assembly.py:33-115`, and `fewsnet_partitioned_rf_pipeline/core/preprocessing.py:311-347,530-564`. These are reusable parts, not proof of an existing unified raw-to-cloud pipeline.

The h5 entry currently hard-codes `sources/wfp_data_7.22.26.csv`, `sources/ACLED Data_2026-07-22.csv`, baseline panel paths, and April 2026 cutoff (`tools/refresh_h5_inputs.py:15,177-188`). It writes new panels with exclusive creation and checks baseline hashes (`:185-201`). Compatible supplied exports require no ACLED/WFP API-fetch connector in this upload path.

## WFP September contract

Required columns:

```text
Country, Admin 1, Admin 2, Market Name, Commodity, Price Type,
Price Date, Price, Unit, Currency, Trend, Data Type
```

- Dates parse as `%d/%m/%Y`; retain only `Data Type == "Aggregated"` at or before the cutoff (`tools/refresh_h5_inputs.py:73-79`). Extra export metadata columns are tolerated.
- Country names resolve through existing ISO3 lookup/aliases. `Price` and `Trend` must parse numerically; missing values can exist, but arbitrary text raises an error.
- Duplicate keys across country/admin/market/commodity/price type/unit/currency/month are rejected (`:59-62,80-82`).
- FEWS uses `100 + mean(100 * (Price(t)/Price(t-1) - 1))` within the same series, joining the immediately previous calendar month. Missing months do not become adjacent observations; nonpositive previous prices and infinities do not contribute (`:63-69,84-89`).
- IPCCH uses `100 + mean(Trend)`. Each system also receives the sample standard deviation of its own unshifted indicator (`:84-96`).
- Supported country/month keys replace the WFP feature pair together; uncovered historical keys retain prior values (`:88-89,134-142`).

Do not substitute `WFP_indicator/00_add_wfp_price_features.py` unchanged: its legacy aggregation lacks the Aggregated-only filter, cutoff, and +100 shift (`:81-113`). Its minimal documented schema is therefore insufficient for September-compatible FEWS input. The current example includes Forecast rows with nonmissing Trend, so this difference is material.

## ACLED September contract

Required columns:

```text
event_date, event_type, country, admin1, admin2, admin3,
location, latitude, longitude, fatalities
```

- Dates parse as `%Y-%m-%d`; year/month are reconstructed from `event_date`, then cutoff applies (`tools/refresh_h5_inputs.py:100-109`). The latest full export also includes `year` and other metadata.
- Existing metrics cover Battles, Explosions/Remote violence, and Violence against civilians. Missing a required event-family column after pivot raises an error (`:110-116`).
- Existing aggregation drops missing location keys, builds admin3 counts/fatalities and mean coordinates, and adds admin2 (`_w5`) and admin1 (`_w10`) totals (`:107-123`). These suffixes are not temporal windows or spatial buffers.
- For source-covered months, replacement clears the conflict family and uses the globally nearest same-month admin3 mean point within 500 km; unmatched rows stay missing. Months absent from the source retain history (`:144-164`). Non-source columns remain exactly unchanged (`:169-174`).

The native `ACLED/00_add_acled_features.py` additionally requires the raw `year` column, uses broader date parsing, and does not implement the h5 cutoff/history-preservation behavior (`:36-57,386-457,508-510`). It is not an interchangeable cloud entry.

## Items to make explicit in the specification

- The old download notes request Political violence and three event types (`docs/08_sediqa_raw_data_download_notes.md:19-28`), whereas the latest example includes Strategic developments. The September converter does not explicitly filter those rows before location aggregation; they may affect coordinates. Do not silently introduce filtering while claiming numerical parity. Preserve the inspected September behavior for the baseline comparison and surface any proposed scientific change separately.
- Documentation requests ALPS-compatible commodities (`docs/08_sediqa_raw_data_download_notes.md:53-74`), but the converter does not enforce a commodity whitelist. Define upload validation against the accepted data contract without inventing a new commodity list from old examples.
- WFP source-wide maximum dates include Forecast; use observed-only coverage in reports. ACLED coverage must use event dates, never filename years.
- Current h5 refresh produces historical panels, not a complete October input by itself. Causal filling, calendar derivatives, accepted model preprocessing, and system-specific assembly remain downstream steps.
- Exact uploaded object references, origin/cutoff, and keep/refresh decisions must be manifest inputs. Reject incompatible raw before publication; preserve the upload and its validation report.
