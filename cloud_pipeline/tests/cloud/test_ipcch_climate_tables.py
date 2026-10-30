"""Task 10-29: table-based climate providers - monthly NDVI/EVI 16-day overlap arithmetic (ndvi_evi.js) and monthly
SPI/SPEI from S2C3 admin tables (spi_monthly.py) through a mocked table boundary."""

import numpy as np
import pandas as pd
import pytest

from cloud.ipcch import climate as cl
from cloud.ipcch import climate_tables as ct
from cloud.ipcch import spi_spei


def test_intervals_and_month_tiling():
    s, e, tag = ct.observation_interval("aqua", 2025, 23)
    assert (tag, s.date().isoformat(), e.date().isoformat()) == ("20251227", "2025-12-27", "2026-01-09")   # DOY 9 + 22*16 = 361
    jan = ct.month_plan("aqua", 2026, 1)                    # Aqua DOY 1-8 belong to the previous year's slot 23
    assert [(p["calendar_year"], p["slot"], p["days"]) for p in jan] == [(2025, 23, 8.0), (2026, 1, 16.0), (2026, 2, 7.0)]
    feb = ct.month_plan("terra", 2024, 2)                   # leap February tiles 29 days
    assert sum(p["days"] for p in feb) == 29 and feb[0]["tag"] == "20240117"      # slot 2 starts DOY 17


def test_monthly_vi_full_coverage_rule():
    parts = ct.month_plan("terra", 2026, 3)
    row = {"admin_code": "1"}
    for p in parts:
        row[f"evi_{p['tag']}_mean"] = 0.30
        row[f"evi_base_s{p['slot']:02d}_mean"] = 0.25
    gap = dict(row, admin_code="2")
    gap[f"evi_{parts[1]['tag']}_mean"] = None              # one composite missing -> incomplete -> MISSING
    out = ct.monthly_vi(pd.DataFrame([row, gap]), "terra", "evi", 2026, 3).set_index("admin_code")
    assert out.loc["1", "value"] == pytest.approx(0.05) and out.loc["1", "coverage"] == 1.0
    assert np.isnan(out.loc["2", "value"]) and out.loc["2", "coverage"] < 1


class Tables:
    def __init__(self, tables, missing=()):
        self.t, self.missing = tables, set(missing)
        self.reads = []

    def missing_assets(self, ids):
        return [i for i in ids if i in self.missing or i not in self.t]

    def read_asset_table(self, asset_id):
        self.reads.append(asset_id)
        return self.t[asset_id].copy()


def vi_tables(month_months=("2026-03",), drop_tag=None):
    refs = ct.TableRefs()
    tables = {}
    for k in range(1, 5):
        rows = [{"admin_code": a, **{f"evi_base_s{s:02d}_mean": 0.2 for s in range(1, 24)}} for a in ("1", "2")]
        tables[refs.asset(refs.vi_baseline.format(label="TERRA", part=k))] = pd.DataFrame(rows if k == 1 else rows[:0])
    for cy in (2025, 2026):
        cols = {f"evi_{ct.observation_interval('terra', cy, s)[2]}_mean": 0.3 for s in range(1, 24)}
        if cy == 2026:                     # current year published through the composite starting 2026-03-22 only
            cols = {k: v for k, v in cols.items() if k <= "evi_20260322_mean"}
        if drop_tag:
            cols.pop(drop_tag, None)
        tables[refs.asset(refs.vi_current.format(label="TERRA", year=cy))] = pd.DataFrame([{"admin_code": a, **cols} for a in ("1", "2")])
    return tables


def test_vegetation_provider_outcomes():
    p = ct.VegetationProvider(Tables(vi_tables()))
    o = p.fetch("terra", "2026-03")
    assert o.status == "published" and o.values["value"].round(12).tolist() == [0.1, 0.1]
    assert p.fetch("terra", "2026-04").status == "unavailable"          # April composites not yet in the 2026 table
    tables = vi_tables()
    with pytest.raises(cl.ClimateProcessingFailure, match="S2E3 baseline"):
        ct.VegetationProvider(Tables(tables, missing=[ct.TableRefs().asset("S2E3_VI_BASE_ADMIN_2003_2020_TERRA_CMG_P02_V3")])).fetch("terra", "2026-03")


