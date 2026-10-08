import pandas as pd
import pytest

from cloud.orchestrator import delivery_scoring as ds


def _panel(areas=("0", "1"), months=None):
    months = months or [str(p) for p in pd.period_range("2024-09", "2026-04", freq="M")]
    rows = []
    for index, area in enumerate(areas):
        for month in months:
            rows.append({"FEWSNET_admin_code": area, "ADMIN0": "A", "ADMIN1": "B", "ADMIN2": f"C{index}",
                         "ADMIN3": f"D{index}", "ISO3": "SSD", "lat": 5.0 + index, "lon": 25.0 + index,
                         # area 0: population observed only before the scoring window
                         "pop": 1000.0 if (area == "0" and month == "2024-10") else None,
                         "date": f"{month}-01", "EVI": 0.1})
    return pd.DataFrame(rows)


def _window(panel, origin="2026-04"):
    first, last = ds.fewsnet_window(origin)
    month = panel["date"].str[:7]
    return panel.loc[month.between(first, last)].reset_index(drop=True)


def test_window_is_thirteen_calendar_months():
    assert ds.fewsnet_window("2026-10") == ("2025-10", "2026-10")


def test_population_older_than_the_window_comes_from_full_history():
    panel = _panel()
    window = _window(panel)
    assert window["pop"].isna().all()  # the window alone would lose area 0's population
    identity, _ = ds.fewsnet_identity_and_window(panel, window, "2026-04")
    row = identity.set_index("admin_code").loc["0"]
    assert row["population"] == 1000.0 and row["population_reference_period"] == "2024-10"
    assert row["population_source"] == "raw_last_observed"
    assert identity.set_index("admin_code").loc["1", "population_source"] == "missing_raw"


def test_area_present_only_before_the_window_is_rejected_not_dropped():
    panel = pd.concat([_panel(), _panel(areas=("9",), months=["2024-09", "2024-10"])], ignore_index=True)
    with pytest.raises(ValueError, match=r"old-only \['9'\]"):
        ds.fewsnet_identity_and_window(panel, _window(panel), "2026-04")


def test_rows_outside_the_window_are_rejected():
    panel = _panel()
    with pytest.raises(ValueError, match="only 2025-04..2026-04"):
        ds.fewsnet_identity_and_window(panel, panel, "2026-04")


def test_chunked_loader_returns_thin_full_history_and_exact_window(tmp_path):
    panel = _panel()
    path = tmp_path / "normalized.csv"
    panel.to_csv(path, index=False)
    identity_source, window = ds.load_fewsnet_scoring_inputs(path, "2026-04", identity_path=path, chunksize=7)
    assert len(identity_source) == len(panel) and "EVI" not in identity_source
    assert sorted(window["date"].str[:7].unique()) == [str(p) for p in pd.period_range("2025-04", "2026-04", freq="M")]
    assert len(window) == 2 * 13
    pd.testing.assert_frame_equal(window.drop(columns="FEWSNET_admin_code"),
                                  _window(panel).drop(columns="FEWSNET_admin_code"), check_dtype=False)


def test_identity_and_calendar_features_are_not_audited_as_filled_sources():
    raw = ["FEWSNET_admin_code", "lat", "lon", "month", "fews_ha", "EVI", "Tair_f_tavg_mean", "WFP_Price"]
    features = ["FEWSNET_admin_code", "lat", "month", "fews_ha", "EVI_l12", "Tair_zscore", "WFP_Price_m3", "year_2020"]
    deps, unaudited = ds.fewsnet_dependencies(features, raw)
    assert deps == {"fews_ha": ("fews_ha", (0,)), "EVI_l12": ("EVI", (12,)),
                    "Tair_zscore": ("Tair_f_tavg_mean", tuple(range(12))), "WFP_Price_m3": ("WFP_Price", (1, 2, 3))}
    assert unaudited == ["FEWSNET_admin_code", "lat", "month", "year_2020"]


def test_carried_forward_population_never_becomes_the_reference_month(tmp_path):
    observed = _panel()  # area 0 population observed only in 2024-10
    filled = observed.copy()
    filled.loc[filled["FEWSNET_admin_code"].eq("0") & (filled["date"] >= "2024-10-01"), "pop"] = 1000.0  # causal fill
    observed.to_csv(tmp_path / "base.csv", index=False)
    filled.to_csv(tmp_path / "normalized.csv", index=False)

    identity_source, window = ds.load_fewsnet_scoring_inputs(tmp_path / "normalized.csv", "2026-04",
                                                             identity_path=tmp_path / "base.csv")
    identity, _ = ds.fewsnet_identity_and_window(identity_source, window, "2026-04")

    row = identity.set_index("admin_code").loc["0"]
    assert row["population"] == 1000.0 and row["population_reference_period"] == "2024-10"
    assert window.loc[window["FEWSNET_admin_code"].eq("0"), "pop"].eq(1000.0).all()  # model inputs keep the fill
