import argparse
import csv
import hashlib
import os
import sys
from pathlib import Path


SOURCE_DATA_ROOT = Path(
    "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data"
)
ASSEMBLED_ROOT = SOURCE_DATA_ROOT / "assembled_IPCCH"
CODEBOOK = ASSEMBLED_ROOT / "metadata" / "variable_codebook_reorganized.csv"
G03_SUMMARY = Path(
    "Outcome/ipcch_unified/features/ipcch_fixed_slow_features_summary.csv"
)
HANDOVER_OUTPUT = Path(
    "Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv"
)
HANDOVER_PANEL = Path("Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv")
PAPER_PDF = Path(
    "/mnt/c/Users/swl00/Downloads/"
    "Forecasting_FEWS_NET_Food_Security_Crises_Using_a_Geo_Aware_"
    "Spatial_Clustering_Model.pdf"
)


FAMILY_METADATA = {
    "aez": {
        "source_family_name": "Agricultural ecological zones",
        "upstream_source_folder": SOURCE_DATA_ROOT / "AEZ",
        "source_files": [
            SOURCE_DATA_ROOT / "AEZ" / "ch_aez_completed.csv",
            SOURCE_DATA_ROOT / "AEZ" / "IPC_aez_completed.csv",
            SOURCE_DATA_ROOT / "AEZ" / "FEWSNET_aez_completed.csv",
            SOURCE_DATA_ROOT / "AEZ" / "diff_aez_completed.csv",
        ],
        "provider_dataset_source": "Agricultural Ecological Zones; paper Appendix Table A10 cites Tricht et al. (2023).",
        "provider_vintage_or_version": "Tricht et al. (2023) per paper source table; local processed files dated 2025.",
        "unit_or_measure": "AEZ code dummy/indicator columns.",
        "aggregation_method": "Spatially match AEZ layer to IPCCH polygons/points and encode zone categories as dummy variables.",
        "paper_evidence": "PDF data section lines 772-777 and Appendix Table A10 lines 1828-1834.",
        "notes": "Current IPCCH handover uses 21 AEZ_* columns from the unified panel.",
    },
    "asap_land_cover": {
        "source_family_name": "ASAP cropland and rangeland masks",
        "upstream_source_folder": SOURCE_DATA_ROOT / "ASAP_land_cover",
        "source_files": [
            SOURCE_DATA_ROOT / "ASAP_land_cover" / "asap_mask_crop_v02.tif",
            SOURCE_DATA_ROOT / "ASAP_land_cover" / "asap_mask_rangeland_v02.tif",
            SOURCE_DATA_ROOT / "ASAP_land_cover" / "ch_ASAP_completed_sampled.csv",
            SOURCE_DATA_ROOT / "ASAP_land_cover" / "IPC_ASAP_completed.csv",
            SOURCE_DATA_ROOT / "ASAP_land_cover" / "FEWS_ASAP_completed_sampled.csv",
            SOURCE_DATA_ROOT / "ASAP_land_cover" / "Diff_ASAP_completed_sampled.csv",
        ],
        "provider_dataset_source": "FAO Anomaly Hotspots of Agricultural Production (ASAP) cropland and rangeland masks.",
        "provider_vintage_or_version": "ASAP mask v02 local rasters; paper reference retrieved 2024.",
        "unit_or_measure": "Processed cropland and rangeland raster summary values.",
        "aggregation_method": "Sample or summarize ASAP crop/rangeland mask rasters over IPCCH polygons/points.",
        "paper_evidence": "PDF data section lines 753-777 and reference lines 923-927.",
        "notes": "Paper describes cropland/rangeland shares; local fields are named crop and range.",
    },
    "river_distance": {
        "source_family_name": "Distance to rivers",
        "upstream_source_folder": SOURCE_DATA_ROOT / "Distance_to_rivers",
        "source_files": [
            SOURCE_DATA_ROOT / "Distance_to_rivers" / "ch_distance_to_river_completed.csv",
            SOURCE_DATA_ROOT / "Distance_to_rivers" / "IPC_distance_to_river_completed.csv",
            SOURCE_DATA_ROOT / "Distance_to_rivers" / "FEWS_distance_to_river_completed.csv",
            SOURCE_DATA_ROOT / "Distance_to_rivers" / "diff_distance_to_river_completed.csv",
            SOURCE_DATA_ROOT / "Distance_to_rivers" / "hydro_dist_main_combined.csv",
        ],
        "provider_dataset_source": "World Bank river layers and Andreadis et al. (2013) global river database.",
        "provider_vintage_or_version": "Andreadis et al. (2013); local processed files dated 2025.",
        "unit_or_measure": "Distance from polygon/point centroid to nearest mapped river segment, in processed distance units.",
        "aggregation_method": "Calculate nearest-river distance from IPCCH polygon or centroid geometry using global hydrographic layers.",
        "paper_evidence": "PDF data section lines 574-582 and Appendix Table A10 lines 1787-1791.",
        "notes": "G-03 summary flags distance_to_river as varying within 16 areas; handover output uses latest nonmissing panel value.",
    },
    "terrain": {
        "source_family_name": "Terrain and physical geography",
        "upstream_source_folder": SOURCE_DATA_ROOT,
        "source_files": [
            SOURCE_DATA_ROOT / "Elevation" / "ch_elevation_completed_FINAL.csv",
            SOURCE_DATA_ROOT / "Elevation" / "IPC_elevation_completed.csv",
            SOURCE_DATA_ROOT / "Ruggedness" / "ch_ruggedness_percentile_completed.csv",
            SOURCE_DATA_ROOT / "Ruggedness" / "IPC_ruggedness_completed.csv",
            SOURCE_DATA_ROOT / "Slope" / "ch_slope_completed_batched.csv",
            SOURCE_DATA_ROOT / "Slope" / "IPC_slope_completed.csv",
        ],
        "provider_dataset_source": "Elevation and slope from ESA/ERA5-derived local processed outputs; ruggedness from Nunn and Puga (2012).",
        "provider_vintage_or_version": "Nunn and Puga (2012) for ruggedness; local elevation/slope processed files dated 2025.",
        "unit_or_measure": "Elevation above sea level; terrain ruggedness index; slope.",
        "aggregation_method": "Extract or aggregate terrain raster values to IPCCH polygons/points.",
        "paper_evidence": "PDF data section lines 557-572 and Appendix Table A10 lines 1787-1791.",
        "notes": "Paper source table lists Elevation=ESA, Ruggedness=Nunn and Puga, Slope=ESA; prose also describes ERA5 for elevation.",
    },
    "isric_soilgrids": {
        "source_family_name": "ISRIC SoilGrids soil attributes",
        "upstream_source_folder": SOURCE_DATA_ROOT / "ISRIC",
        "source_files": [
            SOURCE_DATA_ROOT / "ISRIC" / "ch_soilgrids_completed_batched.csv",
            SOURCE_DATA_ROOT / "ISRIC" / "IPC_soilgrids_completed.csv",
            SOURCE_DATA_ROOT / "ISRIC" / "FEWS_soilgrids_completed_batched.csv",
            SOURCE_DATA_ROOT / "ISRIC" / "Diff_soilgrids_completed_batched.csv",
        ],
        "provider_dataset_source": "International Soil Reference and Information Centre (ISRIC) SoilGrids.",
        "provider_vintage_or_version": "SoilGrids reference retrieved 2024 in paper; local processed files dated 2025.",
        "unit_or_measure": "SoilGrids near-surface attributes at 5-15 cm depth in IPCCH field names/codebook.",
        "aggregation_method": "Extract or aggregate SoilGrids raster layers to IPCCH polygons/points.",
        "paper_evidence": "PDF data section lines 753-767 and Appendix Table A10 lines 1830-1834.",
        "notes": "IPCCH field names use 5-15cm. The FEWS paper prose mentions near-surface 0-5 cm, so the IPCCH codebook/field names should govern this handover.",
    },
    "market_access": {
        "source_family_name": "Market access and market distance",
        "upstream_source_folder": SOURCE_DATA_ROOT,
        "source_files": [
            SOURCE_DATA_ROOT / "Market_access" / "acc_50k.tif",
            SOURCE_DATA_ROOT / "Market_access" / "ch_market_access_completed_batched.csv",
            SOURCE_DATA_ROOT / "Market_access" / "IPC_market_access_completed.csv",
            SOURCE_DATA_ROOT / "Market_access" / "FEWS_market_access_completed_batched.csv",
            SOURCE_DATA_ROOT / "FAO" / "ch_with_matched_markets.csv",
            SOURCE_DATA_ROOT / "FAO" / "IPC_with_matched_markets.csv",
        ],
        "provider_dataset_source": "market_access from Weiss et al. travel time to cities; market_distance from FAO price market matching.",
        "provider_vintage_or_version": "Weiss et al. 2015/2018 accessibility layer; FAO price records retrieved in local FAO workflow; local processed files dated 2025.",
        "unit_or_measure": "market_access is travel-time/accessibility raster value; market_distance is distance to nearest matched food market.",
        "aggregation_method": "Average travel-time raster to IPCCH polygons/points; compute nearest FAO market distance from polygon centroid.",
        "paper_evidence": "PDF data section lines 650-653 and 717-726; Appendix Table A10 lines 1809 and 1814-1829.",
        "notes": "G-03 family contains both market_access and market_distance. They have different upstream sources.",
    },
    "population_context": {
        "source_family_name": "Population density",
        "upstream_source_folder": SOURCE_DATA_ROOT / "Populationdensity",
        "source_files": [
            SOURCE_DATA_ROOT / "Populationdensity" / "ch_population_density_completed_batched.csv",
            SOURCE_DATA_ROOT / "Populationdensity" / "IPC_population_density_completed_batched.csv",
            SOURCE_DATA_ROOT / "Populationdensity" / "FEWS_population_density_completed_batched.csv",
            SOURCE_DATA_ROOT / "Populationdensity" / "Diff_population_density_completed_batched.csv",
        ],
        "provider_dataset_source": "Local Populationdensity processed outputs; FEWS paper includes population density as an economic condition predictor.",
        "provider_vintage_or_version": "Local processed files dated 2025; provider vintage not explicit in available metadata.",
        "unit_or_measure": "Population density raster summary value.",
        "aggregation_method": "Extract or aggregate population density layer to IPCCH polygons/points.",
        "paper_evidence": "PDF predictor overview lines 510-524 and Appendix Table A10 economic-conditions panel lines 1814-1829.",
        "notes": "G-03 summary reports popdensity is present for 1,308 of 6,227 areas.",
    },
    "coastline_distance": {
        "source_family_name": "Distance to coastline",
        "upstream_source_folder": SOURCE_DATA_ROOT / "Coastline_distance_NOAA",
        "source_files": [
            SOURCE_DATA_ROOT
            / "Coastline_distance_NOAA"
            / "GMT_intermediate_coast_distance_01d.tif",
            SOURCE_DATA_ROOT
            / "Coastline_distance_NOAA"
            / "IPCCH_2026_price_completed_unique_lat_lon_coastline_dist.csv",
        ],
        "provider_dataset_source": "NOAA coastline distance raster and local IPCCH lat/lon extraction.",
        "provider_vintage_or_version": "Local processed files dated 2025/2026 where available; provider vintage not explicit in available metadata.",
        "unit_or_measure": "Distance to coastline in processed raster distance units.",
        "aggregation_method": "Match local coastline distance extraction to IPCCH area coordinates by rounded latitude/longitude.",
        "paper_evidence": "Not separately cited in the FEWS NET paper evidence extracted for G-04; included because ToR/codebook list coastline_dist.",
        "notes": "Added to close WDG-02; source CSV fully matches the 6,227 current area lookup rows by rounded lat/lon.",
    },
}


