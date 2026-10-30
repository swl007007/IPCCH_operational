"""Task 10-30 CP1: sparse PATCH32 alignment on all four SPI/SPEI routes, and the produced-table contract (one asset per
chunk, declared source-calendar completeness: complete-but-masked vs unavailable, contradictory metadata fails)."""

import numpy as np
import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import climate as cl
from cloud.ipcch import climate_tables as ct
from cloud.ipcch import spi_spei
from cloud.ipcch import spi_spei_seasonal as sss
from cloud.ipcch.stores import StoreRoot, VersionedTable
from tests.cloud.test_ipcch_climate_tables import Tables, drought_tables, vi_tables

ADMINS = ["1", "2", "3"]
REFS = ct.TableRefs()
NEW = "projects/feisty-flames-511718-d4/assets/run-x/"


def keys(tables, part):
    return [k for k in tables if part in k]


def sparse_patch_world(admins=ADMINS, last="2026-08"):
    """Real PATCH32 shape: admin 2 is a small polygon whose primary ET0 is masked everywhere; the patch tables carry only
    a few polygons (2, 1 - where primary is present - and 9, outside the requested roster) in every chunk."""
    tables = drought_tables(admins, last=last)
    months = spi_spei.month_axis("1990-01", last)
    rng = np.random.default_rng(11)
    for k in keys(tables, "ET0_FAO56"):
        f = tables[k].copy()
        cols = [c for c in f.columns if c != "admin_code"]
        f.loc[f["admin_code"] == "2", cols] = np.nan
        tables[k] = f
    for a, b in REFS.year_chunks:
        sel = [d for d in months if a <= d.year <= b]
        tables[REFS.asset(REFS.et0_patch.format(a=a, b=b))] = pd.DataFrame(
            {"admin_code": ["2", "1", "9"], **{f"et0_{d.year}{d.month:02d}_mean": rng.uniform(60, 160, 3) for d in sel}})
    return tables


def matrices(tables, source, months, codes):
    label = ct.SPI_SOURCES[source]
    prcp = ct._wide_month_matrix([tables[k] for k in keys(tables, f"PRCP_{label}")], "prcp", months, codes)
    et0 = ct._wide_month_matrix([tables[k] for k in keys(tables, "ET0_FAO56")], "et0", months, codes)
    patch = pd.concat([tables[k].set_index("admin_code") for k in keys(tables, "PATCH32")], axis=1)
    want = et0.copy()
    if "2" in codes:                                  # only the masked primary cells take the patch
        row = codes.index("2")
        want[row] = [patch.loc["2"].get(f"et0_{d.year}{d.month:02d}_mean", np.nan) for d in months]
    return prcp, et0, want


# --------------------------------------------------------------------------- sparse PATCH32


def test_sparse_patch_monthly_spi_and_spei_fill_only_missing_primary_et0():
    tables = sparse_patch_world()
    p = ct.DroughtProvider(Tables(tables), ADMINS)
    admin2 = []
    for target in ("2026-06", "2026-07", "2026-08"):
        months = spi_spei.month_axis("1990-01", target)
        prcp, et0, patched = matrices(tables, "chirps", months, ADMINS)
        spi = p.fetch("spi03", "chirps", target)
        spei = p.fetch("spei03", "chirps", target)
        assert spi.status == spei.status == "published"
        np.testing.assert_array_equal(spi.values["value"].to_numpy(), spi_spei.compute_spi03_monthly(prcp, months)[:, -1])
        want = spi_spei.compute_spei03_monthly(prcp, patched, months)[:, -1]
        np.testing.assert_array_equal(spei.values["value"].to_numpy(), want)
        primary_only = spi_spei.compute_spei03_monthly(prcp, et0, months)
        assert np.isnan(primary_only[1]).all()                              # admin 2 has no primary ET0 at all
        np.testing.assert_array_equal(want[[0, 2]], primary_only[[0, 2], -1])  # patch row for admin 1 never overwrites
        assert spei.extra["et0_patch_filled"] == len(months)
        admin2.append(want[1])
    assert np.isfinite(admin2).any()                    # admin 2 becomes computable only through the patch


