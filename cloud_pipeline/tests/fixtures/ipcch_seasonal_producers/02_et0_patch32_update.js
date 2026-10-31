// ============================================================================
// ERA5-LAND ET0 PATCH32 UPDATE — ORIGINAL 30 KM BUFFER METHOD
// ============================================================================


// ============================================================================
// 1. SETTINGS
// ============================================================================

// Use the existing shared full-polygon partitions as the geometry input.
var INPUT_ROOT = 'projects/han-sandbox-505315/assets/';
var STATIC_PREFIX = 'IPCCH_ADMIN_STATIC_CALENDAR_CROPFRAC_V1_G';

// Set the same destination and tag used by 01_vi_prcp_et0_update.js.
var OUTPUT_ROOT = 'projects/YOUR_PROJECT_ID/assets/';
var OUTPUT_TAG = '_UPDATE_' + new Date().toISOString().slice(0, 10).replace(/-/g, '');

if (OUTPUT_ROOT.indexOf('YOUR_PROJECT_ID') !== -1 ||
    !/^projects\/[^/]+\/assets\/(?:[^/]+\/)*$/.test(OUTPUT_ROOT)) {
  throw new Error('Set OUTPUT_ROOT to an existing writable Asset root/folder ending in /.');
}
if (OUTPUT_ROOT.indexOf(INPUT_ROOT) === 0) {
  throw new Error('Use your own output project; shared inputs are read-only.');
}

var ADMIN_ID = 'admin_code';

var ERA5_DAILY_ID =
  'ECMWF/ERA5_LAND/DAILY_AGGR';

// A 30 km buffer is used only for the 32 missing admins.
var FALLBACK_BUFFER_METERS = 30000;

var TILE_SCALE = 8;
var MAX_PIXELS_PER_REGION = 1e9;

// Latest block only for routine updates. For historical reconstruction use:
// [[1990,1995],[1996,2001],[2002,2007],[2008,2013],[2014,2019],[2020,2026]]
var YEAR_CHUNKS = [[2020, 2026]];


// ============================================================================
// 2. TARGET ADMIN CODES
// ============================================================================

var TARGET_CODES_NUMBER = [
  101183,
  101191,
  101194,
  101275,

  2107,
  2108,

  3422,
  3423,
  3427,
  3428,
  3429,
  3430,
  3431,
  3432,
  3433,

  4073,

  4267,
  4269,
  4270,
  4353,

  4783,
  4784,
  4785,
  4786,
  4787,

  76,
  77,

  983,
  984,
  985,
  986,
  987
];

var TARGET_CODES_STRING =
  TARGET_CODES_NUMBER.map(
    function(value) {
      return String(value);
    }
  );


// ============================================================================
// 3. LOAD ONLY THE 32 TARGET ADMINS
// ============================================================================

var allAdmins = ee.FeatureCollection([]);
for (var group = 0; group < 25; group++) {
  allAdmins = allAdmins.merge(ee.FeatureCollection(
    INPUT_ROOT + STATIC_PREFIX + ('0' + group).slice(-2)
  ));
}

// Handle admin_code stored as a number.
var targetAdminsNumeric =
  allAdmins.filter(
    ee.Filter.inList(
      ADMIN_ID,
      TARGET_CODES_NUMBER
    )
  );

// Handle admin_code stored as a string.
var targetAdminsString =
  allAdmins.filter(
    ee.Filter.inList(
      ADMIN_ID,
      TARGET_CODES_STRING
    )
  );

var targetAdmins =
  targetAdminsNumeric
    .merge(targetAdminsString)
    .distinct([ADMIN_ID]);


// Add the 30 km buffer before reduction.
var bufferedTargetAdmins =
  targetAdmins.map(
    function(feature) {
      feature = ee.Feature(feature);

      var originalAreaKm2 =
        feature
          .geometry()
          .area(100)
          .divide(1e6);

      var bufferedGeometry =
        feature
          .geometry()
          .buffer(
            FALLBACK_BUFFER_METERS,
            100
          );

      return ee.Feature(
        bufferedGeometry
      )
        .copyProperties(
          feature,
          [ADMIN_ID]
        )
        .set({
          original_admin_area_km2:
            originalAreaKm2,

          et0_spatial_fallback:
            1,

          fallback_method:
            'BUFFERED_ERA5LAND_MEAN',

          fallback_buffer_m:
            FALLBACK_BUFFER_METERS
        });
    }
  );


