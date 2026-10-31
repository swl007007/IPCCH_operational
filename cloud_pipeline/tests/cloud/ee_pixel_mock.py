"""Eager pixel-level stand-in for the Earth Engine operations the seasonal producer formulas use (task 10-30 CP2).

``tests/fixtures/ipcch_seasonal_producers/ee_pixel_mock.js`` implements the SAME semantics for the JavaScript client, and
``run_js_reference.js`` executes the upstream scripts' own functions on it (``js_reference.json``). Running the Python
port on this module with the same dataset is therefore a differential test of the two code paths: same arithmetic, same
masks, same daily-count completeness. Semantics (kept identical in both files):

* an image is an ordered map band -> (float64 values over N pixels, bool mask); binary operations take the left
  operand's band names, broadcast a single-band right operand (or a number) and AND the masks;
* ``toFloat`` rounds to float32; ``updateMask(m)`` keeps pixels where m is unmasked and nonzero;
* a collection ``sum`` adds unmasked values per band (all-masked pixel -> masked; an empty collection gives a
  band-less image, as EE's lazy ``Algorithms.If`` branch is never used); ``size`` counts images;
* ``filterDate`` keeps ``system:time_start`` in [start, end) (UTC days); ``Algorithms.If`` chooses eagerly.
"""

from __future__ import annotations

import calendar
import datetime as dt
import gzip
import json
import os

import numpy as np

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "ipcch_seasonal_producers")


def _n(x):
    return x.v if isinstance(x, Number) else x


class Number:
    def __init__(self, v):
        self.v = v

    def gt(self, o):
        return Number(1 if self.v > _n(o) else 0)

    def eq(self, o):
        return Number(1 if self.v == _n(o) else 0)

    def toInt(self):
        return Number(int(self.v))