@pytest.mark.parametrize("codes", [ADMINS, ["1", "3"], ["2"]])
def test_sparse_patch_seasonal_spi_and_spei_on_subset_rosters(codes):
    tables = sparse_patch_world()
    windows = pd.DataFrame({"admin_code": codes, "season_year": 2026, "season": "s1",
                            "gs_start_date": "2026-03-01", "gs_end_date_exclusive": "2026-08-01"})
    p = ct.SeasonalDroughtProvider(Tables(tables), ADMINS)
    all_m, idx_m = spi_spei.month_axis("1990-01", "2026-07"), spi_spei.month_axis("2026-03", "2026-07")
    prcp, _, patched = matrices(tables, "era5land", all_m, sorted(codes))
    m = sss.monthly_indices(prcp, patched, all_m, idx_m, "era5land")
    plan = sss.season_plan(windows.assign(gs_calendar_valid=1)[["admin_code", "season_year", "season", "gs_calendar_valid",
                                                                "gs_start_date", "gs_end_date_exclusive"]], idx_m, sorted(codes))
    for base, key in (("spi03", "spi"), ("spei03", "spei")):
        o = p.fetch_season(base, "era5land", 2026, "s1", windows)
        assert o.status == "published" and o.values["admin_code"].tolist() == sorted(codes)
        np.testing.assert_array_equal(o.values["value"].to_numpy(), sss.aggregate(m[key], m[f"{key}_reason"], plan, "v")["v"].to_numpy())


WINDOWS = pd.DataFrame({"admin_code": ADMINS, "season_year": 2026, "season": "s1",
                        "gs_start_date": "2026-03-01", "gs_end_date_exclusive": "2026-09-01"})


def consume(route, tables, base):
    if route == "monthly":
        return ct.DroughtProvider(Tables(tables), ADMINS).fetch(base, "chirps", "2026-08")
    return ct.SeasonalDroughtProvider(Tables(tables), ADMINS).fetch_season(base, "chirps", 2026, "s1", WINDOWS)


@pytest.mark.parametrize("route", ["monthly", "seasonal"])
def test_sparse_patch_keeps_primary_coverage_duplicate_and_numeric_strictness(route):
    tables = sparse_patch_world()
    et0_key = next(k for k in keys(tables, "ET0_FAO56") if "Y2020" in k)
    short = dict(tables); short[et0_key] = tables[et0_key][tables[et0_key]["admin_code"] != "2"]
    with pytest.raises(cl.ClimateProcessingFailure, match="lacks 1 required admins"):     # patch never substitutes a row
        consume(route, short, "spei03")
    patch_key = next(k for k in keys(tables, "PATCH32") if "Y2020" in k)
    dup = dict(tables); dup[patch_key] = pd.concat([tables[patch_key], tables[patch_key].iloc[:1]])
    with pytest.raises(cl.ClimateProcessingFailure, match="duplicate admin_code"):
        consume(route, dup, "spi03")
    bad = dict(tables); bad[patch_key] = tables[patch_key].astype(object); bad[patch_key].iloc[0, 1] = "n/a"
    with pytest.raises(cl.ClimateProcessingFailure, match="non-numeric"):
        consume(route, bad, "spei03")


@pytest.mark.parametrize("route", ["monthly", "seasonal"])
def test_missing_primary_et0_without_a_patch_value_stays_missing(route):
    """Admin 3 has no patch row and admin 2 a NaN patch value in August, while both lack primary August ET0: both stay
    missing (no fill, no failure); admin 1 keeps its primary values."""
    tables = sparse_patch_world()
    et0_key = next(k for k in keys(tables, "ET0_FAO56") if "Y2020" in k)
    patch_key = next(k for k in keys(tables, "PATCH32") if "Y2020" in k)
    tables[et0_key] = tables[et0_key].copy(); tables[et0_key].loc[tables[et0_key]["admin_code"] == "3", "et0_202608_mean"] = np.nan
    tables[patch_key] = tables[patch_key].copy(); tables[patch_key].loc[tables[patch_key]["admin_code"] == "2", "et0_202608_mean"] = np.nan
    months = spi_spei.month_axis("1990-01", "2026-08")
    prcp, _, patched = matrices(tables, "chirps", months, ADMINS)
    assert np.isnan(patched[1:, -1]).all() and np.isfinite(patched[0, -1])
    o = consume(route, tables, "spei03")
    assert o.status == "published" and np.isnan(o.values["value"].iloc[1:]).all()
    if route == "monthly":
        np.testing.assert_array_equal(o.values["value"].to_numpy(), spi_spei.compute_spei03_monthly(prcp, patched, months)[:, -1])
        assert o.extra["et0_patch_filled"] == len(months) - 1          # admin 2's NaN August patch fills nothing


