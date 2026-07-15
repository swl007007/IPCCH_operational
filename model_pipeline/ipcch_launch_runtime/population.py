"""Output-only population selection for monthly assembly."""

import math


POPULATION_OUTPUT_COLUMNS = (
    "population_estimate",
    "population_reference_period",
    "population_imputation_method",
)


class PopulationSelectionError(ValueError):
    """Raised when a complete no-future population snapshot cannot be built."""


class PopulationSnapshotBuilder:
    def __init__(self, *, feature_year: int, feature_month: int):
        self.feature_period = (int(feature_year), int(feature_month))
        self._by_area = {}
        self._by_area_period = {}

    def add(self, area_id, year, month, population):
        area_id = str(area_id).strip()
        period = (int(year), int(month))
        if period > self.feature_period or _is_blank(population):
            return
        try:
            value = float(population)
        except (TypeError, ValueError) as exc:
            raise PopulationSelectionError(
                "population must be finite and non-negative"
            ) from exc
        if not math.isfinite(value) or value < 0:
            raise PopulationSelectionError(
                "population must be finite and non-negative"
            )
        key = (area_id, period)
        previous_same_period = self._by_area_period.get(key)
        if previous_same_period is not None and previous_same_period != value:
            raise PopulationSelectionError(
                "conflicting population values for the same area and period"
            )
        self._by_area_period[key] = value
        previous = self._by_area.get(area_id)
        if previous is None or period > previous[0]:
            self._by_area[area_id] = (period, value)

    def build(self, required_area_ids):
        required = [str(area_id).strip() for area_id in required_area_ids]
        missing = [area_id for area_id in required if area_id not in self._by_area]
        if missing:
            raise PopulationSelectionError(
                "area_id has no current or prior population: {0}".format(
                    ", ".join(missing[:5])
                )
            )
        snapshot = {}
        observed = 0
        carried = 0
        for area_id in required:
            period, value = self._by_area[area_id]
            is_current = period == self.feature_period
            method = (
                "observed_feature_month"
                if is_current
                else "last_observation_carried_forward"
            )
            observed += int(is_current)
            carried += int(not is_current)
            snapshot[area_id] = {
                "population_estimate": value,
                "population_reference_period": "{0:04d}-{1:02d}".format(*period),
                "population_imputation_method": method,
            }
        return snapshot, {
            "observed_feature_month_rows": observed,
            "last_observation_carried_forward_rows": carried,
            "missing_area_count": 0,
        }


def _is_blank(value):
    return value is None or str(value).strip() == "" or str(value).lower() == "nan"
