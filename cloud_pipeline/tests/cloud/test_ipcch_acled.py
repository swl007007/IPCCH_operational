"""Task 10-29 IPCCH ACLED converter/store semantics (R24-R29, R44, R53, R55, R56) on tiny synthetic tables."""

import numpy as np
import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import acled as ac
from cloud.ipcch.stores import StoreRoot, VersionedTable


def tables():
    return ac.AcledTables(
        mapping=pd.DataFrame({"acled_country": ["Aland", "Aland", "Bland"], "admin1": ["A1", "A2", "B1"],
                              "poly_ids": ["pA1", "pA2", "pB1"]}),
        polygons=pd.DataFrame({"poly_id": ["pA1", "pA2", "pB1"], "iso3": ["AAA", "AAA", "BBB"], "pop_denominator": [1000.0, 2000.0, 500.0]}),
        neighbours=pd.DataFrame({"poly_id": ["pA1", "pA2", "pA2", "pB1"], "neighbour_poly_id": ["pA2", "pA1", "pB1", "pA2"]}),
        coverage=pd.DataFrame({"start_month": ["2010-01", "2026-03"], "in_regions": [True, True], "acled_region": ["R1", "R2"]},
                              index=pd.Index(["AAA", "BBB"], name="key")),
        weights=pd.DataFrame({"admin_code": ["1", "2", "2"], "poly_id": ["pA1", "pA2", "pB1"], "weight": [1.0, 0.5, 0.5]}),
        unit_iso3=pd.DataFrame({"admin_code": ["1", "2"], "iso3": ["AAA", "AAA"]}))


def export(rows):
    base = {"region": "R1", "country": "Aland", "admin1": "A1", "event_type": "Battles", "sub_event_type": "Armed clash",
            "events": "1", "fatalities": "0", "population_exposure": "0", "disorder_type": "Political violence",
            "centroid_latitude": "0", "centroid_longitude": "0"}
    return pd.DataFrame([{**base, **r} for r in rows])[list(ac.EXPORT_COLUMNS)]


@pytest.fixture()
def table(tmp_path):
    return VersionedTable(LocalObjectStore(tmp_path), StoreRoot("real", "gs://b/ipcch-v2/real"), "acled_weekly")


START, END = "2025-07-26", "2026-09-04"        # Saturday .. Friday: every week overlapping 2025-08..2026-08
REG = ["R1", "R2"]


def test_export_validation():
    tb = tables()
    ok = export([{"week": "2026-05-02"}])
    assert len(ac.parse_export(ok, start=START, end=END, regions=REG, tables=tb)[0]) == 1
    cases = {
        "header": ok.drop(columns=["disorder_type"]),
        "saturday": export([{"week": "2026-05-03"}]),
        "interval": export([{"week": "2025-07-19"}]),
        "regions": export([{"week": "2026-05-02", "region": "R9"}]),
        "unmapped": export([{"week": "2026-05-02", "admin1": "A9"}]),
        "blank": export([{"week": "2026-05-02", "admin1": " "}]),
        "duplicate": export([{"week": "2026-05-02"}, {"week": "2026-05-02"}]),
        "negative": export([{"week": "2026-05-02", "events": "-1"}]),
    }
    for name, frame in cases.items():
        with pytest.raises(ac.AcledRefreshError):
            ac.parse_export(frame, start=START, end=END, regions=REG, tables=tb)
    with pytest.raises(ac.AcledRefreshError, match="mapped regions"):
        ac.parse_export(ok, start=START, end=END, regions=["R1"], tables=tb)
    with pytest.raises(ac.AcledRefreshError, match="Saturday start"):
        ac.parse_export(ok, start="2025-07-27", end=END, regions=REG, tables=tb)
    outside = export([{"week": "2026-05-02", "country": "Cland", "admin1": "C1"}])
    rows, rep = ac.parse_export(outside, start=START, end=END, regions=REG, tables=tb)
    assert len(rows) == 0 and rep["countries_outside_table"] == ["Cland"]       # research: dropped and counted
    exp = export([{"week": "2026-05-02", "population_exposure": "1,500"}])
    assert ac.parse_export(exp, start=START, end=END, regions=REG, tables=tb)[0]["exposure"].tolist() == [1500.0]


def test_first_refresh_must_cover_the_lookback(table):
    tb = tables()
    rows, _ = ac.parse_export(export([{"week": "2026-05-02"}]), start="2026-01-03", end=END, regions=REG, tables=tb)
    with pytest.raises(ac.AcledRefreshError, match="first ACLED refresh"):
        ac.refresh(table, rows, start="2026-01-03", end=END, regions=REG, source_ref={}, feature_origin="2026-08", tables=tb)
    assert table.head() == (None, "0")                                            # refused: nothing saved
    ac.refresh(table, rows, start=START, end=END, regions=REG, source_ref={}, feature_origin="2026-08", tables=tb)
    later, _ = ac.parse_export(export([{"week": "2026-08-01"}]), start="2026-08-01", end="2026-08-14", regions=REG, tables=tb)
    ac.refresh(table, later, start="2026-08-01", end="2026-08-14", regions=REG, source_ref={}, feature_origin="2026-10", tables=tb)