# --------------------------------------------------------------------------- produced-table contract


def periods(a, b, complete_through):
    return {f"{y}{m:02d}": f"{y}-{m:02d}" <= complete_through for y in range(a, b + 1) for m in range(1, 13)}


def produce(tables, name, through, *, extra_months=(), masked=None, values=None, override=None):
    """A run-produced copy of the 2020-2026 chunk ``name``: months through ``through`` complete; ``extra_months`` get an
    all-null column (the producer masks incomplete months); ``values`` overrides complete columns."""
    old = tables[REFS.asset(name)].copy()
    prefix = "et0" if "ET0" in name else "prcp"
    for month in extra_months:
        old[f"{prefix}_{month.replace('-', '')}_mean"] = np.nan
    for col, v in (values or {}).items():
        old[col] = v
    if masked:
        for col, admins in masked.items():
            old.loc[old["admin_code"].isin(admins), col] = np.nan
    asset = NEW + name + "_v1"
    return asset, old, ct.ProducedTable(asset, {**periods(2020, 2026, through), **(override or {})})


def with_produced(tables, *specs):
    tables, produced = dict(tables), {}
    for name, (asset, frame, table) in specs:
        tables[asset] = frame
        produced[name] = table
    return tables, ct.TableRefs(produced=produced)


PRCP = {s: REFS.prcp.format(label=lab, a=2020, b=2026) for s, lab in ct.SPI_SOURCES.items()}
ET0 = REFS.et0.format(a=2020, b=2026)
PATCH = REFS.et0_patch.format(a=2020, b=2026)


def test_produced_chunk_replaces_the_old_chunk_instead_of_joining_it():
    tables = drought_tables(ADMINS, last="2026-08")
    new_aug = {"prcp_202608_mean": [1.0, 2.0, 3.0]}
    tables, refs = with_produced(tables, (PRCP["chirps"], produce(tables, PRCP["chirps"], "2026-08", values=new_aug)))
    backend = Tables(tables)
    o = ct.DroughtProvider(backend, ADMINS, refs=refs).fetch("spi03", "chirps", "2026-08")
    assert REFS.asset(PRCP["chirps"]) not in backend.reads and refs.asset(PRCP["chirps"]) in backend.reads
    months = spi_spei.month_axis("1990-01", "2026-08")
    frames = [tables[refs.asset(REFS.prcp.format(label="CHIRPS", a=a, b=b))] for a, b in REFS.year_chunks]
    prcp = ct._wide_month_matrix(frames, "prcp", months, ADMINS)
    assert prcp[:, -1].tolist() == [1.0, 2.0, 3.0]
    np.testing.assert_array_equal(o.values["value"].to_numpy(), spi_spei.compute_spi03_monthly(prcp, months)[:, -1])


