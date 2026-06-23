# EVI Cloud Batch Extraction Pilot Design

Status: discussion-only design for a future phase.
Date: 2026-06-23

## Purpose

This spec captures a future technical direction for making the remote-sensing
pipeline cloud-native without relying on ArcPy. It is not an implementation
plan and does not request changes to the current operational pipeline.

The first pilot should cover EVI only. EVI is the smallest useful test because
the current workflow already follows a simple sequence:

1. Earth Engine exports monthly EVI GeoTIFFs to Google Cloud Storage.
2. ArcPy extracts zonal mean and standard deviation by IPCCH polygon.
3. The extraction writes `EVI_mean_extraction_results.csv` and
   `EVI_std_extraction_results.csv`.
4. The existing reshape utility converts those wide CSVs into
   `area_id`, `year`, `month` rows for downstream assembly.

The cloud pilot should preserve that output contract while replacing only the
ArcPy extraction step.

## Decisions

- Target architecture: pure cloud end-to-end for the EVI pilot.
- Processing platform: GCP Batch running a containerized extraction job.
- Data path: keep the raster-to-bucket-to-extract pattern.
- Rejected main path: Earth Engine direct polygon reduction, because prior
  attempts were too slow and less precise for this use case.
- Consistency target: business-acceptable agreement with ArcPy outputs, not
  exact cell-level or polygon-level replication.
- Pilot size: 1 to 3 EVI months.
- Scope boundary: this spec does not cover FLDAS, VIIRS, GOSIF-GPP, tabular
  features, or final model prediction deployment.

## Goals

The pilot should prove that a cloud job can:

- Read EVI GeoTIFFs from GCS.
- Read a versioned IPCCH polygon geometry asset from GCS.
- Compute zonal `mean` and `std` for each zone without ArcPy.
- Write the same wide CSV shape currently produced by
  `EVI/02_arcpy_extract_evi.py`.
- Produce a small validation report comparing cloud outputs to an existing
  ArcPy sample.
- Run repeatably from a container image and explicit job inputs.

## Non-Goals

- No code or pipeline changes are required in this discussion phase.
- No attempt to reproduce ArcPy internals exactly.
- No full historical EVI replay in the first pilot.
- No direct Earth Engine zonal-statistics export as the main workflow.
- No production scheduler, alerting system, or monthly release automation in
  the first pilot.
- No expansion to FLDAS, VIIRS, or GOSIF-GPP until the EVI pilot is reviewed.

## Proposed Architecture

The pilot should introduce a separate cloud extraction backend:

```text
Earth Engine EVI export
        |
        v
GCS GeoTIFF prefix
        |
        v
GCP Batch container job
        |
        +--> IPCCH polygon geometry from GCS
        +--> rasterio/GDAL + geopandas/shapely zonal extraction
        |
        v
GCS pilot output prefix
        |
        +--> EVI_mean_extraction_results.csv
        +--> EVI_std_extraction_results.csv
        +--> validation_report.json or .md
```

The container should use an open geospatial Python stack: GDAL, rasterio,
geopandas, shapely, pyproj, pandas, numpy, and either `rasterstats` or a small
project-owned zonal-statistics implementation built on rasterio masks. The
pilot should prefer clarity and inspectability over aggressive parallelism.

For 1 to 3 months, a single Batch task can process all selected rasters. If the
pilot later grows, the same design can become an array job with one task per
month and a final merge step.

## Data Inputs

### EVI Rasters

The job should consume EVI GeoTIFFs already exported to GCS by the current
Earth Engine script. Pilot inputs should be explicit, for example:

- bucket name.
- source prefix such as `MODIS_MOD13A3_Monthly/`.
- selected months such as `2019_01`, `2020_06`, or another small set chosen for
  comparison with existing ArcPy output.

The job should fail if a selected month has no matching raster or more than one
ambiguous match.

### Polygon Geometry

The cloud job needs a canonical polygon package in GCS. The current repository
contains the IPCCH shapefile package under `Outcome/ipcch_unified/spatial/`.
For cloud execution, the future implementation should stage an immutable copy
in GCS, preferably as a GeoPackage or a zipped shapefile package, with:

- a checksum.
- the geometry CRS.
- the zone id field used for EVI extraction.
- a versioned object path.

The current EVI config uses `zone_field = admin_code`, while existing remote
sensing contracts call the output id column `region_id`. The pilot should keep
the output column name `region_id` and fill it from the selected zone id field.
If downstream consumers require `area_id`, that mapping should remain in the
existing reshape step rather than being hidden inside extraction.

## Extraction Semantics

The cloud extraction should define semantics explicitly, because ArcPy defaults
are not portable:

- CRS: reproject polygons to the raster CRS before extracting. Do not resample
  the raster in the pilot unless validation shows that it is necessary.
- Nodata: ignore raster nodata and NaN values when computing statistics.
- Pixel inclusion: use center-based inclusion as the default
  (`all_touched = false`). If small or coastal polygons show unacceptable
  missingness, run `all_touched = true` as a sensitivity check, not as the
  default.
- Statistics: compute mean and standard deviation over valid pixels inside
  each zone.
- Empty zones: keep the zone row and write missing values for that month.
- Output sorting: sort rows by `region_id` and columns chronologically.
- Filename parsing: parse EVI month columns in the existing `YYYY_MM` format.

These choices may not match ArcPy exactly. That is acceptable for this pilot as
long as the validation report shows business-acceptable behavior.