def drought_tables(admins, last="2026-08", et0_last="2026-08", patch=None):
    refs = ct.TableRefs()
    rng = np.random.default_rng(3)
    months = spi_spei.month_axis("1990-01", last)
    tables = {}
    for a, b in refs.year_chunks:
        sel = [d for d in months if a <= d.year <= b]
        for label in ct.SPI_SOURCES.values():
            tables[refs.asset(refs.prcp.format(label=label, a=a, b=b))] = pd.DataFrame(
                {"admin_code": admins, **{f"prcp_{d.year}{d.month:02d}_mean": rng.gamma(2.0, 40.0, len(admins)) for d in sel}})
        esel = [d for d in sel if d <= pd.Timestamp(f"{et0_last}-01")]
        tables[refs.asset(refs.et0.format(a=a, b=b))] = pd.DataFrame(
            {"admin_code": admins, **{f"et0_{d.year}{d.month:02d}_mean": rng.uniform(60, 160, len(admins)) for d in esel}})
        tables[refs.asset(refs.et0_patch.format(a=a, b=b))] = pd.DataFrame({"admin_code": admins, **(patch or {})}) \
            if a == 2020 else pd.DataFrame({"admin_code": admins})
    return tables


def test_drought_provider_equals_retained_numerics_and_availability():
    admins = ["1", "2", "3"]
    tables = drought_tables(admins)
    p = ct.DroughtProvider(Tables(tables), admins)
    o = p.fetch("spei03", "chirps", "2026-08")
    months = spi_spei.month_axis("1990-01", "2026-08")
    prcp = ct._wide_month_matrix([t for k, t in tables.items() if "PRCP_CHIRPS" in k], "prcp", months, admins)
    et0 = ct._wide_month_matrix([t for k, t in tables.items() if "ET0_FAO56" in k], "et0", months, admins)
    want = spi_spei.compute_spei03_monthly(prcp, et0, months)[:, -1]
    np.testing.assert_array_equal(o.values["value"].to_numpy(), want)
    assert p.fetch("spi03", "chirps", "2026-09").status == "unavailable"
    late_et0 = ct.DroughtProvider(Tables(drought_tables(admins, et0_last="2026-07")), admins)
    assert late_et0.fetch("spi03", "persiann", "2026-08").status == "published"
    assert late_et0.fetch("spei03", "persiann", "2026-08").status == "unavailable"     # ET0 not yet published
    with pytest.raises(cl.ClimateProcessingFailure, match="unreadable S2C3"):
        ct.DroughtProvider(Tables(tables, missing=[ct.TableRefs().asset("S2C3_ET0_PATCH32_Y2020_2026_V2")]), admins).fetch("spi03", "chirps", "2026-08")


def test_seasonal_vegetation_full_support_and_availability():
    windows = pd.DataFrame({"admin_code": ["1", "2"], "season_year": [2026, 2026], "season": ["s1", "s1"],
                            "gs_start_date": ["2026-01-05", "2026-01-05"], "gs_end_date_exclusive": ["2026-03-01", "2026-03-01"]})
    tables = vi_tables()
    p = ct.SeasonalVegetationProvider(Tables(tables))
    o = p.fetch_season("terra", 2026, "s1", windows)
    assert o.status == "published" and o.values["value"].round(12).tolist() == [0.1, 0.1]
    late = windows.assign(gs_end_date_exclusive="2026-05-01")              # April composites not published yet
    assert p.fetch_season("terra", 2026, "s1", late).status == "unavailable"
    gap = vi_tables(drop_tag="evi_20260202_mean")                          # absent composite inside the season -> unavailable
    assert ct.SeasonalVegetationProvider(Tables(gap)).fetch_season("terra", 2026, "s1", windows).status == "unavailable"
    t = pd.DataFrame([{"admin_code": "1", "evi_20260101_mean": 0.3, "evi_base_s01_mean": 0.2}])
    out = ct.season_vi(t, "terra", "evi", windows.iloc[:1], 2026)          # other composites null -> partial -> MISSING
    assert np.isnan(out["value"].iloc[0]) and out["status"].iloc[0] == "MISSING_DATA"


def test_seasonal_drought_uses_the_seasonal_fit():
    from cloud.ipcch import spi_spei_seasonal as sss
    admins = ["1", "2", "3"]
    tables = drought_tables(admins)
    windows = pd.DataFrame({"admin_code": admins, "season_year": [2026] * 3, "season": ["s1"] * 3,
                            "gs_start_date": ["2026-03-01", "2026-02-15", "2026-04-01"],
                            "gs_end_date_exclusive": ["2026-07-01", "2026-06-15", "2026-08-01"]})
    p = ct.SeasonalDroughtProvider(Tables(tables), admins)
    o = p.fetch_season("spei03", "chirps", 2026, "s1", windows)
    all_m, idx_m = spi_spei.month_axis("1990-01", "2026-07"), spi_spei.month_axis("2026-02", "2026-07")
    prcp = ct._wide_month_matrix([t for k, t in tables.items() if "PRCP_CHIRPS" in k], "prcp", all_m, admins)
    et0 = ct._wide_month_matrix([t for k, t in tables.items() if "ET0_FAO56" in k], "et0", all_m, admins)
    m = sss.monthly_indices(prcp, et0, all_m, idx_m, "chirps")
    plan = sss.season_plan(windows.assign(gs_calendar_valid=1)[["admin_code", "season_year", "season", "gs_calendar_valid",
                                                                "gs_start_date", "gs_end_date_exclusive"]], idx_m, admins)
    want = sss.aggregate(m["spei"], m["spei_reason"], plan, "v")["v"].to_numpy()
    np.testing.assert_array_equal(o.values["value"].to_numpy(), want)
    mon = spi_spei.compute_spei03_monthly(prcp, et0, all_m)[:, -5:]          # monthly fit over the same months differs
    assert not np.allclose(np.nan_to_num(mon), np.nan_to_num(m["spei"][:, -5:]))
    short = ct.SeasonalDroughtProvider(Tables(drought_tables(admins, last="2026-06")), admins)
    assert short.fetch_season("spi03", "persiann", 2026, "s1", windows).status == "unavailable"


