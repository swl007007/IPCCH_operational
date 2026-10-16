"""Window-probe comparator routing: pooled -> the cell's global unit; regional_ungated -> local_routed_provider
(local unit only where local_fit_ok), unmapped -> global; inconsistent plan records refused."""
import hashlib
import json
import os
import tempfile
import unittest

import numpy as np

from research_cloud.packages import window_probe
from research_cloud.packages.common import PackageError
from research_cloud.packages.window_probe import routing_for

G, L1, L2 = "g" * 64, "a" * 64, "b" * 64


def cell(regions):
    return {"H": 1, "U": "2023-09", "regions": regions}


def region(name, ok, local, provider):
    return {"region": name, "local_fit_ok": ok, "global_identity": G, "local_identity": local, "local_routed_provider": provider}


class ComparatorRouting(unittest.TestCase):
    def test_pooled_and_ungated_routes(self):
        c = cell([region("r0", "True", L1, L1), region("r1", "False", L2, G)])
        gid, pooled = routing_for(c, "base_global")
        self.assertEqual((gid, set(pooled.values())), (G, {(G, "pooled_global")}))
        _, local = routing_for(c, "base_local")
        self.assertEqual(local, {"": (G, "unmapped_global"), "r0": (L1, "local_routed"), "r1": (G, "local_fit_not_ok_global")})

    def test_inconsistent_plan_records_are_refused(self):
        for regions in ([region("r0", "True", L1, G)],                       # ok but routed to the global unit
                        [region("r0", "False", L1, L1)],                     # not ok but routed to the local unit
                        [region("r0", "True", L1, L1), dict(region("r1", "True", L2, L2), global_identity="h" * 64)]):
            with self.assertRaises(PackageError):
                routing_for(cell(regions), "base_local")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


class InputProvenanceGate(unittest.TestCase):
    """P6 inputs must match the probe's own start.json / source-hashes.json records before they are read."""

    def setUp(self):
        self.probe, self.p6 = tempfile.mkdtemp(), tempfile.mkdtemp()
        for d in ("prepared", "stage1"):
            os.makedirs(f"{self.p6}/{d}")
        open(f"{self.p6}/prepared/keys_h01.csv.gz", "wb").write(b"keys")
        np.save(f"{self.p6}/prepared/X_rich561_h01.npy", np.zeros((1, 2)))
        open(f"{self.p6}/prepared/feature_order.csv", "w").write("name\na\nb\n")
        open(f"{self.p6}/stage1/frozen_map_h01.csv", "w").write("admin_code,node_id\n1,r0\n")
        prepared = {"keys_h01.csv.gz": sha(f"{self.p6}/prepared/keys_h01.csv.gz"),
                    "X_rich561_h01.npy": sha(f"{self.p6}/prepared/X_rich561_h01.npy"),
                    "feature_order.csv": sha(f"{self.p6}/prepared/feature_order.csv")}
        records = {"plan.json": {"selected": [{"H": 1, "U": "2023-09", "target_ord": 24284, "origin": 24283, "regions": []}]},
                   "start.json": {"prepared": {"manifest": {"ledger": {"artifacts_sha256": prepared}}}},
                   "source-hashes.json": {"IPCCHGeoXGBExperiment\\runs\\p6-formal-20261004b\\stage1\\frozen_map_h01.csv":
                                          sha(f"{self.p6}/stage1/frozen_map_h01.csv")}}
        for name, body in records.items():
            json.dump(body, open(f"{self.probe}/{name}", "w"))
        json.dump({n: sha(f"{self.probe}/{n}") for n in records}, open(f"{self.probe}/artifact-hashes.json", "w"))

    def build(self):
        out = os.path.join(tempfile.mkdtemp(), "pkg")
        try:
            window_probe.build(out, probe_dir=self.probe, p6_root=self.p6, p6_source_code=self.p6,
                               p6_members_manifest=f"{self.p6}/none.json", version={}, lead=1, registered_arm="pooled",
                               code_identity={}, original_runtime={}, linux_runtime={})
        finally:
            self.assertFalse(os.path.exists(out), "no package may be started before provenance passes")

    def test_tampered_matrix_is_rejected_before_reading(self):
        np.save(f"{self.p6}/prepared/X_rich561_h01.npy", np.ones((1, 2)))
        with self.assertRaisesRegex(PackageError, "X_rich561_h01.npy does not match the probe's start.json"):
            self.build()

    def test_tampered_frozen_map_is_rejected(self):
        open(f"{self.p6}/stage1/frozen_map_h01.csv", "a").write("2,r1\n")
        with self.assertRaisesRegex(PackageError, "frozen_map_h01.csv does not match the probe's source-hashes.json"):
            self.build()

    def test_tampered_probe_record_is_rejected(self):
        json.dump({"prepared": {}}, open(f"{self.probe}/start.json", "w"))
        with self.assertRaisesRegex(PackageError, "start.json does not match artifact-hashes.json"):
            self.build()


if __name__ == "__main__":
    unittest.main()