// This is the only server-side check performed immediately.
// It involves just 32 features and should be fast.
print(
  'Expected target admin count',
  32
);

print(
  'Selected target admin count',
  targetAdmins.size()
);


// ============================================================================
// 4. HELPERS
// ============================================================================

function pad2(number) {
  return number < 10
    ? '0' + number
    : '' + number;
}


function yyyymm(year, month) {
  return (
    '' +
    year +
    pad2(month)
  );
}


function emptyImage() {
  return ee.Image(0).select([]);
}


// ============================================================================
// 5. ERA5-LAND INPUT BANDS
// ============================================================================

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


var era5FirstImage = ee.Image(
  ee.ImageCollection(ERA5_DAILY_ID)
    .first()
);

var ERA5_PROJECTION =
  era5FirstImage
    .select('temperature_2m')
    .projection();

var ERA5_SCALE =
  ERA5_PROJECTION.nominalScale();


// ============================================================================
// 6. FAO-56 PENMAN-MONTEITH ET0
// ============================================================================

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

  var es =
    saturationVaporPressure(tMinC)
      .add(
        saturationVaporPressure(tMaxC)
      )
      .divide(2);

  var ea =
    saturationVaporPressure(dewpointC);

  var vaporPressureDeficit =
    es
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

  var pressureKpa =
    image
      .select('surface_pressure')
      .divide(1000);

  var psychrometric =
    pressureKpa.multiply(0.000665);

  var wind10m =
    image
      .select('u_component_of_wind_10m')
      .pow(2)
      .add(
        image
          .select('v_component_of_wind_10m')
          .pow(2)
      )
      .sqrt();

  var wind2mFactor =
    4.87 /
    Math.log(
      67.8 * 10 - 5.42
    );

  var wind2m =
    wind10m.multiply(
      wind2mFactor
    );

  // ERA5 radiation:
  // J m-2 day-1 → MJ m-2 day-1.
  var netRadiation =
    image
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
  var radiationTerm =
    slope
      .multiply(netRadiation)
      .multiply(0.408);

  var aerodynamicTerm =
    psychrometric
      .multiply(900)
      .divide(
        tMeanC.add(273)
      )
      .multiply(wind2m)
      .multiply(
        vaporPressureDeficit
      );

  var denominator =
    slope.add(
      psychrometric.multiply(
        wind2m
          .multiply(0.34)
          .add(1)
      )
    );

  var et0 =
    radiationTerm
      .add(aerodynamicTerm)
      .divide(denominator)
      .max(0)
      .rename('et0_mm_day')
      .toFloat();

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


// ============================================================================
// 7. EMPTY MONTH TEMPLATE
// ============================================================================

function et0Template() {
  var firstEra5Image =
    ee.Image(
      ee.ImageCollection(
        ERA5_DAILY_ID
      )
        .select(
          ERA5_ET0_BANDS
        )
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


// ============================================================================
// 8. MONTHLY ET0
// ============================================================================

function monthlyEt0Image(
  year,
  month
) {
  var start =
    ee.Date.fromYMD(
      year,
      month,
      1
    );

  var end =
    start.advance(
      1,
      'month'
    );

  var dailyRaw =
    ee.ImageCollection(
      ERA5_DAILY_ID
    )
      .filterDate(
        start,
        end
      )
      .select(
        ERA5_ET0_BANDS
      );

  var daysPresent =
    dailyRaw.size();

  var daysExpected =
    end
      .difference(
        start,
        'day'
      )
      .toInt();

  var monthComplete =
    daysPresent.eq(
      daysExpected
    );

  var dailyEt0 =
    dailyRaw.map(
      calculateDailyFao56Et0
    );

  var monthly =
    ee.Image(
      ee.Algorithms.If(
        daysPresent.gt(0),
        dailyEt0.sum(),
        et0Template()
      )
    );

  // Keep future/incomplete months masked.
  monthly =
    monthly.updateMask(
      ee.Image.constant(
        monthComplete
      )
    );

  return monthly
    .rename(
      'et0_' +
      yyyymm(year, month)
    )
    .toFloat();
}


// ============================================================================
// 9. BUILD ONE YEAR-CHUNK STACK
// ============================================================================

function buildEt0ChunkStack(
  startYear,
  endYear
) {
  var stack =
    emptyImage();

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
      stack =
        stack.addBands(
          monthlyEt0Image(
            year,
            month
          )
        );
    }
  }

  // Retain the same grid QA field as the original V3 tables.
  var sourceGrid =
    ee.Image.constant(1)
      .rename(
        'source_grid_total'
      )
      .setDefaultProjection(
        ERA5_PROJECTION
      )
      .toFloat();

  return stack.addBands(
    sourceGrid
  );
}


