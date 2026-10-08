import sys, importlib.util, json
from pathlib import Path
import pandas as pd
sys.path.insert(0, ".")
spec = importlib.util.spec_from_file_location("old", "/tmp/cp1old/tools/refresh_h5_inputs_old.py")
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
import tools.refresh_h5_inputs as new
src = Path("Outcome/model_delivery/202609_h5/20260923_country_confidence_v3/sources")
w_old, r_old = old.wfp_aggregates(src / "wfp_data_7.22.26.csv")
w_new, r_new = new.wfp_aggregates(src / "wfp_data_7.22.26.csv")
for k in w_old: pd.testing.assert_frame_equal(w_old[k], w_new[k], check_exact=True)
assert all(r_new[k] == v for k, v in r_old.items()), "wfp report changed"
a_old, ra_old = old.conflict_aggregates(src / "ACLED Data_2026-07-22.csv")
a_new, ra_new = new.conflict_aggregates(src / "ACLED Data_2026-07-22.csv")
pd.testing.assert_frame_equal(a_old, a_new, check_exact=True)
assert all(ra_new[k] == v for k, v in ra_old.items()), "acled report changed"
frame = pd.read_csv("Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv", low_memory=False,
                    float_precision="round_trip", dtype={"admin_code": "string", "area_id": "string"})
frame = frame.loc[new.periods(frame) <= "2026-04"].reset_index(drop=True)
o_out, o_rep = old.replace_sources(frame, w_old["ipcch"], a_old)
n_out, n_rep = new.replace_sources(frame, w_new["ipcch"], a_new)
pd.testing.assert_frame_equal(o_out, n_out, check_exact=True)
assert o_rep == n_rep, (o_rep, n_rep)
c_out, c_rep = new.apply_source_choices(frame, "ipcch", w_new, a_new)
pd.testing.assert_frame_equal(o_out, c_out, check_exact=True)
print(json.dumps({"wfp_frames_equal": True, "acled_frame_equal": True, "replace_sources_frame_equal": True,
  "replace_sources_report_equal": True, "apply_source_choices_refresh_both_equal": True,
  "rows": len(frame), "wfp_covered_rows": n_rep["wfp_covered_rows"], "acled_covered_rows": n_rep["acled_covered_rows"],
  "new_wfp_report_keys_added": sorted(set(r_new) - set(r_old)), "new_acled_report_keys_added": sorted(set(ra_new) - set(ra_old))}, indent=1))