OUTPUT_COLUMNS = [
    "family",
    "source_family_name",
    "features",
    "feature_count",
    "handover_source_panel",
    "handover_source_panel_sha256",
    "handover_output_file",
    "handover_output_sha256",
    "join_key",
    "value_rule",
    "upstream_source_folder",
    "source_files",
    "source_file_rows",
    "source_file_sizes_bytes",
    "source_file_mtimes",
    "source_file_sha256",
    "provider_dataset_source",
    "provider_vintage_or_version",
    "unit_or_measure",
    "aggregation_method",
    "codebook_evidence",
    "paper_evidence",
    "stability_summary",
    "evidence_level",
    "notes",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build IPCCH G-04 source/vintage manifest for fixed and slow-moving features."
    )
    parser.add_argument(
        "--output",
        default="Outcome/ipcch_unified/metadata/ipcch_fixed_slow_source_vintage_manifest.csv",
        help="Output family-level source/vintage manifest CSV.",
    )
    return parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def data_row_count(path):
    if path.suffix.lower() != ".csv" or not path.exists():
        return ""
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def joined(items):
    return "; ".join(str(item) for item in items if str(item))


def read_g03_summary(path):
    by_family = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            family = row["family"]
            by_family.setdefault(family, []).append(row)
    return by_family


