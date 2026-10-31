// WEATHER INTERMEDIATE INPUT UPDATE — VI_CURRENT / PRCP / ET0 (V3)
// Derived from the supplied Stage 2 optimized admin-level V3 export script.
// Run in the Earth Engine JavaScript Code Editor using your own compute project.
// This script creates export tasks; it does not share or delete Assets.
// PATCH32 is generated separately by 02_et0_patch32_update.js.

// 1. SETTINGS: set a writable destination in your own project.
var OUTPUT_ROOT = 'projects/YOUR_PROJECT_ID/assets/';
// A dated suffix prevents confusion with existing production tables.
// Downstream code must explicitly point to these new Asset IDs.
var OUTPUT_TAG = '_UPDATE_' + new Date().toISOString().slice(0, 10).replace(/-/g, '');

// Already-shared polygon partitions; no new permission change is performed.
var INPUT_ROOT = 'projects/han-sandbox-505315/assets/';
var STATIC_PREFIX = 'IPCCH_ADMIN_STATIC_CALENDAR_CROPFRAC_V1_G';
var ADMIN_ID = 'admin_code';
var TILE_SCALE = 8;
var MAX_PIXELS_PER_REGION = 1e9;
var VI_MAX_SUMMARY_QA = 1;

// Default: update the current VI year and the existing latest drought block.
// Keep the 2020-2026 block intact: existing downstream loaders expect it.
var VI_CURRENT_START_YEAR = 2026;
var VI_CURRENT_END_YEAR = 2026;
var DROUGHT_YEAR_CHUNKS = [[2020, 2026]];

var EXPORT_VI_CURRENT = true;
var EXPORT_DROUGHT_PRECIP = true;
var EXPORT_DROUGHT_ET0 = true;

function isInteger(value) {
  return typeof value === 'number' && isFinite(value) && Math.floor(value) === value;
}

if (OUTPUT_ROOT.indexOf('YOUR_PROJECT_ID') !== -1 ||
    !/^projects\/[^/]+\/assets\/(?:[^/]+\/)*$/.test(OUTPUT_ROOT)) {
  throw new Error('Set OUTPUT_ROOT to an existing writable Asset root/folder ending in /.');
}
if (OUTPUT_ROOT.indexOf(INPUT_ROOT) === 0) {
  throw new Error('Use your own output project; the shared input root is read-only.');
}
if (!isInteger(VI_CURRENT_START_YEAR) ||
    !isInteger(VI_CURRENT_END_YEAR) ||
    VI_CURRENT_START_YEAR > VI_CURRENT_END_YEAR) {
  throw new Error('Invalid VI year range.');
}
DROUGHT_YEAR_CHUNKS.forEach(function(chunk) {
  if (chunk.length !== 2 || !isInteger(chunk[0]) ||
      !isInteger(chunk[1]) || chunk[0] > chunk[1]) {
    throw new Error('Invalid drought year block.');
  }
});

// 2. MERGE THE SHARED FULL ADMIN POLYGONS.
// The supplied static-generation script retains original polygon geometry.
var inputAdmins = ee.FeatureCollection([]);
for (var group = 0; group < 25; group++) {
  inputAdmins = inputAdmins.merge(ee.FeatureCollection(
    INPUT_ROOT + STATIC_PREFIX + ('0' + group).slice(-2)
  ));
}
var admins = inputAdmins.map(function(feature) {
  feature = ee.Feature(feature);
  return ee.Feature(feature.geometry())
    .copyProperties(feature, [ADMIN_ID])
    .set('admin_area_km2', feature.geometry().area(1).divide(1e6));
});
print('Admin count (expected 6227):', admins.size());
print('Unique admin_code (expected 6227):', admins.aggregate_count_distinct(ADMIN_ID));

function pad2(number) {
  return number < 10 ? '0' + number : '' + number;
}


function yyyymm(year, month) {
  return '' + year + pad2(month);
}


// Return mean, spatial standard deviation, and valid-pixel count
// for every image band.
var ADMIN_STATS_REDUCER = ee.Reducer.mean()
  .combine({
    reducer2: ee.Reducer.stdDev(),
    sharedInputs: true
  })
  .combine({
    reducer2: ee.Reducer.count(),
    sharedInputs: true
  });


// EE table assets cannot contain null geometry.
// After zonal statistics have been calculated, replace each large polygon
// with a small representative point.
function compactGeometry(collection) {
  return ee.FeatureCollection(collection)
    .map(function(feature) {
      feature = ee.Feature(feature);

      return ee.Feature(
        feature.geometry().centroid(100),
        feature.toDictionary()
      );
    });
}


