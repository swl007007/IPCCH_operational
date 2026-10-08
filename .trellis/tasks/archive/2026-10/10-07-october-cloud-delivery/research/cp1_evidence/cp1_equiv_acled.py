import sys, importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, ".")
spec = importlib.util.spec_from_file_location("old", "/tmp/cp1old/tools/refresh_h5_inputs_old.py")
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
import tools.refresh_h5_inputs as new
src = Path("Outcome/model_delivery/202609_h5/20260923_country_confidence_v3/sources")
acled, _ = new.conflict_aggregates(src / "ACLED Data_2026-07-22.csv")
frame = pd.read_csv("Outcome/ipcch_unified/interim/ipcch_scaffold_202501_202604.csv", dtype={"admin_code": "string"})
frame = frame.loc[(frame.year == 2025) & frame.month.between(4, 8)].reset_index(drop=True)
for col in new.WFP_COLUMNS + new.CONFLICT_COLUMNS:
    frame[col] = -1.0  # sentinel history: must survive in uncovered months
frame["ISO3"] = "SSD"
WFP_NONE = pd.DataFrame({"WFP_Price": [1.0], "WFP_Price_std": [1.0]}, index=pd.MultiIndex.from_tuples([("XXX", "1900-01")], names=["ISO3", "period"]))
o_out, o_rep = old.replace_sources(frame, WFP_NONE, acled)
n_out, n_rep = new.replace_sources(frame, WFP_NONE, acled)
pd.testing.assert_frame_equal(o_out, n_out, check_exact=True); assert o_rep == n_rep
k_out, k_rep = new.apply_source_choices(frame, "ipcch", None, acled)
pd.testing.assert_frame_equal(o_out, k_out, check_exact=True)
month = new.periods(n_out)
print(json.dumps({"rows": len(frame), "acled_covered_rows": n_rep["acled_covered_rows"],
  "matched_rows": int(n_out.distance_to_nearest_acled.ge(0).sum()),
  "uncovered_month_sentinels_kept": bool((n_out.loc[month.isin(["2025-04", "2025-08"]), new.CONFLICT_COLUMNS] == -1).all().all()),
  "old_new_frame_equal": True, "old_new_report_equal": True, "acled_only_choice_equal": True}, indent=1))