## Output Contract

The pilot should write two wide CSVs that can be validated by the current
contract checks:

`EVI_mean_extraction_results.csv`

```text
region_id,YYYY_MM,...
```

`EVI_std_extraction_results.csv`

```text
region_id,YYYY_MM,...
```

For a 1-month pilot, each file should have one monthly value column. For a
3-month pilot, each file should have three monthly value columns. The files
should be compatible with `tools/reshape_remote_sensing_wide_to_long.py`
without changing that utility.

The job should write outputs to a pilot prefix separate from operational
outputs, for example:

```text
gs://<bucket>/ipcch-pilots/evi-cloud-extraction/<run_id>/
```

## Validation

The pilot should compare cloud outputs against an existing ArcPy sample for the
same month or months. The validation should be treated as a business review,
not a strict equality test.

Recommended validation checks:

- row count equals the expected number of zones.
- `region_id` values are unique and match the geometry asset.
- monthly columns are present and correctly named.
- cloud and ArcPy missing-rate differences are summarized overall and by
  country if country mapping is available.
- cloud and ArcPy distributions are compared with min, p5, p25, median, p75,
  p95, and max.
- Pearson and Spearman correlations are computed for matched non-missing
  zone-month pairs.
- largest absolute and relative differences are listed for manual review.
- the cloud wide CSVs pass the existing reshape smoke test.

Initial review thresholds should be advisory rather than hard gates:

- all expected zones are present.
- missing-rate difference is small or explainable.
- distribution shifts are small enough not to change downstream interpretation.
- correlations are high for matched zone-month pairs.
- outliers can be traced to CRS, nodata, pixel-inclusion, or geometry effects.

If the validation fails, the next technical discussion should inspect CRS,
pixel inclusion, nodata handling, raster scaling, and geometry validity before
changing the broader architecture.

## Error Handling

The future implementation should fail fast on:

- missing GCS objects.
- multiple rasters matching one selected month.
- missing or duplicated zone ids.
- unreadable geometry.
- unsupported raster CRS or transform.
- an output file with no monthly columns.

Partial outputs should be written to a temporary run prefix and promoted or
copied to the final pilot prefix only after all requested months complete.

The validation report should record:

- container image digest.
- Batch job id.
- input raster object names.
- geometry object name and checksum.
- extraction options such as `all_touched`.
- output object names.
- warning and failure counts.

## Resource Model

For the EVI pilot, keep the resource model simple:

- one Batch task.
- one container image.
- moderate CPU and memory.
- local scratch disk for raster downloads if direct GCS streaming is slow.

The implementation should test both direct GDAL GCS reads and explicit local
downloads. The pilot should use whichever is more reliable and easier to audit.
For small EVI samples, reliability is more important than minimizing local
scratch use.

## Security and Operations

The Batch service account should have least-privilege access:

- read access to the selected EVI raster prefix.
- read access to the geometry asset.
- write access to the pilot output prefix.
- permission to write logs.

The pilot should not embed secrets in the container image. Runtime settings
should come from Batch environment variables, command arguments, or a small GCS
config object.

## Testing Strategy for a Future Implementation

The later implementation plan should include:

- unit tests for EVI filename parsing and output table construction.
- unit tests for duplicate and missing zone id handling.
- a tiny synthetic raster and polygon fixture to test mean/std extraction.
- one cloud smoke run for a single EVI month.
- one comparison run against existing ArcPy output.
- a reshape smoke test using the generated mean and std CSVs.

These tests should be added only in the implementation phase, not as part of
this discussion-only spec.

## Risks

- Cloud extraction may disagree with ArcPy because of pixel inclusion,
  standard-deviation conventions, nodata handling, or CRS differences.
- GCS raster reads may be slower or less reliable than local downloads.
- The shapefile package may need conversion to a single cloud-friendly geometry
  artifact such as GeoPackage.
- Small coastal or narrow polygons may be sensitive to pixel inclusion rules.
- EVI success does not automatically prove FLDAS or VIIRS success, because
  FLDAS is multi-band and VIIRS currently has a mosaic step.

## Expansion Path

If the EVI pilot is accepted, expand in this order:

1. EVI target-month production dry run.
2. EVI historical subset with more months.
3. FLDAS pilot, treating each band as an output feature column and preserving
   the existing part-style wide CSV contract.
4. VIIRS pilot, replacing ArcPy mosaic with GDAL/rasterio merge or adjusting
   Earth Engine export so one monthly raster is already ready for extraction.
5. GOSIF-GPP pilot, after deciding whether its source downloads should be
   staged directly in GCS.

Each expansion should keep the same principle: preserve downstream CSV
contracts first, then consider broader pipeline simplification.

## Open Questions for the Next Technical Discussion

- Which 1 to 3 EVI months should be used for the pilot comparison?
- Where are the best existing ArcPy EVI outputs for those months?
- Should the cloud geometry asset use `admin_code`, `fid`, or `area_id` as the
  extraction zone id for the pilot?
- Should pilot outputs live in the same operator bucket as Earth Engine exports
  or in a separate controlled output bucket?
- Should validation compare only EVI mean/std, or should it also run the
  reshaped output through the monthly base-input assembly smoke path?

## Stopping Point

This spec is intentionally limited to technical discussion. The next phase
should review the open questions, then write an implementation plan only if the
pilot scope and validation standard are accepted.