function reduceStackToAdminCollection(
  image,
  adminCollection,
  projection,
  scaleMeters
) {
  var reduced = ee.Image(image).reduceRegions({
    collection: ee.FeatureCollection(adminCollection),
    reducer: ADMIN_STATS_REDUCER,
    crs: projection,
    scale: scaleMeters,
    tileScale: TILE_SCALE,
    maxPixelsPerRegion: MAX_PIXELS_PER_REGION
  });

  return compactGeometry(reduced);
}


function reduceStackToAdmins(
  image,
  projection,
  scaleMeters
) {
  return reduceStackToAdminCollection(
    image,
    admins,
    projection,
    scaleMeters
  );
}


function exportTableAsset(collection, taskName, assetName) {
  var outputId = OUTPUT_ROOT + assetName + OUTPUT_TAG;
  print('OUTPUT:', outputId);
  Export.table.toAsset({
    collection: collection,
    description: taskName + OUTPUT_TAG,
    assetId: outputId
  });
}


function emptyImage() {
  return ee.Image(0).select([]);
}


// ============================================================================
// 3. VEGETATION: 0.05-DEGREE MODIS CMG
// ============================================================================

// Preserve the original V3 input-value handling: no additional VI scaling.
// Validate output units against the existing V3 tables before production use.

var VI_SOURCES = [
  {
    key: 'TERRA',
    id: 'MODIS/061/MOD13C1'
  },
  {
    key: 'AQUA',
    id: 'MODIS/061/MYD13C1'
  }
];


function prepareViImage(image) {
  image = ee.Image(image);

  var goodQa = image
    .select('SummaryQA')
    .lte(VI_MAX_SUMMARY_QA);

  var hasInputPixels = image
    .select('Pixel_1km')
    .gt(0);

  var valid = goodQa.and(hasInputPixels);

  return ee.Image(
    image
      .select(
        ['NDVI', 'EVI', 'Pixel_1km'],
        ['ndvi', 'evi', 'used_1km']
      )
      .updateMask(valid)
      .toFloat()
      .copyProperties(
        image,
        ['system:time_start', 'system:index']
      )
  );
}





// Create the 2003-2020 pixel-level slot climatology.



// Create one complete year of 16-day NDVI/EVI observations.
function buildViYearStack(
  sourceConfig,
  year
) {
  var start = ee.Date.fromYMD(year, 1, 1);
  var end = start.advance(1, 'year');

  var collection = ee.ImageCollection(sourceConfig.id)
    .filterDate(start, end)
    .sort('system:time_start')
    .map(prepareViImage);

  var stack = ee.Image(
    collection.iterate(
      function(image, accumulator) {
        image = ee.Image(image);
        accumulator = ee.Image(accumulator);

        var dateTag = ee.Date(
          image.get('system:time_start')
        ).format('YYYYMMdd');

        var renamed = image.rename(
          ee.List([
            ee.String('ndvi_').cat(dateTag),
            ee.String('evi_').cat(dateTag),
            ee.String('used1km_').cat(dateTag)
          ])
        );

        return accumulator.addBands(renamed);
      },
      emptyImage()
    )
  );

  var projection = ee.ImageCollection(sourceConfig.id)
    .first()
    .select('NDVI')
    .projection();

  var gridTotal = ee.Image.constant(1)
    .rename('cmg_grid_total')
    .setDefaultProjection(projection)
    .toFloat();

  return stack.addBands(gridTotal);
}


// Create eight VI baseline tasks:
// four Terra batches and four Aqua batches.



// Create one current-observation table per selected sensor and year.
function createViCurrentTasks() {
  for (
    var sourceIndex = 0;
    sourceIndex < VI_SOURCES.length;
    sourceIndex++
  ) {
    var sourceConfig =
      VI_SOURCES[sourceIndex];

    var projection =
      ee.ImageCollection(sourceConfig.id)
        .first()
        .select('NDVI')
        .projection();

    var scaleMeters =
      projection.nominalScale();

    for (
      var year = VI_CURRENT_START_YEAR;
      year <= VI_CURRENT_END_YEAR;
      year++
    ) {
      var stack =
        buildViYearStack(
          sourceConfig,
          year
        );

      var table = reduceStackToAdmins(
        stack,
        projection,
        scaleMeters
      )
      .map(function(feature) {
        return ee.Feature(feature).set({
          sensor: sourceConfig.key,
          product: sourceConfig.id,
          observation_year: year,
          temporal_resolution: '16_day',
          spatial_product: 'CMG_0P05_DEG'
        });
      });

      var taskName =
        'S2E3_VI_CURRENT_ADMIN_' +
        sourceConfig.key +
        '_Y' +
        year +
        '_CMG_V3';

      exportTableAsset(
        table,
        taskName,
        taskName
      );
    }
  }
}


