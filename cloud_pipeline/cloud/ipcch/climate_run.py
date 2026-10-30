"""IPCCH climate update for one real generation run (task 10-29; R1, R13, R33, R34, R40, R41, R43): every base's monthly
store through O and every completed growing season, each through the provider ported from its shared script.

Routing: rainfall/temperature/soil bases -> EE raster providers (``climate_ee`` monthly, ``climate_ee_seasonal``);
evi_anom -> S2E3 table providers; spi03/spei03 -> S2C3 table providers (monthly fit for months, the seasonal script's own
fit for seasons). Each indicator-month/season is saved as soon as it passes validation; a later failure (another base, a
season, assembly, inference) never discards it (R41). ``ClimateSourceMissing`` for O of a required base and any
``ClimateProcessingFailure`` stop the run after the bases already saved; the report records what was saved, the
source-level gaps (R43) and the method identifiers (R40).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from cloud.ipcch import climate as cl
from cloud.ipcch.stores import VersionedTable


@dataclass
class ClimateProviders:
    monthly: Callable[[str], cl.Fetch]               # base -> (source, month) -> SourceOutcome
    seasonal: Callable[[str], cl.GsFetch]            # base -> (source, season_year, season, windows) -> SourceOutcome


def default_providers(ee_monthly, ee_seasonal, vegetation, seasonal_vegetation, drought, seasonal_drought) -> ClimateProviders:
    def monthly(base):
        if base == "evi_anom":
            return vegetation.fetch
        if base in ("spi03", "spei03"):
            return drought.bound(base)
        return ee_monthly.bound(base)

    def seasonal(base):
        if base == "evi_anom":
            return seasonal_vegetation.bound_season()
        if base in ("spi03", "spei03"):
            return seasonal_drought.bound_season(base)
        return ee_seasonal.bound(base)
    return ClimateProviders(monthly, seasonal)


def update_all(tables: Callable[[str, str], VersionedTable], *, origin: str, roster, windows: pd.DataFrame,
               providers: ClimateProviders, bases=cl.BASES) -> dict[str, Any]:
    """Monthly then seasonal update of every base; raises on blocking conditions after recording what was saved."""
    report: dict[str, Any] = {"origin": origin, "monthly": {}, "seasonal": {}, "methods": {}}
    for base in bases:
        report["methods"][base] = {"month": cl.method_ids(base, cl.MONTHLY), "gs": cl.method_ids(base, cl.SEASONAL)}
    for base in bases:
        try:
            report["monthly"][base] = cl.update_monthly(tables(base, cl.MONTHLY), base, origin=origin, roster=roster,
                                                        fetch=providers.monthly(base))
        except (cl.ClimateSourceMissing, cl.ClimateProcessingFailure) as exc:
            report["stopped"] = {"base": base, "temporal": cl.MONTHLY, "error": f"{type(exc).__name__}: {exc}"}
            raise type(exc)(f"{exc} [climate run report: {report}]") from exc
    for base in bases:
        try:
            report["seasonal"][base] = cl.update_seasonal(tables(base, cl.SEASONAL), base, origin=origin, roster=roster,
                                                          windows=windows, fetch=providers.seasonal(base))
        except cl.ClimateProcessingFailure as exc:
            report["stopped"] = {"base": base, "temporal": cl.SEASONAL, "error": f"{type(exc).__name__}: {exc}"}
            raise type(exc)(f"{exc} [climate run report: {report}]") from exc
    report["gaps"] = {b: r["gaps"] for b, r in report["monthly"].items() if r["gaps"]}
    report["season_gaps"] = {b: r["gaps"] for b, r in report["seasonal"].items() if r["gaps"]}
    return report
