from __future__ import annotations

from io import StringIO

import pandas as pd

from cloud.batch.evi_extract import wide_month_to_long


def write_selected_month_long_outputs(
    *,
    mean_wide_csv: str,
    std_wide_csv: str,
    feature_month: str,
    scaffold_area_ids: list[str],
) -> dict[str, str]:
    mean_wide = pd.read_csv(StringIO(mean_wide_csv))
    std_wide = pd.read_csv(StringIO(std_wide_csv))
    mean_long = wide_month_to_long(
        mean_wide,
        feature_name="EVI_mean",
        feature_month=feature_month,
        scaffold_area_ids=scaffold_area_ids,
    )
    std_long = wide_month_to_long(
        std_wide,
        feature_name="EVI_std",
        feature_month=feature_month,
        scaffold_area_ids=scaffold_area_ids,
    )
    return {
        "EVI_mean_monthly_long.csv": mean_long.to_csv(index=False),
        "EVI_std_monthly_long.csv": std_long.to_csv(index=False),
    }
