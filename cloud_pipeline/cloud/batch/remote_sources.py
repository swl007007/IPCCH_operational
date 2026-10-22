"""Current-repository remote-sensing source contracts, month discovery and zonal statistics.

Operational baseline (user instruction 2026-10-07): the scripts in this repository
define product, grid, reducer and scaling; historical panel parity is not claimed.

| family     | current script                                        | product / grid                                  | reducers |
|------------|-------------------------------------------------------|-------------------------------------------------|----------|
| evi        | EVI/00_ee_export_evi.txt, EVI/02_arcpy_extract_evi.py | MODIS/061/MOD13A3 band EVI, scale 1000 m, raw scaled integers | mean, std |
| fldas      | FLDAS/00_ee_export_fldas_all_bands.txt, 02_*part1-4   | NASA/FLDAS/NOAH01/C/GL/M/V001 all 28 bands, EPSG:4326 0.1 deg | mean, std per band |
| gosif_mean | GOSIF_GPP/00_download_*_mean.py, 02_*_mean.py         | GOSIF-GPP v3 Monthly Mean .tif.gz, provider grid | mean |
| gosif_sd   | GOSIF_GPP/00_download_*_sd.py, 02_*_sd.py             | GOSIF-GPP v2 Monthly SD .tif.gz (provider SD raster) | mean of the SD raster |
| viirs      | VIIRS_nightlight/00_ee_export_*.txt, 02_mosaic, 03_extract | NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG avg_rad, bilinear to 1/30 deg EPSG:4326 | sum, std (+ mean emitted, see note) |

All reducers follow ArcPy ``ZonalStatisticsAsTable(..., "DATA", ...)``: nodata cells
are ignored and STD is the population standard deviation. Cells are included when
their centre falls inside the polygon (rasterio ``all_touched=False``). No unit
scaling is applied. VIIRS ``mean`` is emitted alongside the current ``sum``/``std``
so both systems' chosen operational mappings (``MODEL_COLUMN_MAPPING``) are available;
the mapping to model columns happens at assembly, not here.

Zones are keyed by the explicit native ``admin_code`` property, never feature order or FID.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd


# v2 (2026-10): GOSIF mean from the provider's v3 directory (v2 stopped at 2024-12; the
# v2/v3 break is disclosed by the FEWS retrain). FEWS nightlight maps to the VIIRS sum.
EXTRACTION_CONTRACT_VERSION = "current-repo-remote-scripts-v2"
# Prepared snapshots a delivery may consume: v1 snapshots (GOSIF mean v2 product) stay readable;
# their outputs carry every VIIRS reducer, so assembly applies the current column mapping.
ACCEPTED_EXTRACTION_CONTRACT_VERSIONS = ("current-repo-remote-scripts-v1", EXTRACTION_CONTRACT_VERSION)
NATIVE_KEY = "admin_code"
FLDAS_BANDS = (
    "Evap_tavg", "LWdown_f_tavg", "Lwnet_tavg", "Psurf_f_tavg", "Qair_f_tavg", "Qg_tavg",
    "Qh_tavg", "Qle_tavg", "Qs_tavg", "Qsb_tavg", "RadT_tavg", "Rainf_f_tavg", "SWE_inst",
    "SWdown_f_tavg", "SnowCover_inst", "SnowDepth_inst", "Snowf_tavg", "SoilMoi00_10cm_tavg",
    "SoilMoi100_200cm_tavg", "SoilMoi10_40cm_tavg", "SoilMoi40_100cm_tavg",
    "SoilTemp00_10cm_tavg", "SoilTemp100_200cm_tavg", "SoilTemp10_40cm_tavg",
    "SoilTemp40_100cm_tavg", "Swnet_tavg", "Tair_f_tavg", "Wind_f_tavg",
)
GOSIF_BASE_URL = "http://data.globalecology.unh.edu/data/GOSIF-GPP_v2/Monthly"
GOSIF_V3_BASE_URL = "https://data.globalecology.unh.edu/data/GOSIF-GPP_v3/Monthly"
VIIRS_TRANSFORM = (0.0041666667 * 8, 0, -180.00208525335, 0, -0.0041666667 * 8, 75.00208393335001)

# Chosen current operational construction: model/raw-panel column <- prepared statistic.
# IPCCH follows this repository's CH harmonisation (nightlight_mean <- VIIRS SUM,
# GPP_std <- mean of the provider SD raster). FEWS nightlight is also the VIIRS zonal SUM:
# the FEWS assembly read nightlight_sum_extraction_results.csv into ``nightlight``
# (assemble_latest_FEWSNET 01 cell 1 -> 02 cell 3), and the trained history matches
# avg_rad__sum (2026-10 retrain evidence); nightlight_sd is the zonal STD.
MODEL_COLUMN_MAPPING = {
    "ipcch": {
        "EVI_mean": "EVI__mean", "EVI_std": "EVI__std",
        "GPP_mean": "GPP_Mean__mean", "GPP_std": "GPP_SD__mean",
        "nightlight_mean": "avg_rad__sum", "nightlight_std": "avg_rad__std",
        **{f"{band}_mean": f"{band}__mean" for band in FLDAS_BANDS},
        **{f"{band}_stdDev": f"{band}__std" for band in FLDAS_BANDS},
    },
    "fewsnet": {
        "EVI": "EVI__mean", "gpp_mean": "GPP_Mean__mean",
        "nightlight": "avg_rad__sum", "nightlight_sd": "avg_rad__std",
        "Rainf_f_tavg_mean": "Rainf_f_tavg__mean", "Tair_f_tavg_mean": "Tair_f_tavg__mean",
    },
}


@dataclass(frozen=True)
class SourceContract:
    family: str
    provider: str  # "gee" or "http"
    product: str
    bands: tuple[str, ...]
    reducers: tuple[str, ...]
    script: str
    export: Mapping[str, object]
    # Contract start: discovery and extraction never reach earlier months (the product catalog
    # start, or a version boundary such as GOSIF v3 from 2025-01), never a baseline's first row.
    first_month: str


SOURCE_CONTRACTS = {
    "evi": SourceContract(
        "evi", "gee", "MODIS/061/MOD13A3", ("EVI",), ("mean", "std"),
        "EVI/00_ee_export_evi.txt; EVI/02_arcpy_extract_evi.py",
        {"scale": 1000, "region": (-180, -60, 180, 80)}, "2000-02",
    ),
    "fldas": SourceContract(
        "fldas", "gee", "NASA/FLDAS/NOAH01/C/GL/M/V001", FLDAS_BANDS, ("mean", "std"),
        "FLDAS/00_ee_export_fldas_all_bands.txt; FLDAS/02_arcpy_extract_fldas_part1-4.py",
        {"crs": "EPSG:4326", "crs_transform": (0.1, 0, -180, 0, -0.1, 90), "region": (-180, -90, 180, 90)},
        "1982-01",
    ),
    "gosif_mean": SourceContract(
        # Approved boundary: v2 history through 2024-12 stays as inherited; v3 only from 2025-01.
        "gosif_mean", "http", "GOSIF-GPP_v3/Monthly/Mean from 2025-01 (earlier months: inherited v2 history)",
        ("GPP_Mean",), ("mean",),
        "GOSIF_GPP/00_download_gosif_gpp_mean.py; GOSIF_GPP/02_arcpy_extract_gosif_gpp_mean.py",
        {"url": GOSIF_V3_BASE_URL + "/Mean/GOSIF_GPP_{year}.M{month:02d}_Mean.tif.gz"}, "2025-01",
    ),
    "gosif_sd": SourceContract(
        "gosif_sd", "http", "GOSIF-GPP_v2/Monthly/SD", ("GPP_SD",), ("mean",),
        "GOSIF_GPP/00_download_gosif_gpp_sd.py; GOSIF_GPP/02_arcpy_extract_gosif_gpp_sd.py",
        {"url": GOSIF_BASE_URL + "/SD/GOSIF_GPP_{year}.M{month:02d}_SD.tif.gz"}, "2000-03",
    ),
    "viirs": SourceContract(
        "viirs", "gee", "NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG", ("avg_rad",), ("sum", "std", "mean"),
        "VIIRS_nightlight/00_ee_export_viirs_nightlight.txt; 02_arcpy_mosaic; 03_arcpy_extract",
        {"resample": "bilinear", "crs": "EPSG:4326", "crs_transform": VIIRS_TRANSFORM}, "2014-01",
    ),
}

# Families each system actually consumes (FEWSNET uses no GOSIF SD statistic).
SYSTEM_FAMILIES = {
    system: tuple(family for family, contract in SOURCE_CONTRACTS.items()
                  if any(column.split("__")[0] in contract.bands for column in mapping.values()))
    for system, mapping in MODEL_COLUMN_MAPPING.items()
}

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class SourceRetrievalError(RuntimeError):
    """Provider availability or download could not be established.

    Authentication errors, timeouts, malformed responses and unexpected HTTP
    statuses are failures, never treated as normal publication lag.
    """


class ExtractionError(ValueError):
    """Raster or geometry inputs violate the extraction contract."""


# --- completed-month discovery -------------------------------------------------


def latest_completed_month(
    published_months: Iterable[str], *, origin_month: str, cutoff_utc: datetime
) -> str | None:
    """Latest published month that is <= origin and whose calendar month ended by the cutoff.

    An unfinished current-month composite is never eligible, even if listed.
    """
    limit = _ordinal(last_eligible_month(origin_month, cutoff_utc))
    eligible = [_ordinal(month) for month in map(_month, published_months) if _ordinal(month) <= limit]
    return _month_text(max(eligible)) if eligible else None


def last_eligible_month(origin_month: str, cutoff_utc: datetime) -> str:
    """min(origin, last calendar month that ended before the cutoff's own month)."""
    if cutoff_utc.tzinfo is None:
        raise ValueError("cutoff_utc must be timezone-aware")
    cutoff = cutoff_utc.astimezone(timezone.utc)
    last_ended = cutoff.year * 12 + cutoff.month - 2
    return _month_text(min(_ordinal(_month(origin_month)), last_ended))


def months_between(after_month: str, through_month: str) -> list[str]:
    """Calendar months strictly after ``after_month`` up to and including ``through_month``."""
    start, end = _ordinal(_month(after_month)) + 1, _ordinal(_month(through_month))
    return [_month_text(value) for value in range(start, end + 1)]


def gee_published_months(
    list_images: Callable[[str, str, str], Sequence[tuple[int, str]]],
    collection: str,
    *,
    start_month: str,
    end_month: str,
) -> dict[str, str]:
    """Month -> exact Earth Engine image ID for months in ``[start_month, end_month]``.

    ``list_images(collection, start_iso, end_iso)`` returns ``(system:time_start ms,
    system:id)`` pairs from one query; acquisition later loads that exact image ID, so
    the provider image cannot silently change after discovery. Any exception or
    malformed entry is a retrieval failure; two images in one month are ambiguous.
    """
    end_exclusive = _month_text(_ordinal(_month(end_month)) + 1)
    try:
        images = list(list_images(collection, f"{_month(start_month)}-01", f"{end_exclusive}-01"))
    except Exception as exc:
        raise SourceRetrievalError(f"{collection} availability query failed: {exc}") from exc
    by_month: dict[str, list[str]] = {}
    for entry in images:
        millis, image_id = entry if isinstance(entry, (tuple, list)) and len(entry) == 2 else (None, None)
        if not isinstance(millis, (int, float)) or isinstance(millis, bool) or not isinstance(image_id, str) \
                or not image_id.startswith(collection + "/"):
            raise SourceRetrievalError(f"{collection} returned malformed image entry {entry!r}")
        stamp = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
        by_month.setdefault(f"{stamp.year:04d}-{stamp.month:02d}", []).append(image_id)
    duplicated = sorted(month for month, ids in by_month.items() if len(ids) > 1)
    if duplicated:
        raise SourceRetrievalError(f"{collection} has multiple images for months {duplicated}")
    return {month: ids[0] for month, ids in sorted(by_month.items())}


def http_published_months(
    head: Callable[[str], int],
    url_template: str,
    candidate_months: Iterable[str],
) -> dict[str, str]:
    """Month -> provider URL for files that exist: HTTP 200 published, 404 not yet published.

    ``head(url)`` returns the status code. Any other status or an exception is a
    retrieval failure. The downloaded bytes' SHA-256 binds the snapshot later.
    """
    published = {}
    for month in candidate_months:
        url = gosif_url(url_template, month)
        try:
            status = head(url)
        except Exception as exc:
            raise SourceRetrievalError(f"availability request failed for {url}: {exc}") from exc
        if status == 200:
            published[month] = url
        elif status != 404:
            raise SourceRetrievalError(f"unexpected HTTP {status} for {url}")
    return published


def gosif_url(url_template: str, month: str) -> str:
    year, number = _month(month).split("-")
    return url_template.format(year=int(year), month=int(number))


def gee_export_spec(family: str, month: str) -> dict:
    """Earth Engine export parameters taken from the current repository scripts."""
    contract = SOURCE_CONTRACTS[family]
    if contract.provider != "gee":
        raise ValueError(f"{family} is not an Earth Engine source")
    start = f"{_month(month)}-01"
    end = f"{_month_text(_ordinal(month) + 1)}-01"
    spec = {"collection": contract.product, "start": start, "end": end, "bands": list(contract.bands)}
    spec.update({key: value for key, value in contract.export.items()})
    return spec


# --- geometry and zonal statistics --------------------------------------------


def native_geometries(feature_collection: Mapping, *, roster: Sequence[str]) -> dict[str, dict]:
    """Geometries keyed by the explicit string ``admin_code``; must equal the pinned roster."""
    by_key: dict[str, dict] = {}
    for feature in feature_collection.get("features", []):
        key = (feature.get("properties") or {}).get(NATIVE_KEY)
        if not isinstance(key, str) or not key.strip() or key != key.strip():
            raise ExtractionError(f"geometry {NATIVE_KEY} must be a non-empty string, got {key!r}")
        if key in by_key:
            raise ExtractionError(f"duplicate geometry {NATIVE_KEY}: {key}")
        by_key[key] = feature["geometry"]
    roster_keys = list(roster)
    if len(set(roster_keys)) != len(roster_keys) or set(roster_keys) != set(by_key):
        missing = sorted(set(roster_keys) - set(by_key))[:5]
        extra = sorted(set(by_key) - set(roster_keys))[:5]
        raise ExtractionError(f"geometry keys must equal the roster; missing {missing}, extra {extra}")
    return {key: by_key[key] for key in roster_keys}


def zonal_statistics(
    raster_path: str,
    geometries: Mapping[str, dict],
    *,
    family: str,
    month: str,
    geometry_crs: str | None = "EPSG:4326",
) -> pd.DataFrame:
    """One row per native key: ``{band}__{reducer}`` columns, NaN where no valid cell."""
    import rasterio
    from rasterio.mask import mask
    from rasterio.warp import transform_geom

    contract = SOURCE_CONTRACTS[family]
    rows = []
    with rasterio.open(raster_path) as dataset:
        band_indexes = _band_indexes(dataset, contract)
        if not dataset.crs:
            raise ExtractionError(f"{family} raster has no CRS; polygons cannot be placed on an unknown grid")
        dataset_crs = dataset.crs.to_string()
        for key, geometry in geometries.items():
            shape = geometry
            if geometry_crs and geometry_crs != dataset_crs:
                shape = transform_geom(geometry_crs, dataset_crs, geometry)
            try:
                data, _ = mask(dataset, [shape], crop=True, all_touched=False, filled=False,
                               indexes=list(band_indexes.values()))
            except ValueError as exc:
                if "overlap" not in str(exc).lower():
                    raise
                data = None
            row = {NATIVE_KEY: key, "month": _month(month)}
            for position, band in enumerate(band_indexes):
                values = _valid_values(None if data is None else data[position])
                for reducer in contract.reducers:
                    row[f"{band}__{reducer}"] = _reduce(values, reducer)
            rows.append(row)
    return pd.DataFrame(rows)


def stamp_band_names(raster_path: str, bands: Sequence[str]) -> str:
    """Bind multi-band identity to the explicit Earth Engine ``select(bands)`` order.

    Missing descriptions are written from the explicit selection order; existing
    descriptions must equal it exactly. Returns how the names were established.
    """
    import rasterio

    with rasterio.open(raster_path, "r+") as dataset:
        if dataset.count != len(bands):
            raise ExtractionError(f"raster has {dataset.count} bands, export selected {len(bands)}")
        descriptions = tuple(dataset.descriptions or ())
        if all(not description for description in descriptions):
            for index, band in enumerate(bands, start=1):
                dataset.set_band_description(index, band)
            return "explicit_export_selection_order"
        if descriptions != tuple(bands):
            raise ExtractionError(f"raster band names {descriptions} differ from the export selection")
        return "raster_band_descriptions"


def mosaic_shards(shard_paths: Sequence[str], output_path: str) -> str:
    """Join non-overlapping Earth Engine export shards into one GeoTIFF.

    The current VIIRS script mosaics with ArcPy BLEND, which only differs from
    first-wins where tiles overlap; Earth Engine shards of one export do not overlap.
    Band descriptions are carried over so multi-band identity survives.

    Per-band validity (nodata values and internal/dataset masks) is preserved: the
    shards are merged as masked arrays and written as float64 with NaN nodata, so an
    invalid cell can never become a valid 0. Reducers already work in float64.
    """
    import rasterio
    from rasterio.merge import merge

    if not shard_paths:
        raise ExtractionError("no raster shards to mosaic")
    if len(shard_paths) == 1:
        return shard_paths[0]
    datasets = [rasterio.open(path) for path in shard_paths]
    try:
        descriptions = {tuple(dataset.descriptions) for dataset in datasets}
        if len(descriptions) != 1:
            raise ExtractionError("raster shards disagree on band descriptions")
        # Explicit float64/NaN destination: without it a nodata-less source gets an
        # implicit 0 nodata and valid zero pixels would be masked.
        array, transform = merge(datasets, method="first", masked=True, nodata=np.nan, dtype="float64")
        filled = np.ma.filled(array.astype("float64"), np.nan)
        profile = {
            "driver": "GTiff", "height": filled.shape[1], "width": filled.shape[2], "count": filled.shape[0],
            "dtype": "float64", "crs": datasets[0].crs, "transform": transform, "nodata": np.nan,
        }
        with rasterio.open(output_path, "w", **profile) as out:
            out.write(filled)
            for index, description in enumerate(next(iter(descriptions)), start=1):
                if description:
                    out.set_band_description(index, description)
    finally:
        for dataset in datasets:
            dataset.close()
    return output_path


def _band_indexes(dataset, contract: SourceContract) -> dict[str, int]:
    if len(contract.bands) == 1:
        if dataset.count != 1:
            raise ExtractionError(f"{contract.family} raster must have one band, found {dataset.count}")
        return {contract.bands[0]: 1}
    # Multi-band identity comes from band descriptions, never from band position.
    descriptions = list(dataset.descriptions or ())
    if any(not description for description in descriptions):
        raise ExtractionError(f"{contract.family} raster lacks band descriptions; band identity unavailable")
    if sorted(descriptions) != sorted(contract.bands) or len(set(descriptions)) != len(descriptions):
        raise ExtractionError(f"{contract.family} bands {descriptions} do not match the contract")
    return {band: descriptions.index(band) + 1 for band in contract.bands}


def _valid_values(masked) -> np.ndarray:
    if masked is None:
        return np.array([], dtype="float64")
    values = np.ma.compressed(masked).astype("float64")
    return values[np.isfinite(values)]


def _reduce(values: np.ndarray, reducer: str) -> float:
    if values.size == 0:
        return math.nan
    if reducer == "mean":
        return float(values.mean())
    if reducer == "std":
        return float(values.std(ddof=0))  # population SD, as ArcPy STD
    if reducer == "sum":
        return float(values.sum())
    raise ValueError(f"unknown reducer {reducer}")


def _month(value: object) -> str:
    if not isinstance(value, str) or _MONTH_RE.fullmatch(value) is None:
        raise ValueError(f"month must be YYYY-MM, got {value!r}")
    return value


def _ordinal(month: str) -> int:
    return int(month[:4]) * 12 + int(month[5:7]) - 1


def _month_text(ordinal: int) -> str:
    return f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}"
