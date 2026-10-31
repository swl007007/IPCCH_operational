// Execute the upstream seasonal producer scripts' own formula functions on the pixel mock (task 10-30 CP2 evidence).
// usage: node run_js_reference.js <dataset.json> <out.json>
// Functions and constants are extracted verbatim from the vendored scripts (sha256 checked by the Python test) and run
// in a fresh context per script, so 01 and 02 are evaluated independently.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { ee, loadDataset, bandValues } = require('./ee_pixel_mock.js');

function block(src, start) {                 // text from start through the matching close of the first {...} or ;
  let depth = 0, i = start, seen = false;
  for (; i < src.length; i++) {
    const c = src[i];
    if (c === '{' || c === '[' || c === '(') { depth++; seen = true; }
    else if (c === '}' || c === ']' || c === ')') { depth--; if (depth === 0 && seen && c === '}') return src.slice(start, i + 1); }
    else if (c === ';' && depth === 0) return src.slice(start, i + 1);
  }
  throw new Error('unterminated block at ' + start);
}

function extract(src, names) {
  const parts = [];
  for (const name of names) {
    let at = src.indexOf('function ' + name + '(');
    if (at < 0) at = src.search(new RegExp('var ' + name + '\\s*='));
    if (at < 0) throw new Error('missing ' + name);
    parts.push(block(src, at));
  }
  return parts.join('\n\n');
}

const dir = __dirname;
const [datasetPath, outPath] = process.argv.slice(2);
const input = JSON.parse(fs.readFileSync(datasetPath, 'utf8'));
loadDataset(input.dataset);

const COMMON = ['pad2', 'yyyymm', 'ERA5_DAILY_ID', 'ERA5_ET0_BANDS', 'saturationVaporPressure', 'calculateDailyFao56Et0',
                'et0Template', 'monthlyEt0Image'];
const SCRIPTS = {
  '01': { file: '01_vi_prcp_et0_update.js',
          names: COMMON.concat(['VI_MAX_SUMMARY_QA', 'prepareViImage', 'PRECIP_SOURCES', 'precipitationTemplate',
                                'monthlyPrecipitationImage']) },
  '02': { file: '02_et0_patch32_update.js', names: COMMON },
};
const MONTHS = [[2026, 2], [2026, 3], [2026, 4]];
const out = { dataset: input.dataset, pixels: input.pixels, js: {} };

for (const [key, spec] of Object.entries(SCRIPTS)) {
  const src = fs.readFileSync(path.join(dir, spec.file), 'utf8');
  const ctx = vm.createContext({ ee, Math, print: () => {} });
  vm.runInContext(extract(src, spec.names) + '\nthis.exported = { ' + spec.names.join(', ') + ' };', ctx);
  const f = ctx.exported;
  const res = { daily_et0: [], monthly_et0: {}, extracted: spec.names };
  for (const img of ee.ImageCollection(f.ERA5_DAILY_ID).images) res.daily_et0.push(bandValues(f.calculateDailyFao56Et0(img)));
  for (const [y, m] of MONTHS) {
    const image = f.monthlyEt0Image(y, m);
    res.monthly_et0[y + '-' + m] = { band: image.bands.keys().next().value, values: bandValues(image),
                                     props: image.props };
  }
  if (key === '01') {
    res.vi = ee.ImageCollection('MODIS/061/MOD13C1').images.map(img => {
      const p = f.prepareViImage(img);
      return Object.fromEntries(Array.from(p.bands.keys()).map(b => [b, bandValues(p.select(b))]));
    });
    res.precipitation = {};
    for (const cfg of f.PRECIP_SOURCES) {
      for (const [y, m] of MONTHS) {
        const image = f.monthlyPrecipitationImage(cfg, y, m);
        res.precipitation[cfg.key + ' ' + y + '-' + m] = { band: image.bands.keys().next().value,
                                                          values: bandValues(image), props: image.props };
      }
    }
  }
  out.js[key] = res;
}
fs.writeFileSync(outPath, JSON.stringify(out));