def test_incomplete_month_with_a_null_column_is_unavailable_but_complete_masked_month_is_published():
    base = drought_tables(ADMINS, last="2026-08")
    # static rule (unchanged for history tables): an all-null September column reads as published all-NaN
    static = dict(base); static[REFS.asset(PRCP["chirps"])] = base[REFS.asset(PRCP["chirps"])].assign(prcp_202609_mean=np.nan)
    hazard = ct.DroughtProvider(Tables(static), ADMINS).fetch("spi03", "chirps", "2026-09")
    assert hazard.status == "published" and hazard.values["value"].isna().all()
    tables, refs = with_produced(base, (PRCP["chirps"], produce(base, PRCP["chirps"], "2026-08", extra_months=["2026-09"])))
    o = ct.DroughtProvider(Tables(tables), ADMINS, refs=refs).fetch("spi03", "chirps", "2026-09")
    assert o.status == "unavailable" and "2026-09" in o.detail
    sep = {"prcp_202609_mean": [50.0, 60.0, 70.0]}
    tables, refs = with_produced(base, (PRCP["chirps"], produce(base, PRCP["chirps"], "2026-09", values=sep,
                                                                masked={"prcp_202609_mean": ["2"]})))
    o = ct.DroughtProvider(Tables(tables), ADMINS, refs=refs).fetch("spi03", "chirps", "2026-09")
    assert o.status == "published" and np.isnan(o.values["value"].iloc[1]) and np.isfinite(o.values["value"].iloc[[0, 2]]).all()
    tables, refs = with_produced(base, (PRCP["chirps"], produce(base, PRCP["chirps"], "2026-09", extra_months=["2026-09"])))
    o = ct.DroughtProvider(Tables(tables), ADMINS, refs=refs).fetch("spi03", "chirps", "2026-09")
    assert o.status == "published" and o.values["value"].isna().all()   # complete: no finite-count availability proxy


def test_contradictory_or_absent_completeness_metadata_fails():
    base = drought_tables(ADMINS, last="2026-08")

    def fetch(spec):
        tables, refs = with_produced(base, (PRCP["chirps"], spec))
        return ct.DroughtProvider(Tables(tables), ADMINS, refs=refs).fetch("spi03", "chirps", "2026-08")
    with pytest.raises(cl.ClimateProcessingFailure, match="declared complete but has no (prcp|evi)_"):
        fetch(produce(base, PRCP["chirps"], "2026-09"))
    with pytest.raises(cl.ClimateProcessingFailure, match="declared incomplete but carries values"):
        fetch(produce(base, PRCP["chirps"], "2026-07"))
    with pytest.raises(cl.ClimateProcessingFailure, match="undeclared periods"):
        fetch(produce(base, PRCP["chirps"], "2026-08", values={"prcp_202701_mean": [1.0, 1.0, 1.0]}))
    tables, refs = with_produced(base, (PRCP["chirps"], produce(base, PRCP["chirps"], "2026-08")))
    del tables[refs.asset(PRCP["chirps"])]
    with pytest.raises(cl.ClimateProcessingFailure, match="unreadable S2C3"):
        ct.DroughtProvider(Tables(tables), ADMINS, refs=refs).fetch("spi03", "chirps", "2026-08")


@pytest.mark.parametrize("produced, match", [
    ({"S2E3_VI_BASE_ADMIN_2003_2020_TERRA_CMG_P01_V3": ct.ProducedTable(NEW + "a", {"20260101": True})}, "not a producible"),
    ({"S2C3_DROUGHT_ADMIN_PRCP_CHIRPS_Y2020_2025_V3": ct.ProducedTable(NEW + "a", periods(2020, 2025, "2025-12"))}, "not a producible"),
    ({PRCP["chirps"]: ct.ProducedTable(REFS.asset(PRCP["chirps"]), periods(2020, 2026, "2026-08"))}, "not a new full asset id"),
    ({PRCP["chirps"]: ct.ProducedTable("S2C3_X", periods(2020, 2026, "2026-08"))}, "not a new full asset id"),
    ({PRCP["chirps"]: ct.ProducedTable(NEW + "a", periods(2020, 2026, "2026-08")),
      ET0: ct.ProducedTable(NEW + "a", periods(2020, 2026, "2026-08"))}, "share an asset"),
    ({PRCP["chirps"]: ct.ProducedTable(NEW + "a", {k: v for k, v in periods(2020, 2026, "2026-08").items() if k != "202609"})},
     "exactly the chunk's months"),
    ({PRCP["chirps"]: ct.ProducedTable(NEW + "a", {})}, "no source-calendar completeness"),
    ({PRCP["chirps"]: ct.ProducedTable(NEW + "a", {**periods(2020, 2026, "2026-08"), "202608": 1})}, "malformed"),
    ({"S2E3_VI_CURRENT_ADMIN_TERRA_Y2026_CMG_V3": ct.ProducedTable(NEW + "a", {"20251219": True})}, "not a published 2026"),
    ({"S2E3_VI_CURRENT_ADMIN_TERRA_Y2026_CMG_V3": ct.ProducedTable(NEW + "a", {"20260101": False})}, "not a published 2026"),
])
def test_produced_mapping_validation(produced, match):
    with pytest.raises(cl.ClimateProcessingFailure, match=match):
        ct.TableRefs(produced=produced)