// ============================================================================
// 4. DROUGHT INPUT A: MONTHLY PRECIPITATION
// ============================================================================

var PRECIP_SOURCES = [
  {
    key: 'CHIRPS',
    id: 'UCSB-CHC/CHIRPS/V3/DAILY_RNL',
    band: 'precipitation',
    multiplierToMm: 1
  },
  {
    key: 'PERSIANN',
    id: 'NOAA/PERSIANN-CDR',
    band: 'precipitation',
    multiplierToMm: 1
  },
  {
    key: 'ERA5LAND',
    id: 'ECMWF/ERA5_LAND/DAILY_AGGR',
    band: 'total_precipitation_sum',
    multiplierToMm: 1000
  }
];


function precipitationTemplate(
  sourceConfig
) {
  return ee.Image(
    ee.ImageCollection(sourceConfig.id)
      .select(sourceConfig.band)
      .first()
  )
  .multiply(0)
  .rename('prcp_mm')
  .updateMask(ee.Image.constant(0))
  .toFloat();
}


function monthlyPrecipitationImage(
  sourceConfig,
  year,
  month
) {
  var start =
    ee.Date.fromYMD(year, month, 1);

  var end =
    start.advance(1, 'month');

  var daily =
    ee.ImageCollection(sourceConfig.id)
      .filterDate(start, end)
      .select(sourceConfig.band)
      .map(function(image) {
        return ee.Image(image)
          .multiply(
            sourceConfig.multiplierToMm
          )
          .max(0)
          .rename('prcp_mm')
          .toFloat();
      });

  var daysPresent = daily.size();

  var daysExpected = end
    .difference(start, 'day')
    .toInt();

  var monthComplete =
    daysPresent.eq(daysExpected);

  var monthly = ee.Image(
    ee.Algorithms.If(
      daysPresent.gt(0),
      daily.sum(),
      precipitationTemplate(sourceConfig)
    )
  );

  // Mask the complete month if source coverage is incomplete.
  monthly = monthly.updateMask(
    ee.Image.constant(monthComplete)
  );

  return monthly
    .rename(
      'prcp_' + yyyymm(year, month)
    )
    .set({
      year: year,
      month: month,
      days_present: daysPresent,
      days_expected: daysExpected,
      month_complete: monthComplete
    });
}


function buildPrecipitationChunkStack(
  sourceConfig,
  startYear,
  endYear
) {
  var stack = emptyImage();

  for (
    var year = startYear;
    year <= endYear;
    year++
  ) {
    for (
      var month = 1;
      month <= 12;
      month++
    ) {
      stack = stack.addBands(
        monthlyPrecipitationImage(
          sourceConfig,
          year,
          month
        )
      );
    }
  }

  var projection =
    ee.ImageCollection(sourceConfig.id)
      .first()
      .select(sourceConfig.band)
      .projection();

  var gridTotal =
    ee.Image.constant(1)
      .rename('source_grid_total')
      .setDefaultProjection(projection)
      .toFloat();

  return stack.addBands(gridTotal);
}


function createDroughtPrecipitationTasks() {
  for (
    var sourceIndex = 0;
    sourceIndex < PRECIP_SOURCES.length;
    sourceIndex++
  ) {
    var sourceConfig =
      PRECIP_SOURCES[sourceIndex];

    var projection =
      ee.ImageCollection(sourceConfig.id)
        .first()
        .select(sourceConfig.band)
        .projection();

    var scaleMeters =
      projection.nominalScale();

    for (
      var chunkIndex = 0;
      chunkIndex < DROUGHT_YEAR_CHUNKS.length;
      chunkIndex++
    ) {
      var startYear =
        DROUGHT_YEAR_CHUNKS[chunkIndex][0];

      var endYear =
        DROUGHT_YEAR_CHUNKS[chunkIndex][1];

      var stack =
        buildPrecipitationChunkStack(
          sourceConfig,
          startYear,
          endYear
        );

      var table = reduceStackToAdmins(
        stack,
        projection,
        scaleMeters
      )
      .map(function(feature) {
        return ee.Feature(feature).set({
          source: sourceConfig.key,
          product: sourceConfig.id,
          chunk_start_year: startYear,
          chunk_end_year: endYear,
          temporal_resolution: 'monthly_total',
          unit: 'mm_month'
        });
      });

      var taskName =
        'S2C3_DROUGHT_ADMIN_PRCP_' +
        sourceConfig.key +
        '_Y' +
        startYear +
        '_' +
        endYear +
        '_V3';

      exportTableAsset(
        table,
        taskName,
        taskName
      );
    }
  }
}


