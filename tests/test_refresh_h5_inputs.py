import pandas as pd
import pytest

from tools import refresh_h5_inputs as refresh


WFP_HEADER = refresh.WFP_REQUIRED_COLUMNS + ["Data Source", "ALPS Phase"]


def _wfp_row(date, price, trend, data_type="Aggregated", market="M1", country="Kenya"):
    return {
        "Country": country, "Admin 1": "A1", "Admin 2": "A2", "Market Name": market,
        "Commodity": "Maize", "Price Type": "Retail", "Price Date": date, "Price": price,
        "Unit": "KG", "Currency": "KES", "Trend": trend, "Data Type": data_type,
        "Data Source": "extra", "ALPS Phase": "extra",
    }


def _write(tmp_path, name, rows, columns=None):
    path = tmp_path / name
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
    return path


def _wfp(tmp_path, rows):
    return _write(tmp_path, "wfp.csv", rows, WFP_HEADER)


def test_wfp_formulas_stay_system_specific_and_forecast_is_excluded(tmp_path):
    path = _wfp(tmp_path, [
        _wfp_row("15/01/2026", 100.0, 2.0),
        _wfp_row("15/02/2026", 110.0, 4.0),
        _wfp_row("15/02/2026", 999.0, 50.0, data_type="Forecast", market="M2"),
        _wfp_row("15/06/2026", 120.0, 6.0, data_type="Forecast"),
    ])

    result, report = refresh.wfp_aggregates(path, cutoff="2026-04")

    fews = result["fewsnet"].loc[("KEN", "2026-02")]
    ipcch = result["ipcch"].loc[("KEN", "2026-02")]
    assert fews["WFP_Price"] == pytest.approx(110.0)  # 100 + 100*(110/100-1)
    assert ipcch["WFP_Price"] == pytest.approx(104.0)  # 100 + Trend; Forecast excluded
    assert ("KEN", "2026-01") not in result["fewsnet"].index  # no previous month
    assert result["ipcch"].loc[("KEN", "2026-01"), "WFP_Price"] == pytest.approx(102.0)
    assert report["forecast_rows_excluded_through_cutoff"] == 1
    assert report["observed_period_max"] == "2026-02"
    assert report["source_period_max"] == "2026-06"


def test_wfp_does_not_bridge_a_missing_previous_calendar_month(tmp_path):
    path = _wfp(tmp_path, [
        _wfp_row("15/01/2026", 100.0, 1.0),
        _wfp_row("15/03/2026", 150.0, 1.0),
    ])

    result, _ = refresh.wfp_aggregates(path, cutoff="2026-04")

    assert result["fewsnet"].empty


def test_wfp_cutoff_is_explicit_and_validated(tmp_path):
    path = _wfp(tmp_path, [
        _wfp_row("15/01/2026", 100.0, 1.0),
        _wfp_row("15/02/2026", 110.0, 3.0),
    ])

    result, report = refresh.wfp_aggregates(path, cutoff="2026-01")

    assert list(result["ipcch"].index) == [("KEN", "2026-01")]
    assert report["cutoff"] == "2026-01" and report["rows_after_cutoff"] == 1
    with pytest.raises(ValueError, match="YYYY-MM"):
        refresh.wfp_aggregates(path, cutoff="2026-13")


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([_wfp_row("15/01/2026", 100.0, 1.0), _wfp_row("15/01/2026", 101.0, 1.0)], "duplicate WFP"),
        ([_wfp_row("2026-01-15", 100.0, 1.0)], "doesn't match format"),
        ([_wfp_row(None, 100.0, 1.0)], "Price Date must not be blank"),
        ([_wfp_row("15/01/2026", 100.0, 1.0, data_type="Modelled")], "Data Type"),
        ([_wfp_row("15/01/2026", "abc", 1.0)], "Unable to parse"),
        ([_wfp_row("15/01/2026", 100.0, 1.0, country="Atlantis")], "(?i)atlantis"),
    ],
)
def test_wfp_rejects_malformed_or_ambiguous_raw(tmp_path, rows, message):
    with pytest.raises((ValueError, LookupError), match=message):
        refresh.wfp_aggregates(_wfp(tmp_path, rows), cutoff="2026-04")


def test_wfp_requires_contract_columns(tmp_path):
    path = _write(tmp_path, "wfp.csv", [{"Country": "Kenya", "Price Date": "15/01/2026"}])

    with pytest.raises(ValueError, match="lacks required columns"):
        refresh.wfp_aggregates(path, cutoff="2026-04")


def _acled_row(date, event_type, lat=1.0, lon=36.0, fatalities=1, year=None, admin3="X"):
    row = {
        "event_date": date, "event_type": event_type, "country": "Kenya", "admin1": "A",
        "admin2": "B", "admin3": admin3, "location": "L", "latitude": lat, "longitude": lon,
        "fatalities": fatalities, "notes": "extra",
    }
    row["year"] = int(date[:4]) if year is None and date else year
    return row


def _acled(tmp_path, rows):
    return _write(tmp_path, "acled.csv", rows)


def _acled_month(date):
    return [_acled_row(date, kind) for kind in refresh.EVENT_TYPES]


