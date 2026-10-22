"""Count full-history fit eligibility per horizon (no fitting): existing builder + alignment."""
import json
import sys
from pathlib import Path

import pandas as pd

from fewsnet_partitioned_rf_pipeline.config import ADMIN_SOURCE_COLUMN, HORIZON_KEYS, HORIZON_MONTHS, TARGET_COLUMN
from fewsnet_partitioned_rf_pipeline.core.data import inspect_panel
from fewsnet_partitioned_rf_pipeline.core.horizons import TARGET_MONTH_COLUMN, align_horizon
from fewsnet_partitioned_rf_pipeline.core.normalization import validate_normalization_audit
from fewsnet_partitioned_rf_pipeline.core.preprocessing import Stage3FeatureBuilder, load_feature_contract
from fewsnet_partitioned_rf_pipeline.config import FEATURE_CONTRACT_PATH

panel_path, audit_path, out = map(Path, sys.argv[1:4])
validate_normalization_audit(audit_path, panel_path)
info = inspect_panel(panel_path)
panel = pd.read_csv(panel_path, dtype={ADMIN_SOURCE_COLUMN: "string"}, low_memory=False)
features = Stage3FeatureBuilder().transform(panel, load_feature_contract(FEATURE_CONTRACT_PATH))
report = {"panel_info": {k: v for k, v in info.items() if k != "admin_codes"}, "feature_rows": len(features),
          "horizons": {}}
for months in HORIZON_MONTHS:
    result = align_horizon(features, months)
    frame = result.frame
    targets = frame[TARGET_MONTH_COLUMN].astype(str)
    report["horizons"][HORIZON_KEYS[months]] = {
        "eligible_rows": len(frame), "excluded": result.dropped_rows_by_reason,
        "target_month_range": [targets.min(), targets.max()], "target_months": int(targets.nunique()),
        "class_counts": frame[TARGET_COLUMN].value_counts().sort_index().astype(int).to_dict(),
        "rows_by_recent_target_month": targets[targets >= "2024-06"].value_counts().sort_index().to_dict()}
out.write_text(json.dumps(report, indent=1, default=str) + "\n")
print(json.dumps(report["horizons"], indent=1, default=str))
