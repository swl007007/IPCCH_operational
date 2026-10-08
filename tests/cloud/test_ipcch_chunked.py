"""Bounded-memory IPCCH assembly must equal the whole-panel path exactly (memory-only change)."""
import hashlib

import numpy as np
import pandas as pd
import pytest

from cloud.orchestrator import delivery_inputs as di
from tools.refresh_h5_inputs import CONFLICT_COLUMNS, WFP_COLUMNS

FAMILIES = {
    "evi": {"provider_latest_completed_month": "2026-08", "system_months": {"ipcch": ["2026-03"]}},
    "fldas": {"provider_latest_completed_month": "2026-08"},
    "gosif_mean": {"provider_latest_completed_month": "2024-12"},
    "gosif_sd": {"provider_latest_completed_month": "2024-12"},
    "viirs": {"provider_latest_completed_month": "2026-08"},
}
IPCCH_RS = list(di.MODEL_COLUMN_MAPPING["ipcch"])
FEATURES = ["EVI_mean", "GPP_mean", "CPI", "gini", "WFP_Price", "event_count_battles"]
IDENTITY = ["area_id", "admin_code", "year", "month", "lat", "lon", "ISO3", "country", "country_en"]


def _panel(months_by_area, *, shuffle=False, after_origin=True):
    rows = []
    for index, (area, months) in enumerate(months_by_area.items()):
        for month in months:
            year, mon = int(month[:4]), int(month[5:])
            row = {"area_id": area, "admin_code": area, "year": year, "month": mon, "lat": 9.0 + index,
                   "lon": 8.0 + index, "ISO3": np.nan if area == "1" else "NGA", "country": "Nigeria",
                   # numeric-looking text with a leading zero in some chunks, words in others
                   "country_en": "0042" if area == "007" else "Nigeria",
                   "CPI": float(mon) if (area, month) != ("00", "2026-04") else np.nan,
                   "gini": 30 if area != "1" else (np.nan if month == "2026-02" else 31)}
            row.update({column: float(index + mon) for column in IPCCH_RS})
            row.update({column: 0.0 for column in WFP_COLUMNS + CONFLICT_COLUMNS})
            rows.append(row)
    frame = pd.DataFrame(rows)
    if after_origin:  # rows after O never reach the series
        extra = frame.iloc[[0]].assign(year=2026, month=11)
        frame = pd.concat([frame, extra], ignore_index=True)
    if shuffle:
        frame = frame.sample(frac=1.0, random_state=7).reset_index(drop=True)
    return frame


OCTOBER = {"0": ["2024-12", "2026-01", "2026-03", "2026-04"], "00": ["2026-02", "2026-03", "2026-04"],
           "007": ["2025-11", "2026-04"], "1": ["2026-01", "2026-02", "2026-04"], "2": ["2026-04"]}


def _prepared(month_values, areas):
    rows = [{"admin_code": area, "month": month, "EVI__mean": value, "EVI__std": value / 10}
            for area in areas for month, value in month_values]
    return {"evi": pd.DataFrame(rows)}


def _template(areas):
    return pd.DataFrame({"area_id": areas, "admin_code": areas, "year": 2026, "month": 4, "ISO3": "NGA",
                         "country": "Nigeria", "country_en": "Nigeria",
                         "population_estimate": [100.0 + i for i in range(len(areas))],
                         "population_reference_period": "2026-04",
                         "population_imputation_method": "observed_feature_month"})