// ============================================================================
// 10. SAME OUTPUT REDUCER AS ORIGINAL V3
// ============================================================================

var ADMIN_STATS_REDUCER =
  ee.Reducer.mean()
    .combine({
      reducer2:
        ee.Reducer.stdDev(),

      sharedInputs:
        true
    })
    .combine({
      reducer2:
        ee.Reducer.count(),

      sharedInputs:
        true
    });


// Reduce the complete chunk in one operation.
function reduceChunk(
  stack,
  startYear,
  endYear
) {
  var reduced =
    ee.Image(stack)
      .reduceRegions({
        collection:
          bufferedTargetAdmins,

        reducer:
          ADMIN_STATS_REDUCER,

        crs:
          ERA5_PROJECTION,

        scale:
          ERA5_SCALE,

        tileScale:
          TILE_SCALE,

        maxPixelsPerRegion:
          MAX_PIXELS_PER_REGION
      });

  // Replace buffered polygons with compact point geometries.
  return reduced.map(
    function(feature) {
      feature =
        ee.Feature(feature);

      return ee.Feature(
        feature
          .geometry()
          .centroid(100),

        feature.toDictionary()
      )
        .set({
          source:
            'ERA5LAND_FAO56_PM_ET0',

          product:
            ERA5_DAILY_ID,

          chunk_start_year:
            startYear,

          chunk_end_year:
            endYear,

          temporal_resolution:
            'monthly_total',

          unit:
            'mm_month',

          et0_method:
            'FAO56_PENMAN_MONTEITH_DAILY_THEN_MONTHLY_SUM',

          et0_spatial_fallback:
            1,

          fallback_method:
            'BUFFERED_ERA5LAND_MEAN',

          fallback_buffer_m:
            FALLBACK_BUFFER_METERS,

          patch_version:
            'V2'
        });
    }
  );
}


// ============================================================================
// 11. VALIDATE TARGET COUNT, THEN CREATE THE SELECTED PATCH TASKS
// ============================================================================

// Asset graph construction does not prove successful computation.
// Create export tasks only after confirming the expected 32 distinct targets.
ee.Dictionary({
  rows: targetAdmins.size(),
  unique_codes: targetAdmins.aggregate_count_distinct(ADMIN_ID)
}).evaluate(function(result, error) {
  if (error || !result || result.rows !== 32 || result.unique_codes !== 32) {
    print('STOP: target selection must have exactly 32 rows and distinct codes.', error || result);
    return;
  }
for (
  var chunkIndex = 0;
  chunkIndex < YEAR_CHUNKS.length;
  chunkIndex++
) {
  var startYear =
    YEAR_CHUNKS[chunkIndex][0];

  var endYear =
    YEAR_CHUNKS[chunkIndex][1];

  var stack =
    buildEt0ChunkStack(
      startYear,
      endYear
    );

  var patchTable =
    reduceChunk(
      stack,
      startYear,
      endYear
    );

  var taskName =
    'S2C3_ET0_PATCH32_Y' +
    startYear +
    '_' +
    endYear +
    '_V2';

  Export.table.toAsset({
    collection:
      patchTable,

    description:
      taskName + OUTPUT_TAG,

    assetId:
      OUTPUT_ROOT +
      taskName + OUTPUT_TAG
  });
}


print('PATCH32 export tasks created:', YEAR_CHUNKS.length);
print('Output folder:', OUTPUT_ROOT);
print('Output tag:', OUTPUT_TAG);
print('Review and start tasks in the Tasks panel. Missing values can remain.');
});