def test_spei_needs_both_produced_et0_families_complete():
    base = sparse_patch_world()
    sep = {"et0_202609_mean": [100.0, np.nan, 90.0]}
    prcp_sep = {"prcp_202609_mean": [50.0, 60.0, 70.0]}
    prcp_spec = (PRCP["chirps"], produce(base, PRCP["chirps"], "2026-09", values=prcp_sep))
    et0_spec = (ET0, produce(base, ET0, "2026-09", values=sep))
    tables, refs = with_produced(base, prcp_spec, et0_spec)            # static PATCH32 has no September
    p = ct.DroughtProvider(Tables(tables), ADMINS, refs=refs)
    assert p.fetch("spi03", "chirps", "2026-09").status == "published"
    assert p.fetch("spei03", "chirps", "2026-09").status == "unavailable"
    patch_incomplete = (PATCH, produce(base, PATCH, "2026-08", extra_months=["2026-09"]))
    tables, refs = with_produced(base, prcp_spec, et0_spec, patch_incomplete)
    assert ct.DroughtProvider(Tables(tables), ADMINS, refs=refs).fetch("spei03", "chirps", "2026-09").status == "unavailable"
    patch_complete = (PATCH, produce(base, PATCH, "2026-09", values={"et0_202609_mean": [95.0, 999.0, 85.0]}))
    tables, refs = with_produced(base, prcp_spec, et0_spec, patch_complete)
    o = ct.DroughtProvider(Tables(tables), ADMINS, refs=refs).fetch("spei03", "chirps", "2026-09")
    months = spi_spei.month_axis("1990-01", "2026-09")
    prcp, _, patched = matrices({k: tables[refs.asset(n)] for n in [*PRCP.values(), ET0, PATCH]
                                 for k in [REFS.asset(n)]} | {k: v for k, v in tables.items() if "Y2020" not in k},
                                "chirps", months, ADMINS)
    assert o.status == "published" and patched[1, -1] == 95.0 and patched[0, -1] == 100.0     # admin 1 keeps primary
    np.testing.assert_array_equal(o.values["value"].to_numpy(), spi_spei.compute_spei03_monthly(prcp, patched, months)[:, -1])
    assert o.extra["et0_patch_filled"] == len(months)   # admin 2 only, every month


def test_produced_schema_must_carry_the_family_field():
    base = drought_tables(ADMINS, last="2026-08")
    et0_as_prcp = produce(base, ET0, "2026-08")          # a PRCP chunk whose fields are ET0's
    tables, refs = with_produced(base, (PRCP["chirps"], et0_as_prcp))
    with pytest.raises(cl.ClimateProcessingFailure, match="is not a prcp field"):
        ct.DroughtProvider(Tables(tables), ADMINS, refs=refs).fetch("spi03", "chirps", "2026-08")
    asset, frame, table = produce(base, PRCP["chirps"], "2026-08")
    frame = frame.assign(et0_202608_mean=1.0)            # one stray foreign field is enough
    tables, refs = with_produced(base, (PRCP["chirps"], (asset, frame, table)))
    with pytest.raises(cl.ClimateProcessingFailure, match="is not a prcp field"):
        ct.DroughtProvider(Tables(tables), ADMINS, refs=refs).fetch("spi03", "chirps", "2026-08")
    vi = vi_tables()
    name = REFS.vi_current.format(label="TERRA", year=2026)
    ndvi_only = vi[REFS.asset(name)].rename(columns=lambda c: c.replace("evi_", "ndvi_"))
    tags = {c.split("_")[1]: True for c in ndvi_only.columns if c.startswith("ndvi_")}
    vi[NEW + "vi"] = ndvi_only
    p = ct.VegetationProvider(Tables(vi), refs=ct.TableRefs(produced={name: ct.ProducedTable(NEW + "vi", tags)}))
    with pytest.raises(cl.ClimateProcessingFailure, match="has no evi_"):
        p.fetch("terra", "2026-03")


