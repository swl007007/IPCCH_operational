from __future__ import annotations

import math
from typing import Any

import pandas as pd


class EVIExtractionError(ValueError):
    """Raised when EVI extraction inputs violate the v1 contract."""


def compute_evi_zone_stats(
    zones: list[dict[str, Any]], *, pixel_inclusion_rule: str
) -> list[dict[str, float | str | None]]:
    if pixel_inclusion_rule != "all_touched_false_center_inside":
        raise EVIExtractionError(
            "pixel inclusion rule must be all_touched_false_center_inside"
        )
    results = []
    for zone in zones:
        area_id = zone["area_id"]
        region_id = zone.get("region_id", area_id)
        if region_id != area_id:
            raise EVIExtractionError("region_id must equal area_id")
        values = [float(value) for value in zone.get("values", []) if value is not None]
        if not values:
            results.append({"region_id": area_id, "EVI_mean": None, "EVI_std": None})
            continue
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        results.append(
            {"region_id": area_id, "EVI_mean": mean, "EVI_std": math.sqrt(variance)}
        )
    return results


def wide_month_to_long(
    wide: pd.DataFrame,
    *,
    feature_name: str,
    feature_month: str,
    scaffold_area_ids: list[str],
) -> pd.DataFrame:
    year, month = (int(part) for part in feature_month.split("-"))
    month_column = f"{year}_{month:02d}"
    if month_column not in wide.columns:
        raise EVIExtractionError(f"missing selected month column: {month_column}")
    result = wide[["region_id", month_column]].rename(
        columns={"region_id": "area_id", month_column: feature_name}
    )
    if set(result["area_id"]) != set(scaffold_area_ids):
        raise EVIExtractionError("EVI long rows must match scaffold area ids")
    result.insert(1, "year", year)
    result.insert(2, "month", month)
    return result[["area_id", "year", "month", feature_name]]