// ============================================================================
// 5. DROUGHT INPUT B: ERA5-LAND FAO-56 PENMAN-MONTEITH ET0
// ============================================================================

var ERA5_DAILY_ID =
  'ECMWF/ERA5_LAND/DAILY_AGGR';

var ERA5_ET0_BANDS = [
  'temperature_2m',
  'temperature_2m_min',
  'temperature_2m_max',
  'dewpoint_temperature_2m',
  'u_component_of_wind_10m',
  'v_component_of_wind_10m',
  'surface_pressure',
  'surface_net_solar_radiation_sum',
  'surface_net_thermal_radiation_sum'
];


function saturationVaporPressure(tempC) {
  tempC = ee.Image(tempC);

  return tempC
    .multiply(17.27)
    .divide(
      tempC.add(237.3)
    )
    .exp()
    .multiply(0.6108);
}


function calculateDailyFao56Et0(image) {
  image = ee.Image(image);

  var tMeanC = image
    .select('temperature_2m')
    .subtract(273.15);

  var tMinC = image
    .select('temperature_2m_min')
    .subtract(273.15);

  var tMaxC = image
    .select('temperature_2m_max')
    .subtract(273.15);

  var dewpointC = image
    .select('dewpoint_temperature_2m')
    .subtract(273.15);

  var es = saturationVaporPressure(tMinC)
    .add(
      saturationVaporPressure(tMaxC)
    )
    .divide(2);

  var ea =
    saturationVaporPressure(dewpointC);

  var vaporPressureDeficit = es
    .subtract(ea)
    .max(0);

  var slope =
    saturationVaporPressure(tMeanC)
      .multiply(4098)
      .divide(
        tMeanC
          .add(237.3)
          .pow(2)
      );

  var pressureKpa = image
    .select('surface_pressure')
    .divide(1000);

  var psychrometric =
    pressureKpa.multiply(0.000665);

  var wind10m = image
    .select('u_component_of_wind_10m')
    .pow(2)
    .add(
      image
        .select('v_component_of_wind_10m')
        .pow(2)
    )
    .sqrt();

  // Convert wind speed from 10 m to 2 m.
  var wind2mFactor =
    4.87 /
    Math.log(67.8 * 10 - 5.42);

  var wind2m =
    wind10m.multiply(wind2mFactor);

  // ERA5 radiation:
  // J m-2 day-1 to MJ m-2 day-1.
  var netRadiation = image
    .select(
      'surface_net_solar_radiation_sum'
    )
    .add(
      image.select(
        'surface_net_thermal_radiation_sum'
      )
    )
    .divide(1e6);

  // Daily soil heat flux is assumed to be zero.
  var radiationTerm = slope
    .multiply(netRadiation)
    .multiply(0.408);

  var aerodynamicTerm = psychrometric
    .multiply(900)
    .divide(
      tMeanC.add(273)
    )
    .multiply(wind2m)
    .multiply(vaporPressureDeficit);

  var denominator = slope.add(
    psychrometric.multiply(
      wind2m
        .multiply(0.34)
        .add(1)
    )
  );

  var et0 = radiationTerm
    .add(aerodynamicTerm)
    .divide(denominator)
    .max(0)
    .rename('et0_mm_day')
    .toFloat();

  // Explicit ee.Image casting prevents the multiply-type error.
  return ee.Image(
    et0.copyProperties(
      image,
      [
        'system:time_start',
        'system:index'
      ]
    )
  );
}


function et0Template() {
  var firstEra5Image = ee.Image(
    ee.ImageCollection(ERA5_DAILY_ID)
      .select(ERA5_ET0_BANDS)
      .first()
  );

  return ee.Image(
    calculateDailyFao56Et0(
      firstEra5Image
    )
  )
  .multiply(0)
  .updateMask(
    ee.Image.constant(0)
  )
  .rename('et0_mm_day');
}


