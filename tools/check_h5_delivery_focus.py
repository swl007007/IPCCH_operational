"""Focused h5 calendar/source checks; no regression suite."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from tools.refresh_h5_inputs import monthly_price_change, replace_sources, WFP_COLUMNS, CONFLICT_COLUMNS
from fewsnet_partitioned_rf_pipeline.core.horizons import align_horizon


def check():
    frame = pd.DataFrame({"admin_code": ["A"] * 3,
        "feature_month": ["2025-11", "2026-03", "2026-04"], "fews_ipc_crisis": [0, 0, 1], "x": [11, 3, 4]})
    aligned = align_horizon(frame, 5).frame
    assert len(aligned) == 1 and aligned.iloc[0].x == 11 and aligned.iloc[0].fews_ipc_crisis == 1
    raw = pd.DataFrame({"market": ["a"] * 3, "period": ["2026-01", "2026-03", "2026-04"], "Price": [100, 200, 300]})
    changes = monthly_price_change(raw, ["market"], "Price")
    assert changes.period.tolist() == ["2026-04"] and changes.change.tolist() == [50.0]
    panel = pd.DataFrame({"ISO3": ["KEN", "KEN"], "year": [2024, 2026], "month": [1, 4],
                          "lat": [0., 0.], "lon": [0., 0.], "untouched": [7, 8]})
    for col in WFP_COLUMNS + CONFLICT_COLUMNS:
        panel[col] = 9.0
    wfp = pd.DataFrame({"ISO3": ["KEN"], "period": ["2026-04"], "WFP_Price": [150.], "WFP_Price_std": [np.nan]}).set_index(["ISO3", "period"])
    out, _ = replace_sources(panel, wfp, pd.DataFrame(columns=["period"]))
    assert out.loc[0, "WFP_Price"] == 9 and out.loc[1, "WFP_Price"] == 150
    assert np.isnan(out.loc[1, "WFP_Price_std"])
    assert out.untouched.equals(panel.untouched)
    print("PASS: h5 calendar alignment, price-change calendar gaps, covered-group overwrite, historical preservation")


if __name__ == "__main__":
    check()