def test_acled_cutoff_uses_event_dates(tmp_path):
    path = _acled(tmp_path, _acled_month("2026-03-02") + _acled_month("2026-05-02"))

    aggregates, report = refresh.conflict_aggregates(path, cutoff="2026-04")

    assert report["covered_months"] == ["2026-03"]
    assert report["actual_date_max"] == "2026-05-02"
    assert aggregates["event_count_battles"].tolist() == [1]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda rows: rows[0].update(event_date=None), "event_date must not be blank"),
        (lambda rows: rows[0].update(event_date="02/03/2026"), "doesn't match format"),
        (lambda rows: rows[0].update(year=2025), "year column disagrees"),
        (lambda rows: rows[0].update(fatalities="many"), "Unable to parse"),
    ],
)
def test_acled_rejects_malformed_or_ambiguous_raw(tmp_path, mutate, message):
    rows = _acled_month("2026-03-02")
    mutate(rows)

    with pytest.raises(ValueError, match=message):
        refresh.conflict_aggregates(_acled(tmp_path, rows), cutoff="2026-04")


def test_acled_requires_contract_columns(tmp_path):
    path = _write(tmp_path, "acled.csv", [{"event_date": "2026-03-02", "event_type": "Battles"}])

    with pytest.raises(ValueError, match="lacks required columns"):
        refresh.conflict_aggregates(path, cutoff="2026-04")


def _panel():
    rows = []
    for admin, lat in (("0", 1.0), ("10", 50.0)):
        for month in (2, 3):
            rows.append({"admin_code": admin, "year": 2026, "month": month, "lat": lat,
                         "lon": 36.0, "ISO3": "KEN", "other_feature": float(month)})
    frame = pd.DataFrame(rows)
    frame["admin_code"] = frame["admin_code"].astype("string")
    for col in refresh.WFP_COLUMNS + refresh.CONFLICT_COLUMNS:
        frame[col] = -1.0  # retained history sentinel
    return frame


@pytest.fixture
def sources(tmp_path):
    wfp, _ = refresh.wfp_aggregates(_wfp(tmp_path, [
        _wfp_row("15/02/2026", 100.0, 2.0),
        _wfp_row("15/03/2026", 120.0, 5.0),
    ]), cutoff="2026-04")
    acled, _ = refresh.conflict_aggregates(_acled(tmp_path, _acled_month("2026-03-02")), cutoff="2026-04")
    return wfp, acled


@pytest.mark.parametrize("refresh_wfp", [False, True])
@pytest.mark.parametrize("refresh_acled", [False, True])
def test_four_source_choices_change_only_selected_families(sources, refresh_wfp, refresh_acled):
    wfp, acled = sources
    frame = _panel()
    original = frame.copy(deep=True)

    out, report = refresh.apply_source_choices(
        frame, "ipcch", wfp if refresh_wfp else None, acled if refresh_acled else None
    )

    pd.testing.assert_frame_equal(frame, original)  # input never mutated
    untouched = ["admin_code", "year", "month", "lat", "lon", "ISO3", "other_feature"]
    pd.testing.assert_frame_equal(out[untouched], original[untouched], check_exact=True)
    assert out["admin_code"].tolist() == ["0", "0", "10", "10"]  # string IDs kept
    assert report["wfp_action"] == ("refresh" if refresh_wfp else "keep")
    assert report["acled_action"] == ("refresh" if refresh_acled else "keep")
    feb, mar = out["month"].eq(2), out["month"].eq(3)
    if refresh_wfp:
        assert out.loc[feb, "WFP_Price"].tolist() == [102.0, 102.0]
        assert out.loc[mar, "WFP_Price"].tolist() == [105.0, 105.0]
    else:
        pd.testing.assert_frame_equal(out[refresh.WFP_COLUMNS], original[refresh.WFP_COLUMNS])
    if refresh_acled:
        assert out.loc[feb, refresh.CONFLICT_COLUMNS].eq(-1.0).all().all()  # uncovered month kept
        near = mar & out["admin_code"].eq("0")
        far = mar & out["admin_code"].eq("10")  # ~5,500 km away: unmatched stays missing
        assert out.loc[near, "event_count_battles"].tolist() == [1]
        assert out.loc[far, refresh.CONFLICT_COLUMNS].isna().all().all()
    else:
        pd.testing.assert_frame_equal(out[refresh.CONFLICT_COLUMNS], original[refresh.CONFLICT_COLUMNS])


def test_wfp_choice_selects_the_system_specific_indicator(sources):
    wfp, _ = sources
    fews_frame = _panel()

    out, _ = refresh.apply_source_choices(fews_frame, "fewsnet", wfp, None)

    # FEWS gets price change (+20%) only where the previous month exists.
    assert out.loc[out["month"].eq(3), "WFP_Price"].tolist() == [120.0, 120.0]
    assert out.loc[out["month"].eq(2), "WFP_Price"].tolist() == [-1.0, -1.0]
    with pytest.raises(ValueError, match="system must be one of"):
        refresh.apply_source_choices(fews_frame, "ch", wfp, None)


def test_combined_wrapper_matches_independent_family_overlays(sources):
    wfp, acled = sources
    frame = _panel()

    combined, report = refresh.replace_sources(frame, wfp["ipcch"], acled)
    independent, _ = refresh.apply_source_choices(frame, "ipcch", wfp, acled)

    pd.testing.assert_frame_equal(combined, independent, check_exact=True)
    assert report["non_source_columns_exactly_preserved"] is True
    assert report["wfp_covered_rows"] == 4 and report["acled_covered_rows"] == 2
    assert report["changed_columns"]["WFP_Price"]["changed_rows"] == 4
