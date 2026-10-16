"""Window-probe comparator routing: pooled -> the cell's global unit; regional_ungated -> local_routed_provider
(local unit only where local_fit_ok), unmapped -> global; inconsistent plan records refused."""
import unittest

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


if __name__ == "__main__":
    unittest.main()
