// Eager pixel-level stand-in for the Earth Engine JavaScript operations used by the seasonal producer formulas.
// Same semantics as tests/cloud/ee_pixel_mock.py (see its docstring); kept deliberately small and symmetric.
'use strict';

function num(x) { return (x instanceof EENumber) ? x.v : x; }

class EENumber {
  constructor(v) { this.v = v; }
  gt(o) { return new EENumber(this.v > num(o) ? 1 : 0); }
  eq(o) { return new EENumber(this.v === num(o) ? 1 : 0); }
  toInt() { return new EENumber(Math.trunc(this.v)); }
}

class EEDate {
  constructor(d) { this.d = d; }                       // UTC milliseconds
  static fromYMD(y, m, d) { return new EEDate(Date.UTC(y, m - 1, d)); }
  advance(n, unit) {
    const t = new Date(this.d);
    if (unit === 'day') return new EEDate(this.d + n * 86400000);
    const months = n * (unit === 'year' ? 12 : 1);
    return new EEDate(Date.UTC(t.getUTCFullYear(), t.getUTCMonth() + months, t.getUTCDate()));
  }
  difference(other, unit) {
    if (unit !== 'day') throw new Error('unit');
    return new EENumber(Math.round((this.d - other.d) / 86400000));
  }
}

function constantBand(v) { return [[num(v)], [true]]; }

class EEImage {
  constructor(bands, props) { this.bands = new Map(bands || []); this.props = Object.assign({}, props || {}); }
  static constant(v) { return new EEImage([['constant', constantBand(v)]]); }
  one() {
    if (this.bands.size !== 1) throw new Error('expected one band: ' + Array.from(this.bands.keys()));
    return this.bands.values().next().value;
  }
  binary(other, fn) {
    const [ov, om] = (other instanceof EEImage) ? other.one() : constantBand(other);
    const out = [];
    for (const [name, [v, m]] of this.bands) {
      const n = Math.max(v.length, ov.length, m.length, om.length);
      const at = (a, i) => a.length === 1 ? a[0] : a[i];
      const vals = [], mask = [];
      for (let i = 0; i < n; i++) { vals.push(fn(at(v, i), at(ov, i))); mask.push(at(m, i) && at(om, i)); }
      out.push([name, [vals, mask]]);
    }
    return new EEImage(out, this.props);
  }
  unary(fn) {
    const out = [];
    for (const [name, [v, m]] of this.bands) out.push([name, [v.map(fn), m.slice()]]);
    return new EEImage(out, this.props);
  }
  add(o) { return this.binary(o, (a, b) => a + b); }
  subtract(o) { return this.binary(o, (a, b) => a - b); }
  multiply(o) { return this.binary(o, (a, b) => a * b); }
  divide(o) { return this.binary(o, (a, b) => a / b); }
  pow(o) { return this.binary(o, (a, b) => Math.pow(a, b)); }
  max(o) { return this.binary(o, (a, b) => Math.max(a, b)); }
  lte(o) { return this.binary(o, (a, b) => (a <= b ? 1 : 0)); }
  gt(o) { return this.binary(o, (a, b) => (a > b ? 1 : 0)); }
  and(o) { return this.binary(o, (a, b) => ((a !== 0 && b !== 0) ? 1 : 0)); }
  exp() { return this.unary(Math.exp); }
  sqrt() { return this.unary(Math.sqrt); }
  toFloat() { return this.unary(Math.fround); }
  select(names, renamed) {
    names = (typeof names === 'string') ? [names] : names;
    renamed = renamed || names;
    return new EEImage(names.map((n, i) => [renamed[i], this.bands.get(n)]), this.props);
  }
  rename(name) { return new EEImage([[name, this.one()]], this.props); }
  updateMask(m) {
    const [mv, mm] = m.one();
    const out = [];
    for (const [name, [v, msk]] of this.bands) {
      const at = (a, i) => a.length === 1 ? a[0] : a[i];
      out.push([name, [v.slice(), msk.map((x, i) => x && at(mm, i) && at(mv, i) !== 0)]]);
    }
    return new EEImage(out, this.props);
  }
  set(props) {
    const p = Object.assign({}, this.props);
    for (const k of Object.keys(props)) p[k] = num(props[k]);
    return new EEImage(Array.from(this.bands), p);
  }
  copyProperties(source, names) {
    const p = Object.assign({}, this.props);
    for (const k of names) if (k in source.props) p[k] = source.props[k];
    return new EEImage(Array.from(this.bands), p);
  }
  get(name) { return this.props[name]; }
}

class EEImageCollection {
  constructor(images) {
    this.images = (typeof images === 'string') ? EEImageCollection.datasets[images].slice() : images.slice();
  }
  filterDate(start, end) {
    return new EEImageCollection(this.images.filter(i => start.d <= i.props['system:time_start'] && i.props['system:time_start'] < end.d));
  }
  select(names) { return new EEImageCollection(this.images.map(i => i.select(names))); }
  map(fn) { return new EEImageCollection(this.images.map(i => fn(i))); }
  size() { return new EENumber(this.images.length); }
  first() { return this.images[0]; }
  sum() {
    if (this.images.length === 0) return new EEImage([]);   // lazy in EE: only an error if the empty sum is used
    const out = [];
    for (const name of this.images[0].bands.keys()) {
      const n = this.images[0].bands.get(name)[0].length;
      const vals = new Array(n).fill(0), mask = new Array(n).fill(false);
      for (const img of this.images) {
        const [v, m] = img.bands.get(name);
        for (let i = 0; i < n; i++) if (m[i]) { vals[i] += v[i]; mask[i] = true; }
      }
      out.push([name, [vals, mask]]);
    }
    return new EEImage(out);
  }
}
EEImageCollection.datasets = {};

function Image(x) { return (x instanceof EEImage) ? x : EEImage.constant(x); }
Image.constant = EEImage.constant;

const ee = {
  Image, ImageCollection: (x) => new EEImageCollection(x), Number: (v) => new EENumber(v),
  Date: { fromYMD: EEDate.fromYMD },
  Algorithms: { If: (c, a, b) => (num(c) ? a : b) },
};

function loadDataset(dataset) {
  for (const [cid, images] of Object.entries(dataset)) {
    EEImageCollection.datasets[cid] = images.map(img => new EEImage(
      Object.entries(img.bands).map(([b, v]) => [b, [v.slice(), v.map(() => true)]]),
      { 'system:time_start': Date.parse(img.date + 'T00:00:00Z') }));
  }
}

function bandValues(image) {
  const [v, m] = image.one();
  const n = m.length;
  const out = [];
  for (let i = 0; i < n; i++) out.push(m[i] ? (v.length === 1 ? v[0] : v[i]) : null);
  return out;
}

module.exports = { ee, loadDataset, bandValues, EEImage };