class Date:
    def __init__(self, d):
        self.d = d

    @staticmethod
    def fromYMD(y, m, d):
        return Date(dt.datetime(y, m, d))

    def advance(self, n, unit):
        if unit == "day":
            return Date(self.d + dt.timedelta(days=n))
        months = n * (12 if unit == "year" else 1)
        o = self.d.year * 12 + self.d.month - 1 + months
        return Date(self.d.replace(year=o // 12, month=o % 12 + 1))

    def difference(self, other, unit):
        assert unit == "day"
        return Number((self.d - other.d).days)


class Image:
    def __init__(self, bands=None, props=None):
        self.bands = dict(bands or {})               # name -> (values, mask)
        self.props = dict(props or {})

    @staticmethod
    def constant(v):
        return Image({"constant": (np.array([float(_n(v))]), np.array([True]))})

    def _one(self):
        assert len(self.bands) == 1, list(self.bands)
        return next(iter(self.bands.values()))

    def _binary(self, other, fn):
        ov, om = (other._one() if isinstance(other, Image) else (np.array([float(_n(other))]), np.array([True])))
        out = {}
        for name, (v, m) in self.bands.items():
            out[name] = (fn(v, ov), m & om)
        return Image(out, self.props)

    def _unary(self, fn):
        return Image({k: (fn(v), m) for k, (v, m) in self.bands.items()}, self.props)

    def add(self, o):
        return self._binary(o, np.add)

    def subtract(self, o):
        return self._binary(o, np.subtract)

    def multiply(self, o):
        return self._binary(o, np.multiply)

    def divide(self, o):
        return self._binary(o, np.divide)

    def pow(self, o):
        return self._binary(o, np.power)

    def max(self, o):
        return self._binary(o, np.maximum)

    def lte(self, o):
        return self._binary(o, lambda a, b: (a <= b).astype(float))

    def gt(self, o):
        return self._binary(o, lambda a, b: (a > b).astype(float))

    def And(self, o):
        return self._binary(o, lambda a, b: ((a != 0) & (b != 0)).astype(float))

    def exp(self):
        return self._unary(np.exp)

    def sqrt(self):
        return self._unary(np.sqrt)

    def toFloat(self):
        return self._unary(lambda v: v.astype(np.float32).astype(np.float64))

    def select(self, names, new=None):
        names = [names] if isinstance(names, str) else list(names)
        new = names if new is None else list(new)
        return Image({n2: self.bands[n] for n, n2 in zip(names, new)}, self.props)

    def rename(self, name):
        v = self._one()
        return Image({name: v}, self.props)

    def updateMask(self, m):
        mv, mm = m._one()
        return Image({k: (v, msk & mm & (mv != 0)) for k, (v, msk) in self.bands.items()}, self.props)

    def set(self, props):
        return Image(self.bands, {**self.props, **{k: _n(v) for k, v in props.items()}})

    def copyProperties(self, source, names):
        return Image(self.bands, {**self.props, **{k: source.props[k] for k in names if k in source.props}})

    def get(self, name):
        return self.props[name]


class ImageCollection:
    datasets: dict = {}

    def __init__(self, images):
        self.images = list(ImageCollection.datasets[images]) if isinstance(images, str) else list(images)

    def filterDate(self, start, end):
        return ImageCollection([i for i in self.images if start.d <= i.props["system:time_start"] < end.d])

    def select(self, names):
        return ImageCollection([i.select(names) for i in self.images])

    def map(self, fn):
        return ImageCollection([fn(i) for i in self.images])

    def size(self):
        return Number(len(self.images))

    def first(self):
        return self.images[0]

    def sum(self):
        if not self.images:                      # lazy in EE: only an error if the empty sum is used
            return Image()
        out = {}
        for name in self.images[0].bands:
            vals = np.stack([np.where(i.bands[name][1], i.bands[name][0], 0.0) for i in self.images])
            masks = np.stack([i.bands[name][1] for i in self.images])
            out[name] = (vals.sum(axis=0), masks.any(axis=0))
        return Image(out)


class Algorithms:
    @staticmethod
    def If(cond, a, b):
        return a if _n(cond) else b


class MockEE:
    """The ``ee`` argument of the producer graph functions."""
    Number, Date, ImageCollection, Algorithms = Number, Date, ImageCollection, Algorithms

    @staticmethod
    def Image(x=None):
        return x if isinstance(x, Image) else Image.constant(x)


MockEE.Image.constant = Image.constant


def load_dataset(path=None):
    """The shared dataset (collections of daily/16-day images over N pixels) as mock collections."""
    with gzip.open(path or os.path.join(FIXTURES, "js_reference.json.gz"), "rt") as fh:
        ref = json.load(fh)
    ImageCollection.datasets = {
        cid: [Image({b: (np.array(v, float), np.ones(len(v), bool)) for b, v in img["bands"].items()},
                    {"system:time_start": dt.datetime.strptime(img["date"], "%Y-%m-%d")})
              for img in images] for cid, images in ref["dataset"].items()}
    return ref


def band_values(image):
    v, m = image._one()
    v = np.broadcast_to(v, m.shape) if v.shape != m.shape else v
    return [float(x) if ok else None for x, ok in zip(v, m)]


def make_dataset(seed=7, pixels=6):
    """Deterministic inputs: ERA5-Land daily (Feb 2026 complete, Mar 2026 missing its last day, no Apr 2026 images),
    CHIRPS/PERSIANN daily with negative values, MODIS 16-day composites with every SummaryQA/Pixel_1km case."""
    rng = np.random.default_rng(seed)

    def days(y, m, n):
        return [dt.date(y, m, d).isoformat() for d in range(1, n + 1)]
    era5 = []
    for date in days(2026, 2, 28) + days(2026, 3, 30):
        t = rng.uniform(270, 310, pixels)
        era5.append({"date": date, "bands": {
            "temperature_2m": t.tolist(), "temperature_2m_min": (t - rng.uniform(1, 12, pixels)).tolist(),
            "temperature_2m_max": (t + rng.uniform(1, 12, pixels)).tolist(),
            "dewpoint_temperature_2m": (t - rng.uniform(-2, 20, pixels)).tolist(),      # dewpoint > tmax: VPD floor
            "u_component_of_wind_10m": rng.normal(0, 4, pixels).tolist(), "v_component_of_wind_10m": [0.0] * pixels,
            "surface_pressure": rng.uniform(70000, 103000, pixels).tolist(),
            "surface_net_solar_radiation_sum": rng.uniform(0, 3e7, pixels).tolist(),
            "surface_net_thermal_radiation_sum": rng.uniform(-2e7, 0, pixels).tolist(),   # negative ET0 -> floor 0
            "total_precipitation_sum": rng.uniform(-0.001, 0.02, pixels).tolist()}})
    rain = {cid: [{"date": d, "bands": {"precipitation": rng.uniform(-1, 40, pixels).tolist()}}
                  for d in days(2026, 2, 28) + days(2026, 3, 31 if cid == "NOAA/PERSIANN-CDR" else 30)]
            for cid in ("UCSB-CHC/CHIRPS/V3/DAILY_RNL", "NOAA/PERSIANN-CDR")}
    modis = []
    for date in ("2026-01-01", "2026-01-17", "2026-02-02"):
        modis.append({"date": date, "bands": {"NDVI": rng.uniform(-2000, 9000, pixels).tolist(),
                                              "EVI": rng.uniform(-2000, 9000, pixels).tolist(),
                                              "Pixel_1km": [0, 1, 4, 9, 16, 3][:pixels],
                                              "SummaryQA": [0, 1, 2, 3, 0, 1][:pixels]}})
    return {"pixels": pixels, "dataset": {"ECMWF/ERA5_LAND/DAILY_AGGR": era5, **rain, "MODIS/061/MOD13C1": modis}}