def test_every_produced_input_month_of_the_window_must_be_complete():
    base = drought_tables(ADMINS, last="2026-08")
    gap = {"prcp_202608_mean": np.nan, "prcp_202609_mean": [50.0, 60.0, 70.0]}
    spec = produce(base, PRCP["chirps"], "2026-09", values=gap, override={"202608": False})
    tables, refs = with_produced(base, (PRCP["chirps"], spec))
    p = ct.DroughtProvider(Tables(tables), ADMINS, refs=refs)
    assert p.fetch("spi03", "chirps", "2026-09").status == "unavailable"   # its 3-month sum reads the incomplete August
    assert p.fetch("spi03", "chirps", "2026-07").status == "published"
    windows = pd.DataFrame({"admin_code": ADMINS, "season_year": 2026, "season": "s1",
                            "gs_start_date": "2026-06-01", "gs_end_date_exclusive": "2026-10-01"})
    sp = ct.SeasonalDroughtProvider(Tables(tables), ADMINS, refs=refs)
    assert sp.fetch_season("spi03", "chirps", 2026, "s1", windows).status == "unavailable"   # interior month incomplete
    early = windows.assign(gs_start_date="2026-03-01", gs_end_date_exclusive="2026-08-01")
    assert sp.fetch_season("spi03", "chirps", 2026, "s1", early).status == "published"
    lead = windows.assign(gs_start_date="2026-10-01", gs_end_date_exclusive="2026-11-01")
    tables, refs = with_produced(base, (PRCP["chirps"], produce(
        base, PRCP["chirps"], "2026-10", values={**gap, "prcp_202610_mean": [1.0, 2.0, 3.0]}, override={"202608": False})))
    assert ct.SeasonalDroughtProvider(Tables(tables), ADMINS, refs=refs).fetch_season(
        "spi03", "chirps", 2026, "s1", lead).status == "unavailable"   # lookback T-2 = August



def test_produced_gaps_outside_the_consumed_inputs_keep_upstream_missingness():
    """An incomplete old (fit-baseline) month of a produced chunk is masked/NaN as upstream and handled by the fit, not
    a failure; another source's produced gap never affects this source's fetch."""
    base = drought_tables(ADMINS, last="2026-08")
    old_gap = {"prcp_202003_mean": np.nan}
    tables, refs = with_produced(
        base, (PRCP["chirps"], produce(base, PRCP["chirps"], "2026-08", values=old_gap, override={"202003": False})),
        (PRCP["persiann"], produce(base, PRCP["persiann"], "2026-08", values=old_gap, override={"202003": False})))
    p = ct.DroughtProvider(Tables(tables), ADMINS, refs=refs)
    o = p.fetch("spi03", "chirps", "2026-08")
    months = spi_spei.month_axis("1990-01", "2026-08")
    frames = [tables[refs.asset(REFS.prcp.format(label="CHIRPS", a=a, b=b))] for a, b in REFS.year_chunks]
    prcp = ct._wide_month_matrix(frames, "prcp", months, ADMINS)
    assert np.isnan(prcp[:, months.get_loc(pd.Timestamp("2020-03-01"))]).all()
    assert o.status == "published"
    np.testing.assert_array_equal(o.values["value"].to_numpy(), spi_spei.compute_spi03_monthly(prcp, months)[:, -1])
    assert p.fetch("spi03", "chirps", "2020-04").status == "unavailable"     # only a consumed input month gates
    tables, refs = with_produced(
        base, (PRCP["persiann"], produce(base, PRCP["persiann"], "2026-07", values={"prcp_202608_mean": np.nan})))
    assert ct.DroughtProvider(Tables(tables), ADMINS, refs=refs).fetch("spi03", "chirps", "2026-08").status == "published"


