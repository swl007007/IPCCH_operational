"""Guarded fixture self-check of store_inventory.py (CP5 evidence code): HEAD generation + sha recorded from the pinned
generation, version counting, full content kept only for small tables with its sha verified, and refusal when HEAD
content differs from its recorded sha256 or the HEAD moved between listing and read."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import store_inventory as si  # noqa: E402


class Moved(Exception):
    pass


class Blob:
    def __init__(self, objects, bucket, name, generation=None):
        self.objects, self.bucket_name, self.name, self.generation = objects, bucket, name, generation

    def download_as_bytes(self, if_generation_match=None):
        data, gen = self.objects[(self.bucket_name, self.name)]
        if if_generation_match is not None and gen != if_generation_match:
            raise Moved(f"{self.name} generation {gen} != {if_generation_match}")
        return data


class Bucket:
    def __init__(self, objects, name):
        self.objects, self.name = objects, name

    def blob(self, name):
        return Blob(self.objects, self.name, name)


class Client:
    def __init__(self, objects, moved=None):
        self.objects, self.moved = objects, moved or {}

    def list_blobs(self, bucket, prefix):
        out = [Blob(self.objects, b, n, g) for (b, n), (_, g) in sorted(self.objects.items())
               if b == bucket and n.startswith(prefix)]
        for (b, n), g in self.moved.items():                 # HEAD rewritten after listing
            self.objects[(b, n)] = (self.objects[(b, n)][0], g)
        return out

    def bucket(self, name):
        return Bucket(self.objects, name)


def world(content_ok=True):
    root, objs = "r/ipcch-v2/real", {}
    def put(name, data, gen):
        objs[("bkt", f"{root}/{name}")] = (data, gen)
    ledger = b"month,status\n2026-01,unpublished\n"
    put("gpp_ledger/versions/1-a.csv", ledger, 11)
    put("gpp_ledger/HEAD.json", json.dumps({"version": 1, "content": f"gs://bkt/{root}/gpp_ledger/versions/1-a.csv",
        "sha256": hashlib.sha256(ledger if content_ok else b"other").hexdigest(), "rows": 1}).encode(), 12)
    big = b"a,b\n1,2\n"
    put("climate_spi03_monthly/versions/1-x.csv", big, 21)
    put("climate_spi03_monthly/versions/2-y.csv", big, 22)
    put("climate_spi03_monthly/HEAD.json", json.dumps({"version": 2, "content": f"gs://bkt/{root}/climate_spi03_monthly/"
        "versions/2-y.csv", "sha256": hashlib.sha256(big).hexdigest(), "rows": 1}).encode(), 23)
    return objs


def test_records_pinned_heads_versions_and_small_contents(tmp_path):
    objs = world()
    body = si.main("gs://bkt/r/ipcch-v2/real", str(tmp_path / "inv.json"), client=Client(objs))
    t = body["tables"]
    assert set(t) == {"gpp_ledger", "climate_spi03_monthly"}
    head = objs[("bkt", "r/ipcch-v2/real/climate_spi03_monthly/HEAD.json")][0]
    assert t["climate_spi03_monthly"]["head_generation"] == "23"
    assert t["climate_spi03_monthly"]["head_sha256"] == hashlib.sha256(head).hexdigest()
    assert t["climate_spi03_monthly"]["version_objects"] == 2 and "content_text" not in t["climate_spi03_monthly"]
    assert t["gpp_ledger"]["content_text"].startswith("month,status") and t["gpp_ledger"]["version"] == 1
    assert json.loads((tmp_path / "inv.json").read_text())["table_count"] == 2


def test_refuses_content_that_differs_from_the_head_sha(tmp_path):
    with pytest.raises(SystemExit, match="differs from its recorded sha256"):
        si.main("gs://bkt/r/ipcch-v2/real", str(tmp_path / "inv.json"), client=Client(world(content_ok=False)))


def test_refuses_a_head_that_moved_after_listing(tmp_path):
    objs = world()
    with pytest.raises(Moved):
        si.main("gs://bkt/r/ipcch-v2/real", str(tmp_path / "inv.json"),
                client=Client(objs, moved={("bkt", "r/ipcch-v2/real/gpp_ledger/HEAD.json"): 99}))