def read_codebook(path):
    codebook = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            codebook[row["variable"]] = row
    return codebook


def file_metadata(paths):
    existing = [path for path in paths if path.exists()]
    return {
        "paths": joined(existing),
        "rows": joined(
            "{0}={1}".format(path.name, data_row_count(path)) for path in existing
        ),
        "sizes": joined(
            "{0}={1}".format(path.name, path.stat().st_size) for path in existing
        ),
        "mtimes": joined(
            "{0}={1}".format(
                path.name,
                __import__("datetime")
                .datetime.fromtimestamp(path.stat().st_mtime)
                .strftime("%Y-%m-%d %H:%M:%S"),
            )
            for path in existing
        ),
        "hashes": joined(
            "{0}={1}".format(path.name, sha256(path)) for path in existing
        ),
        "missing": [path for path in paths if not path.exists()],
    }


def codebook_evidence(features, codebook):
    entries = []
    for feature in features:
        row = codebook.get(feature)
        if row:
            entries.append(
                "{0}: {1} / {2} / {3}".format(
                    feature,
                    row.get("group", ""),
                    row.get("category", ""),
                    row.get("description", ""),
                )
            )
    return joined(entries)


def stability_summary(rows):
    parts = []
    for row in rows:
        parts.append(
            "{feature}: {classification}, areas_with_value={areas_with_value}, "
            "missing_area_count={missing_area_count}, max_distinct_values_per_area={max_distinct_values_per_area}, "
            "varying_area_count={varying_area_count}".format(**row)
        )
    return joined(parts)