def test_seasonal_availability_follows_declared_completeness():
    base = drought_tables(ADMINS, last="2026-08")
    windows = pd.DataFrame({"admin_code": ADMINS, "season_year": 2026, "season": "s1",
                            "gs_start_date": "2026-05-01", "gs_end_date_exclusive": "2026-10-01"})
    tables, refs = with_produced(base, (PRCP["persiann"], produce(base, PRCP["persiann"], "2026-08", extra_months=["2026-09"])))
    p = ct.SeasonalDroughtProvider(Tables(tables), ADMINS, refs=refs)
    assert p.fetch_season("spi03", "persiann", 2026, "s1", windows).status == "unavailable"
    sep = {"prcp_202609_mean": [10.0, 20.0, 30.0]}
    tables, refs = with_produced(base, (PRCP["persiann"], produce(base, PRCP["persiann"], "2026-09", values=sep)))
    assert ct.SeasonalDroughtProvider(Tables(tables), ADMINS, refs=refs).fetch_season(
        "spi03", "persiann", 2026, "s1", windows).status == "published"


def test_produced_vi_table_contract():
    base = vi_tables()
    name = REFS.vi_current.format(label="TERRA", year=2026)
    frame = base[REFS.asset(name)]
    tags = {c.split("_")[1]: True for c in frame.columns if c.startswith("evi_")}
    asset = NEW + name + "_v1"

    def provider(produced, frame=frame):
        tables = dict(base); tables[asset] = frame
        return ct.VegetationProvider(Tables(tables), refs=ct.TableRefs(produced={name: produced}))
    o = provider(ct.ProducedTable(asset, tags)).fetch("terra", "2026-03")
    assert o.status == "published" and o.values["value"].round(12).tolist() == [0.1, 0.1]
    assert provider(ct.ProducedTable(asset, tags)).fetch("terra", "2026-04").status == "unavailable"
    with pytest.raises(cl.ClimateProcessingFailure, match="declared complete but has no (prcp|evi)_"):
        provider(ct.ProducedTable(asset, {**tags, "20260407": True})).fetch("terra", "2026-03")
    with pytest.raises(cl.ClimateProcessingFailure, match="undeclared periods"):
        provider(ct.ProducedTable(asset, {k: v for k, v in tags.items() if k != "20260322"})).fetch("terra", "2026-03")
    tables = dict(base)                                    # produced table absent: failure, not unavailability
    lost = ct.VegetationProvider(Tables(tables), refs=ct.TableRefs(produced={name: ct.ProducedTable(asset, tags)}))
    with pytest.raises(cl.ClimateProcessingFailure, match="produced by this run are not readable"):
        lost.fetch("terra", "2026-03")
    del tables[REFS.asset(name)]                            # static current table absent: unavailable (unchanged)
    assert ct.VegetationProvider(Tables(tables)).fetch("terra", "2026-03").status == "unavailable"


def test_incomplete_then_published_recovery_saves_no_placeholder(tmp_path):
    table = VersionedTable(LocalObjectStore(tmp_path), StoreRoot("real", "gs://b/ipcch-v2/real"),
                           cl.table_name("spi03", cl.MONTHLY))
    table.commit(pd.DataFrame([{"admin_code": a, "month": "2026-08", "value": 0.0, "n_sources": 3, "ens_sd": 0.0,
                                "method_id": "accepted"} for a in ADMINS]), {"action": "initialise"}, expected_generation="0")
    base = drought_tables(ADMINS, last="2026-08")

    def run(through, **kw):
        tables, refs = with_produced(base, *[(PRCP[s], produce(base, PRCP[s], through, **kw)) for s in PRCP])
        p = ct.DroughtProvider(Tables(tables), ADMINS, refs=refs)
        return cl.update_monthly(table, "spi03", origin="2026-09", roster=ADMINS, fetch=p.bound("spi03"))
    with pytest.raises(cl.ClimateSourceMissing):
        run("2026-08", extra_months=["2026-09"])
    assert set(cl.read_monthly(table)[0]["month"]) == {"2026-08"}           # nothing saved for the incomplete month
    rep = run("2026-09", values={"prcp_202609_mean": [40.0, 50.0, 60.0]})
    saved = cl.read_monthly(table)[0].query("month == '2026-09'")
    assert rep["saved"] == ["2026-09"] and np.isfinite(saved["value"]).all() and (saved["n_sources"] == 3).all()