def _ref(path):
    return {"uri": "gs://bucket/inputs/ipcch_base_series.csv", "generation": "1",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _whole(panel_path, template, tmp_path, *, origin, prepared, wfp, acled):
    """The current whole-panel path in deliver._ipcch."""
    header = pd.read_csv(panel_path, nrows=0).columns
    wanted = set(IDENTITY) | set(FEATURES) | set(IPCCH_RS) | set(WFP_COLUMNS) | set(CONFLICT_COLUMNS)
    frame = pd.read_csv(panel_path, low_memory=False, dtype={"admin_code": str, "area_id": str},
                        usecols=[c for c in header if c in wanted])
    base, report = di.ipcch_base_series(frame, origin=origin, prepared_families=FAMILIES, prepared_features=prepared,
                                        wfp=wfp, acled=acled)
    path = tmp_path / "whole.csv"
    base.to_csv(path, index=False, lineterminator="\n")
    rows, audit = di.ipcch_origin_rows(base, template, origin=origin, feature_columns=FEATURES, source_ref=_ref(path))
    return path, rows, audit, report


def _chunked(panel_path, template, tmp_path, *, origin, prepared, wfp, acled, groups, chunksize):
    header = pd.read_csv(panel_path, nrows=0).columns
    wanted = set(IDENTITY) | set(FEATURES) | set(IPCCH_RS) | set(WFP_COLUMNS) | set(CONFLICT_COLUMNS)
    path = tmp_path / f"chunked_{groups}_{chunksize}.csv"
    rows, audit, report, info = di.ipcch_assemble_chunked(
        panel_path, template, origin=origin, feature_columns=FEATURES, usecols=[c for c in header if c in wanted],
        prepared_families=FAMILIES, prepared_features=prepared, base_path=path, make_ref=_ref,
        work_dir=tmp_path / f"work_{groups}_{chunksize}", wfp=wfp, acled=acled, groups=groups, chunksize=chunksize)
    return path, rows, audit, report, info


def _wfp():
    return pd.DataFrame({"WFP_Price": [5.0, 6.0], "WFP_Price_std": [0.5, 0.6]},
                        index=pd.MultiIndex.from_tuples([("NGA", "2026-03"), ("NGA", "2026-10")], names=["ISO3", "period"]))


def _acled():
    point = {column: 2.0 for column in CONFLICT_COLUMNS[:-1]}
    return pd.DataFrame([{"period": "2026-04", "lat": 9.0, "lon": 8.0, **point},
                         {"period": "2026-10", "lat": 12.0, "lon": 11.0, **point}])


def _assert_same(tmp_path, panel, template, *, origin, prepared, wfp=None, acled=None, groups=(1, 2, 64),
                 chunksizes=(2, 5, 1000)):
    panel_path = tmp_path / "panel.csv"
    panel.to_csv(panel_path, index=False)
    whole_path, rows, audit, report = _whole(panel_path, template, tmp_path, origin=origin, prepared=prepared,
                                             wfp=wfp, acled=acled)
    infos = []
    for count in groups:
        for chunksize in chunksizes:
            path, c_rows, c_audit, c_report, info = _chunked(panel_path, template, tmp_path, origin=origin,
                                                             prepared=prepared, wfp=wfp, acled=acled,
                                                             groups=count, chunksize=chunksize)
            assert path.read_bytes() == whole_path.read_bytes(), (count, chunksize)
            pd.testing.assert_frame_equal(c_rows, rows, check_exact=True)
            pd.testing.assert_frame_equal(c_audit, audit, check_exact=True)
            assert c_report == report
            infos.append(info)
    return infos


@pytest.mark.parametrize("wfp_refresh", [False, True])
@pytest.mark.parametrize("acled_refresh", [False, True])
def test_chunked_october_assembly_is_byte_identical_for_all_source_choices(tmp_path, wfp_refresh, acled_refresh):
    panel = _panel(OCTOBER, shuffle=True)
    # 2024-06 precedes area 0's panel start -> extra observation; area 9 is prepared-only.
    prepared = _prepared([("2024-06", 3.0), ("2026-03", 4.0), ("2026-08", 5.0)], ["0", "00", "007", "9"])
    template = _template(["2", "007", "0", "1", "00", "9", "5"])  # 5: template-only area, no history
    infos = _assert_same(tmp_path, panel, template, origin="2026-10", prepared=prepared,
                         wfp={"ipcch": _wfp()} if wfp_refresh else None, acled=_acled() if acled_refresh else None)
    assert all(info["sorted_branch"] for info in infos)


def test_no_calendar_addition_keeps_the_original_row_order(tmp_path):
    complete = {area: ["2026-02", "2026-03", "2026-04"] for area in ("0", "00", "007", "1")}
    panel = _panel(complete, shuffle=True, after_origin=False)
    infos = _assert_same(tmp_path, panel, _template(["0", "00", "007", "1"]), origin="2026-04", prepared={})
    assert not any(info["sorted_branch"] for info in infos)


def test_object_column_text_survives_mixed_chunks(tmp_path):
    panel = _panel(OCTOBER)
    panel_path = tmp_path / "panel.csv"
    panel.to_csv(panel_path, index=False)
    path, *_ = _chunked(panel_path, _template(["0", "00", "007", "1", "2"]), tmp_path, origin="2026-10",
                        prepared={}, wfp=None, acled=None, groups=2, chunksize=2)
    base = pd.read_csv(path, dtype=str)
    assert set(base.loc[base["admin_code"].eq("007"), "country_en"].dropna()) == {"0042"}


def test_duplicate_area_months_fail_the_same_way(tmp_path):
    panel = _panel(OCTOBER)
    panel = pd.concat([panel, panel.iloc[[1]]], ignore_index=True)
    panel_path = tmp_path / "panel.csv"
    panel.to_csv(panel_path, index=False)
    template = _template(["0", "00", "007", "1", "2"])
    with pytest.raises(ValueError) as whole:
        _whole(panel_path, template, tmp_path, origin="2026-10", prepared={}, wfp=None, acled=None)
    with pytest.raises(ValueError) as chunked:
        _chunked(panel_path, template, tmp_path, origin="2026-10", prepared={}, wfp=None, acled=None, groups=2,
                 chunksize=3)
    assert str(chunked.value) == str(whole.value)


def test_history_area_missing_from_the_template_roster_still_fails(tmp_path):
    panel = _panel(OCTOBER)
    panel_path = tmp_path / "panel.csv"
    panel.to_csv(panel_path, index=False)
    template = _template(["0", "00", "007", "1"])  # area 2 has history but no roster row
    with pytest.raises(ValueError, match="outside the roster") as whole:
        _whole(panel_path, template, tmp_path, origin="2026-10", prepared={}, wfp=None, acled=None)
    with pytest.raises(ValueError, match="outside the roster") as chunked:
        _chunked(panel_path, template, tmp_path, origin="2026-10", prepared={}, wfp=None, acled=None, groups=2,
                 chunksize=4)
    assert str(chunked.value) == str(whole.value)


def test_mixed_signed_and_unsigned_integers_keep_the_whole_column_inference(tmp_path):
    panel = _panel({"0": ["2026-03", "2026-04"], "00": ["2026-03", "2026-04"]}, after_origin=False)
    panel["CPI"] = pd.Series([-1, -2, 18446744073709551614, 18446744073709551615], dtype=object)
    template = _template(["0", "00"])
    panel_path = tmp_path / "panel.csv"
    panel.to_csv(panel_path, index=False)
    try:
        whole = _whole(panel_path, template, tmp_path, origin="2026-04", prepared={}, wfp=None, acled=None)
    except (ValueError, OverflowError, TypeError) as exc:  # the chunked path must fail identically
        with pytest.raises(type(exc)) as chunked:
            _chunked(panel_path, template, tmp_path, origin="2026-04", prepared={}, wfp=None, acled=None,
                     groups=2, chunksize=2)
        assert str(chunked.value) == str(exc)
        return
    path, rows, audit, report, _ = _chunked(panel_path, template, tmp_path, origin="2026-04", prepared={},
                                            wfp=None, acled=None, groups=2, chunksize=2)
    assert path.read_bytes() == whole[0].read_bytes()
    pd.testing.assert_frame_equal(rows, whole[1], check_exact=True)
    pd.testing.assert_frame_equal(audit, whole[2], check_exact=True)


def test_quoted_newlines_survive_the_ordinal_merge(tmp_path):
    complete = {area: ["2026-02", "2026-03", "2026-04"] for area in ("0", "00", "007", "1")}
    panel = _panel(complete, shuffle=True, after_origin=False)
    panel.loc[panel["admin_code"].eq("00"), "country_en"] = "Nigeria\nNorth"
    infos = _assert_same(tmp_path, panel, _template(["0", "00", "007", "1"]), origin="2026-04", prepared={},
                         groups=(2, 64), chunksizes=(2, 1000))
    assert not any(info["sorted_branch"] for info in infos)