def build_manifest(output_path):
    g03_by_family = read_g03_summary(G03_SUMMARY)
    codebook = read_codebook(CODEBOOK)
    panel_hash = sha256(HANDOVER_PANEL)
    output_hash = sha256(HANDOVER_OUTPUT)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for family in sorted(g03_by_family):
            rows = g03_by_family[family]
            features = [row["feature"] for row in rows]
            meta = FAMILY_METADATA[family]
            file_meta = file_metadata(meta["source_files"])
            evidence_level = "confirmed_from_local_assets_and_paper_data_section"
            if file_meta["missing"]:
                evidence_level = "partial_missing_expected_source_files"
            writer.writerow(
                {
                    "family": family,
                    "source_family_name": meta["source_family_name"],
                    "features": joined(features),
                    "feature_count": len(features),
                    "handover_source_panel": HANDOVER_PANEL,
                    "handover_source_panel_sha256": panel_hash,
                    "handover_output_file": HANDOVER_OUTPUT,
                    "handover_output_sha256": output_hash,
                    "join_key": "area_id = admin_code; lat/lon retained for spatial QA",
                    "value_rule": "G-03 handover asset uses latest nonmissing source-panel value by year/month for each area.",
                    "upstream_source_folder": meta["upstream_source_folder"],
                    "source_files": file_meta["paths"],
                    "source_file_rows": file_meta["rows"],
                    "source_file_sizes_bytes": file_meta["sizes"],
                    "source_file_mtimes": file_meta["mtimes"],
                    "source_file_sha256": file_meta["hashes"],
                    "provider_dataset_source": meta["provider_dataset_source"],
                    "provider_vintage_or_version": meta["provider_vintage_or_version"],
                    "unit_or_measure": meta["unit_or_measure"],
                    "aggregation_method": meta["aggregation_method"],
                    "codebook_evidence": codebook_evidence(features, codebook),
                    "paper_evidence": meta["paper_evidence"],
                    "stability_summary": stability_summary(rows),
                    "evidence_level": evidence_level,
                    "notes": meta["notes"],
                }
            )

    print("PASS: wrote {0} family rows to {1}".format(len(g03_by_family), output_path))


def main():
    try:
        build_manifest(parse_args().output)
    except (OSError, csv.Error, UnicodeError, KeyError, ValueError) as error:
        print("FAIL: {0}".format(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