def test_historical_target_keeps_the_full_baseline_and_patch_counts():
    admins = ["1", "2", "3"]
    tables = drought_tables(admins)
    p = ct.DroughtProvider(Tables(tables), admins)
    o = p.fetch("spi03", "chirps", "2016-05")                        # target before the baseline end (2020-12)
    months = spi_spei.month_axis("1990-01", "2020-12")
    prcp = ct._wide_month_matrix([t for k, t in tables.items() if "PRCP_CHIRPS" in k], "prcp", months, admins)
    want = spi_spei.compute_spi03_monthly(prcp, months)[:, months.get_loc(pd.Timestamp("2016-05-01"))]
    np.testing.assert_array_equal(o.values["value"].to_numpy(), want)
    patched = drought_tables(admins, et0_last="2026-07", patch={"et0_202608_mean": [100.0, 110.0, 120.0]})
    q = ct.DroughtProvider(Tables(patched), admins)
    assert q.fetch("spei03", "chirps", "2026-08").status == "published"          # PATCH32 supplies the target ET0
    sp = ct.SeasonalDroughtProvider(Tables(tables), admins)
    w = pd.DataFrame({"admin_code": admins, "season_year": [2016] * 3, "season": ["s1"] * 3,
                      "gs_start_date": ["2016-03-01"] * 3, "gs_end_date_exclusive": ["2016-07-01"] * 3})
    assert sp.fetch_season("spei03", "era5land", 2016, "s1", w).status == "published"


def test_malformed_values_and_absent_admins_fail():
    admins = ["1", "2", "3"]
    tables = drought_tables(admins)
    key = next(k for k in tables if "PRCP_CHIRPS_Y2020" in k)
    bad = dict(tables); bad[key] = tables[key].astype(object); bad[key].loc[0, "prcp_202608_mean"] = "n/a"
    with pytest.raises(cl.ClimateProcessingFailure, match="non-numeric"):
        ct.DroughtProvider(Tables(bad), admins).fetch("spi03", "chirps", "2026-08")
    short = dict(tables); short[key] = tables[key].iloc[1:]
    with pytest.raises(cl.ClimateProcessingFailure, match="lacks 1 required admins"):
        ct.DroughtProvider(Tables(short), admins).fetch("spi03", "chirps", "2026-08")
    blank = dict(tables); blank[key] = tables[key].astype(object); blank[key].loc[0, "prcp_202608_mean"] = ""
    assert ct.DroughtProvider(Tables(blank), admins).fetch("spi03", "chirps", "2026-08").status == "published"  # blank = missing
    with pytest.raises(cl.ClimateProcessingFailure, match="required admins"):
        ct.VegetationProvider(Tables(vi_tables()), admins=["1", "2", "9"]).fetch("terra", "2026-03")



def test_current_table_missing_an_admin_fails_before_the_join():
    """Baseline has admin 2 but the 2026 current table lacks it: never a published NaN (review finding A)."""
    refs = ct.TableRefs()
    tables = vi_tables()
    key = refs.asset(refs.vi_current.format(label="TERRA", year=2026))
    tables[key] = tables[key][tables[key]["admin_code"] != "2"]
    with pytest.raises(cl.ClimateProcessingFailure, match="current TERRA 2026"):
        ct.VegetationProvider(Tables(tables), admins=["1", "2"]).fetch("terra", "2026-03")
    with pytest.raises(cl.ClimateProcessingFailure, match="current TERRA 2026"):
        ct.VegetationProvider(Tables(tables)).fetch("terra", "2026-03")            # no roster: baseline admins required
    windows = pd.DataFrame({"admin_code": ["1", "2"], "season_year": [2026, 2026], "season": ["s1", "s1"],
                            "gs_start_date": ["2026-01-05", "2026-01-05"], "gs_end_date_exclusive": ["2026-03-01", "2026-03-01"]})
    with pytest.raises(cl.ClimateProcessingFailure, match="current TERRA 2026"):
        ct.SeasonalVegetationProvider(Tables(tables)).fetch_season("terra", 2026, "s1", windows)
