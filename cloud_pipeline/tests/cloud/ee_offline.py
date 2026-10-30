"""Offline Earth Engine client for tests: the algorithm signatures captured read-only from the EE API with
earthengine-api 1.7.36 (tests/fixtures/ipcch_climate/ee_algorithms_1.7.36.json.gz) let the real client build and
serialize computation graphs with no network or credentials."""
import gzip
import json
import os

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "ipcch_climate", "ee_algorithms_1.7.36.json.gz")


def offline_ee():
    import ee
    from ee import data as eedata
    if getattr(offline_ee, "_ready", False):
        return ee
    algorithms = json.load(gzip.open(FIXTURE, "rt"))
    eedata.getAlgorithms = lambda: algorithms
    ee.ApiFunction.initialize()
    for cls in (ee.Element, ee.Image, ee.Feature, ee.Collection, ee.ImageCollection, ee.FeatureCollection, ee.Filter,
                ee.Geometry, ee.List, ee.Number, ee.String, ee.Reducer, ee.Dictionary, ee.Date, ee.DateRange, ee.Kernel,
                ee.Join, ee.Algorithms):
        if hasattr(cls, "initialize"):
            cls.initialize()
    ee._InitializeGeneratedClasses()      # the rest of what ee.Initialize does after fetching the signatures
    ee._InitializeUnboundMethods()        # ee.Algorithms.If / IsEqual
    offline_ee._ready = True
    return ee
