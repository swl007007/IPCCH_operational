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
from typing import Any, Callable, Mapping

import pandas as pd

from cloud.ipcch import climate as cl
from cloud.ipcch.stores import VersionedTable


@dataclass
class ClimateProviders:
    monthly: Callable[[str], cl.Fetch]               # base -> (source, month) -> SourceOutcome
    seasonal: Callable[[str], cl.GsFetch]            # base -> (source, season_year, season, windows) -> SourceOutcome
    production: Mapping[str, Any] | None = None      # this run's table production report (table_producers), if any


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
               providers: ClimateProviders, bases=cl.BASES, declared_extra=()) -> dict[str, Any]:
    """Monthly then seasonal update of every base; raises on blocking conditions after recording what was saved.
    ``declared_extra``: the fixed geography's declared out-of-roster admins (``geography.declared_extras``)."""
    report: dict[str, Any] = {"origin": origin, "monthly": {}, "seasonal": {}, "methods": {},
                              "production": providers.production}
    for base in bases:
        report["methods"][base] = {"month": cl.method_ids(base, cl.MONTHLY), "gs": cl.method_ids(base, cl.SEASONAL)}
    for base in bases:
        try:
            report["monthly"][base] = cl.update_monthly(tables(base, cl.MONTHLY), base, origin=origin, roster=roster,
                                                        fetch=providers.monthly(base), declared_extra=declared_extra)
        except (cl.ClimateSourceMissing, cl.ClimateProcessingFailure) as exc:
            report["stopped"] = {"base": base, "temporal": cl.MONTHLY, "error": f"{type(exc).__name__}: {exc}",
                                 "saved_in_base": getattr(exc, "climate_report", {}).get("saved", [])}
            report["monthly"][base] = getattr(exc, "climate_report", None)
            err = type(exc)(f"{exc} [climate run report: {report}]")
            err.climate_run_report = report
            raise err from exc
    for base in bases:
        try:
            report["seasonal"][base] = cl.update_seasonal(tables(base, cl.SEASONAL), base, origin=origin, roster=roster,
                                                          windows=windows, fetch=providers.seasonal(base),
                                                          declared_extra=declared_extra)
        except cl.ClimateProcessingFailure as exc:
            report["stopped"] = {"base": base, "temporal": cl.SEASONAL, "error": f"{type(exc).__name__}: {exc}",
                                 "saved_in_base": getattr(exc, "climate_report", {}).get("saved", [])}
            report["seasonal"][base] = getattr(exc, "climate_report", None)
            err = type(exc)(f"{exc} [climate run report: {report}]")
            err.climate_run_report = report
            raise err from exc
    report["gaps"] = {b: r["gaps"] for b, r in report["monthly"].items() if r["gaps"]}
    report["season_gaps"] = {b: r["gaps"] for b, r in report["seasonal"].items() if r["gaps"]}
    return report


class _Readback:
    """The table boundary for the consumers: frames this run's producer already read back are served from memory
    (validated once, never read twice); everything else goes to the transport."""

    def __init__(self, transport, frames: Mapping[str, Any]):
        self.transport, self.frames = transport, dict(frames)

    def missing_assets(self, asset_ids):
        return [] if all(a in self.frames for a in asset_ids) else self.transport.missing_assets(asset_ids)

    def read_asset_table(self, asset_id):
        return self.frames[asset_id].copy() if asset_id in self.frames else self.transport.read_asset_table(asset_id)


def real_providers(transport, *, origin: str, roster, calendar_windows: pd.DataFrame, asset_root: str | None = None,
                   production=None) -> ClimateProviders:
    """Every base's providers over ONE concrete transport (``ee_transport.EETransport``: EEBackend + TableBackend):
    monthly/seasonal raster providers, S2E3 vegetation and S2C3 drought table providers on the fixed roster; data reads
    stop at the first day after O. ``asset_root`` overrides the shared scripts' private-asset root (han-sandbox).
    ``production`` (``table_producers.Production``): this run's produced tables replace their existing names
    (``TableRefs.produced``); drought chunks run through O's year (``climate_tables.year_chunks``)."""
    from cloud.ipcch import climate_ee as ce
    from cloud.ipcch import climate_ee_seasonal as cs
    from cloud.ipcch import climate_tables as ct

    refs = ce.AssetRefs(root=asset_root) if asset_root else ce.AssetRefs()
    trefs = ct.TableRefs(**({"root": asset_root} if asset_root else {}), year_chunks=ct.year_chunks(int(origin[:4])),
                         produced=dict(production.produced) if production else {})
    tables = _Readback(transport, production.frames) if production else transport
    admins = [str(a) for a in roster]
    providers = default_providers(
        ce.MonthlyEEProvider(transport, refs=refs),
        cs.SeasonalEEProvider(transport, data_end=cl.first_day_after(origin), calendar_windows=calendar_windows, refs=refs),
        ct.VegetationProvider(tables, refs=trefs, admins=admins),
        ct.SeasonalVegetationProvider(tables, refs=trefs, admins=admins),
        ct.DroughtProvider(tables, admins=admins, refs=trefs),
        ct.SeasonalDroughtProvider(tables, admins=admins, refs=trefs))
    providers.production = production.report if production else None
    return providers


def real_provider_factory(transport, *, roster, asset_root: str | None = None, producer=None,
                          tables: Callable[[str, str], Any] | None = None):
    """The ``Generation.climate_providers`` factory for real runs: providers are built only once the derived season
    windows (delivered + calendar-extended) and O are known, so the seasonal providers see the same windows as the
    climate scheduling and assembly. With ``producer`` (``table_producers.TableProducer``) and the retained ``tables``
    accessor (base, temporal) -> VersionedTable, this run's unsaved table-based periods are produced first (plan ->
    exports -> readback) and their tables mapped into the consumers; already-retained periods produce nothing."""
    if (producer is None) != (tables is None):
        raise ValueError("a table producer needs the retained tables accessor (and vice versa)")

    def build(windows, origin):
        production = producer.run(tables, origin=origin, windows=windows) if producer is not None else None
        return real_providers(transport, origin=origin, roster=roster, calendar_windows=windows, asset_root=asset_root,
                              production=production)
    return build
