# Cloud Test Fixtures

The cloud test suite uses generated miniature fixtures rather than large
production rasters or geometry files.

Required EVI fixture expectations:

- A tiny single-band raster with deterministic EVI pixel values.
- A tiny geometry table or file with canonical `area_id` values.
- Rasterio zonal statistics must use `all_touched=false`, meaning only pixels
  whose centers fall inside a geometry are included.
- At least one geometry should have no intersecting raster pixels so empty-zone
  preservation can be tested.
- `region_id` in EVI wide outputs must equal canonical `area_id`.
- Long EVI outputs must contain exactly the selected feature month and one row
  per scaffold area.

Tests may create these fixtures dynamically in `tmp_path` to avoid committing
binary raster artifacts.