def series(table, months, units=("1", "2")):
    weekly, records, _ = ac.saved_weekly(table)
    return ac.monthly_series(weekly, records, tables(), months, list(units)).set_index(["admin_code", "month"])


def test_event_free_covered_weeks_are_zero_and_uncovered_months_nan(table):
    tb = tables()
    rows, _ = ac.parse_export(export([{"week": "2026-05-02", "events": "7"}]), start=START, end=END, regions=REG, tables=tb)
    ac.refresh(table, rows, start=START, end=END, regions=REG, source_ref={}, feature_origin="2026-08", tables=tb)
    s = series(table, ["2026-04", "2026-05", "2026-09"])
    assert s.loc[("1", "2026-04"), "acled_agg_events_battles"] == 0.0              # covered, no event rows -> 0 (R55/FCC7)
    assert s.loc[("1", "2026-05"), "acled_agg_events_battles"] == 7.0
    assert np.isnan(s.loc[("1", "2026-09"), "acled_agg_events_battles"])          # weeks of 2026-09 not declared -> NaN
    weekly, records, _ = ac.saved_weekly(table)
    assert ac.coverage_end(records, tb, "2026-10") == "2026-08"                    # R53 warning input


def test_interval_replacement_without_double_counting(table):
    tb = tables()
    first, _ = ac.parse_export(export([{"week": "2026-05-02", "events": "7"}, {"week": "2026-06-06", "events": "2"},
                                       {"week": "2026-05-02", "region": "R2", "country": "Bland", "admin1": "B1", "events": "3"}]),
                               start=START, end=END, regions=REG, tables=tb)
    ac.refresh(table, first, start=START, end=END, regions=REG, source_ref={}, feature_origin="2026-08", tables=tb)
    second, _ = ac.parse_export(export([{"week": "2026-05-02", "events": "5"}]), start="2026-04-25", end="2026-05-29",
                                regions=REG, tables=tb)
    head = ac.refresh(table, second, start="2026-04-25", end="2026-05-29", regions=REG, source_ref={}, feature_origin="2026-08", tables=tb)
    assert head["record"]["replaced_rows"] == 2                                    # both regions' in-interval rows replaced
    weekly, _, _ = ac.saved_weekly(table)
    assert sorted(zip(weekly["week"], weekly["events"])) == [("2026-05-02", 5), ("2026-06-06", 2)]   # B1 superseded row removed
    s = series(table, ["2026-05", "2026-06"])
    assert s.loc[("1", "2026-05"), "acled_agg_events_battles"] == 5.0               # replaced, not 7 + 5


def test_week_split_coverage_start_share_and_spillover(table):
    tb = tables()
    rows, _ = ac.parse_export(export([
        {"week": "2026-02-28", "events": "7", "admin1": "A2"},                      # Sat 2026-02-28: 1 day Feb, 6 days Mar
        {"week": "2026-05-02", "events": "4", "population_exposure": "5000", "admin1": "A2"},
        {"week": "2026-05-02", "region": "R2", "country": "Bland", "admin1": "B1", "events": "3"}]),
        start=START, end=END, regions=REG, tables=tb)
    ac.refresh(table, rows, start=START, end=END, regions=REG, source_ref={}, feature_origin="2026-08", tables=tb)
    s = series(table, ["2026-02", "2026-03", "2026-05"])
    # unit 2 = 0.5 pA2 + 0.5 pB1; pB1 (BBB) uncovered before 2026-03 -> renormalised over pA2 only
    assert s.loc[("2", "2026-02"), "acled_agg_events_battles"] == pytest.approx(1.0)        # 7 * 1/7, pA2 only
    assert s.loc[("2", "2026-03"), "acled_agg_events_battles"] == pytest.approx(0.5 * 6.0 + 0.5 * 0.0)
    assert s.loc[("2", "2026-05"), "acled_agg_exposure_share_battles"] == pytest.approx(0.5 * 1.0 + 0.5 * 0.0)   # 5000/2000 capped at 1
    # spillover of unit 1 (pA1): units behind neighbour pA2 = A2 only (own A1 excluded)
    assert s.loc[("1", "2026-05"), "acled_agg_spill_events_battles"] == pytest.approx(4.0)
    assert s.loc[("1", "2026-05"), "acled_agg_events_battles"] == 0.0


def test_month_completeness_needs_every_overlapping_week():
    rec = [{"start": "2026-05-02", "end": "2026-05-29", "regions": ["R1"]}]
    assert not ac.month_complete(rec, "R1", "2026-05")                            # week of 2026-04-25 overlaps May 1
    rec.append({"start": "2026-04-25", "end": "2026-05-01", "regions": ["R1"]})
    rec.append({"start": "2026-05-30", "end": "2026-06-05", "regions": ["R1"]})
    assert ac.month_complete(rec, "R1", "2026-05") and not ac.month_complete(rec, "R2", "2026-05")