function monthlyEt0Image(
  year,
  month
) {
  var start =
    ee.Date.fromYMD(year, month, 1);

  var end =
    start.advance(1, 'month');

  var dailyRaw =
    ee.ImageCollection(ERA5_DAILY_ID)
      .filterDate(start, end)
      .select(ERA5_ET0_BANDS);

  var daysPresent =
    dailyRaw.size();

  var daysExpected = end
    .difference(start, 'day')
    .toInt();

  var monthComplete =
    daysPresent.eq(daysExpected);

  var dailyEt0 =
    dailyRaw.map(
      calculateDailyFao56Et0
    );

  var monthly = ee.Image(
    ee.Algorithms.If(
      daysPresent.gt(0),
      dailyEt0.sum(),
      et0Template()
    )
  );

  monthly = monthly.updateMask(
    ee.Image.constant(monthComplete)
  );

  return monthly
    .rename(
      'et0_' + yyyymm(year, month)
    )
    .set({
      year: year,
      month: month,
      days_present: daysPresent,
      days_expected: daysExpected,
      month_complete: monthComplete
    });
}


function buildEt0ChunkStack(
  startYear,
  endYear
) {
  var stack = emptyImage();

  for (
    var year = startYear;
    year <= endYear;
    year++
  ) {
    for (
      var month = 1;
      month <= 12;
      month++
    ) {
      stack = stack.addBands(
        monthlyEt0Image(
          year,
          month
        )
      );
    }
  }

  var projection =
    ee.ImageCollection(ERA5_DAILY_ID)
      .first()
      .select('temperature_2m')
      .projection();

  var gridTotal =
    ee.Image.constant(1)
      .rename('source_grid_total')
      .setDefaultProjection(projection)
      .toFloat();

  return stack.addBands(gridTotal);
}


function createDroughtEt0Tasks() {
  var projection =
    ee.ImageCollection(ERA5_DAILY_ID)
      .first()
      .select('temperature_2m')
      .projection();

  var scaleMeters =
    projection.nominalScale();

  for (
    var chunkIndex = 0;
    chunkIndex < DROUGHT_YEAR_CHUNKS.length;
    chunkIndex++
  ) {
    var startYear =
      DROUGHT_YEAR_CHUNKS[chunkIndex][0];

    var endYear =
      DROUGHT_YEAR_CHUNKS[chunkIndex][1];

    var stack =
      buildEt0ChunkStack(
        startYear,
        endYear
      );

    var table = reduceStackToAdmins(
      stack,
      projection,
      scaleMeters
    )
    .map(function(feature) {
      return ee.Feature(feature).set({
        source: 'ERA5LAND_FAO56_PM_ET0',
        product: ERA5_DAILY_ID,
        chunk_start_year: startYear,
        chunk_end_year: endYear,
        temporal_resolution: 'monthly_total',
        unit: 'mm_month',
        et0_method:
          'FAO56_PENMAN_MONTEITH_DAILY_THEN_MONTHLY_SUM'
      });
    });

    var taskName =
      'S2C3_DROUGHT_ADMIN_ET0_FAO56_Y' +
      startYear +
      '_' +
      endYear +
      '_V3';

    exportTableAsset(
      table,
      taskName,
      taskName
    );
  }
}



// 6. CREATE ONLY THE SELECTED UPDATE TASKS.
if (EXPORT_VI_CURRENT) createViCurrentTasks();
if (EXPORT_DROUGHT_PRECIP) createDroughtPrecipitationTasks();
if (EXPORT_DROUGHT_ET0) createDroughtEt0Tasks();
var taskCount =
  (EXPORT_VI_CURRENT ? VI_SOURCES.length * (VI_CURRENT_END_YEAR - VI_CURRENT_START_YEAR + 1) : 0) +
  (EXPORT_DROUGHT_PRECIP ? PRECIP_SOURCES.length * DROUGHT_YEAR_CHUNKS.length : 0) +
  (EXPORT_DROUGHT_ET0 ? DROUGHT_YEAR_CHUNKS.length : 0);
print('Expected export tasks (default 6):', taskCount);
print('Review and start the required tasks in the Tasks panel.');
print('PRCP/ET0 require complete source months; unavailable months stay masked.');
print('VI uses all currently published observations in each selected year.');
print('Run 02_et0_patch32_update.js separately for the matching ET0 patch update.');
