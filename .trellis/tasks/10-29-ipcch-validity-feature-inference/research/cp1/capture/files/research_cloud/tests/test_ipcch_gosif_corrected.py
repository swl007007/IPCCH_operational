"""Corrected-input formal refit of the tuned aggregated-ACLED arm (task 10-27-ipcch-gosif2025-retrain): the explicit
``corrected_input`` recipe contract (structure), its pre-fit gate (pinned input bytes, eleven preserved equivalence
digests, two re-pinned feature digests, per-column digests of every unchanged feature column) and the truthful caveat
and identity of the formal job. Synthetic fixtures only (no real data, no network).

  IPCCH_AE_SRC=$W/sources/Food_Crisis_Cluster/IPCCHAlphaEarthExperiment ~/.venvs/ipcch-validity-idp/bin/python \
      -m unittest research_cloud.tests.test_ipcch_gosif_corrected
"""
import copy
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

from research_cloud.tests import test_ipcch_acledagg_hpt as th
from research_cloud.training import ipcch_validity_features as vf
from research_cloud.training import ipcch_validity_pooled as vp

HPT = vp.HPT_ARM
REF100 = {**vp.HPT_REFERENCE, "q3_n_estimators": 100, "other_n_estimators": 100}
WINNER = {"role": "reference", "trial_id": "reference", "params": REF100}


def fixture_gpp(order):
    """13 ordinary fixture columns standing in for the GPP_mean-derived columns (no history, ACLED or IDP column)."""
    skip = set(vf.HISTORY_FEATURES) | set(vf.ACLED_AGG_FEATURES) | set(vf.IDP_LOCAL_FEATURES)
    return tuple([c for c in order if c not in skip][:13])


class Names(unittest.TestCase):
    def test_gpp_columns_are_the_compact_gpp_mean_names(self):
        cp, _, _ = vf.ae_modules()
        want = [*cp.ordinary_names("GPP_mean"), *cp.z_names("GPP_mean"), *cp.stress_names("GPP_mean__vegetation_stress")]
        self.assertEqual(list(vp.GPP_INPUT_FEATURES), want)
        self.assertEqual(len(vp.GPP_INPUT_FEATURES), 13)
        self.assertNotIn("GPP_std", " ".join(cp.INTERIM_SOURCES))          # GPP_std is delivered but is not a model input
        self.assertEqual(set(vp.CORRECTED_PRESERVED) | set(vp.CORRECTED_REPINNED), set(vp.EQUIVALENCE_KEYS))
        self.assertEqual(len(vp.CORRECTED_PRESERVED), 11)


class Corrected(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.jobs = th.Jobs()
        self.jobs.tmp = self.tmp

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build(self, fx):
        """(formal recipe with a corrected_input block, inputs, corrected fixture, gpp names); call inside th.patched(fx)."""
        gpp = fixture_gpp(fx.order)
        inputs, fsha, isha = self.jobs.formal_inputs(fx, WINNER)
        for role in ("interim", "raw_panel"):                       # dummy role files: the fake build ignores them
            p = os.path.join(self.tmp, f"{role}.csv")
            with open(p, "w") as f:
                f.write(f"{role} corrected\n")
            inputs[role] = p
        cfg = self.jobs.formal_config(fx, inputs, fsha, isha, WINNER)
        report = os.path.join(self.tmp, "report-regions.csv")       # report-only map: six regions (not the pairing map)
        pd.DataFrame({"area_id": np.arange(1, 9), "region": [a % 6 for a in range(1, 9)]}).to_csv(report, index=False)
        inputs[vp.REPORT_ROLE] = report
        new = copy.copy(fx)
        new.X = np.array(fx.X, copy=True)
        idx = [fx.order.index(c) for c in gpp]
        new.X[:, idx] = new.X[:, idx] * 2.0 + 1.0                  # the corrected input changes only these columns
        d = new.arm()
        got = vp.equivalence_digests(d, vp.plan_contexts(d), len(fx.order))
        names = [c for c in fx.order if c not in gpp]
        cols, mask = vp.non_acled_digests(fx.X, fx.order, names)     # reference: the original build's unchanged columns
        pins = {r: th.sha(p) for r, p in inputs.items()}
        pins["region_mapping"] = vp.REGION_MAPPING_SHA256
        cfg["corrected_input"] = {
            "kind": vp.CORRECTED_INPUT_KIND, "data_version": "test-gpp-v3", "replaced_role": "interim", "inputs": pins,
            "original_inputs": {"interim": "0" * 64}, "changed_columns": list(gpp),
            "corrected": {k: got[k] for k in vp.CORRECTED_REPINNED},
            "unchanged_columns": {"order_sha256": vf.list_sha256(names), "nan_mask_sha256": mask, "values": cols},
            "original_run": {"run_id": "r" * 32, "recipe_sha256": "a" * 64, "journal_sha256": "b" * 64},
            "relation": "test relation",
            "report": {"role": vp.REPORT_ROLE, "regions": {str(k): f"Region {k}" for k in range(6)}, "somalia_iso2": "SO"}}
        return cfg, inputs, new, gpp

    def run_formal(self, fx_build, cfg, inputs, gpp, name):
        with mock.patch.object(vp, "GPP_INPUT_FEATURES", gpp), self.jobs.frozen_sha(inputs["region_mapping"]):
            return self.jobs.run_job(fx_build, cfg, {}, inputs, name=name)

    def test_contract_structure_and_refusals(self):
        fx = th.Fixture(6)
        with th.patched(fx):
            cfg, inputs, new, gpp = self.build(fx)
        with th.patched(fx), mock.patch.object(vp, "GPP_INPUT_FEATURES", gpp):
            vp.check_config(cfg, 6, HPT)
            ci = cfg["corrected_input"]
            cases = [("extra key", {**ci, "extra": 1}), ("kind", {**ci, "kind": "other"}),
                     ("role", {**ci, "replaced_role": "climate_monthly"}), ("no version", {**ci, "data_version": " "}),
                     ("same interim", {**ci, "original_inputs": {"interim": ci["inputs"]["interim"]}}),
                     ("two replaced", {**ci, "original_inputs": {"interim": "0" * 64, "raw_panel": "1" * 64}}),
                     ("missing role", {**ci, "inputs": {k: v for k, v in ci["inputs"].items() if k != "raw_panel"}}),
                     ("freeze pin", {**ci, "inputs": {**ci["inputs"], "freeze": "3" * 64}}),
                     ("comparison pin", {**ci, "inputs": {**ci["inputs"], "baseline_predictions": "4" * 64}}),
                     ("columns", {**ci, "changed_columns": list(gpp[:-1])}),
                     ("repinned keys", {**ci, "corrected": {**ci["corrected"], "fit_keys_sha256": "5" * 64}}),
                     ("short unchanged", {**ci, "unchanged_columns": {**ci["unchanged_columns"], "values": dict(list(ci["unchanged_columns"]["values"].items())[1:])}}),
                     ("original run", {**ci, "original_run": {"run_id": "r"}}),
                     ("report on pairing map", {**ci, "inputs": {**ci["inputs"], vp.REPORT_ROLE: vp.REGION_MAPPING_SHA256}}),
                     ("report role", {**ci, "report": {**ci["report"], "role": "region_mapping"}}),
                     ("no report", {k: v for k, v in ci.items() if k != "report"})]
            for what, bad in cases:
                with self.assertRaises(vp.ValidityError, msg=what):
                    vp.check_config({**cfg, "corrected_input": bad}, 6, HPT)
            tuning = fx.config()
            with self.assertRaises(vp.ValidityError):                 # never on a tuning recipe
                vp.check_config({**tuning, "corrected_input": ci}, 6, HPT)
            vp.check_config(tuning, 6, HPT)                           # the tuned arm's own recipes are unchanged
        self.assertTrue(vp.hpt_caveat(6, fx.schedule).startswith("Tuned candidate"))

    def test_corrected_formal_job_passes_and_records_the_contract(self):
        fx = th.Fixture(0)
        with th.patched(fx):
            cfg, inputs, new, gpp = self.build(fx)
            res, root, _ = self.run_formal(new, cfg, inputs, gpp, "corrected")
        eq = json.load(open(os.path.join(root, "equivalence.json")))
        self.assertTrue(eq["passed"])
        ci = eq["corrected_input"]
        self.assertEqual((ci["preserved_differing"], ci["repinned_differing"], ci["unchanged_columns_differing_count"]), ([], [], 0))
        self.assertTrue(all(ci["inputs_verified"].values()))
        self.assertEqual(ci["unchanged_columns"], len(fx.order) - 13)
        # the original-run digests that were re-pinned really differ (the GPP columns changed)
        self.assertNotEqual(eq["treatment"]["feature_prefix_X_sha256"], cfg["baseline"]["equivalence"]["feature_prefix_X_sha256"])
        metrics = json.load(open(os.path.join(root, "metrics.json")))
        self.assertTrue(metrics["caveat"].startswith("Corrected-input refit"))
        self.assertNotIn("Every input, feature", metrics["caveat"])
        self.assertEqual(metrics["corrected_input"]["data_version"], "test-gpp-v3")
        self.assertEqual(res["identity"]["data_version"], "test-gpp-v3")
        pkg = json.load(open(os.path.join(root, "package", "package.json")))
        self.assertEqual(pkg["identity"]["corrected_input"]["interim_sha256"], cfg["corrected_input"]["inputs"]["interim"])
        self.assertEqual(res["identity"]["params"], REF100)
        rep = json.load(open(os.path.join(root, "report_tables.json")))
        rows = rep["rows"]
        self.assertEqual(len(rows), 6 * 2 + 2 * 4)
        pred = pd.read_csv(os.path.join(root, "predictions.csv.gz"), keep_default_na=False, na_values=[""])
        for scope, period in (("primary", "main"), ("holdout", "supplement")):
            self.assertEqual(sum(r["n_rows"] for r in rows if r["table"] == "region" and r["scope"] == scope),
                             int((pred["period"] == period).sum()))
        temporal = {(r["subset"], r["scope"]): r for r in rows if r["table"] == "temporal"}
        for y in ("2023", "2024", "2025"):
            want = int(((pred["period"] == "main") & (pred["target_ord"] // 12 == int(y))).sum())
            self.assertEqual(temporal[("All regions", y)]["n_rows"], want)
        self.assertEqual(temporal[("Somalia", "holdout")]["n_rows"], int(((pred["iso2"] == "SO") & (pred["period"] == "supplement")).sum()))
        for r in rows:                                               # value or explicit reason for every metric
            for k in vp.FORMAL_METRICS:
                self.assertTrue(r[k] is not None or r["na_reasons"].get(k), (r["subset"], r["scope"], k))
        self.assertTrue(any(k.startswith("report.region.") for k in res["metrics"]))
        self.assertEqual(res["metrics"]["report.temporal.all_regions.holdout.n_rows"], temporal[("All regions", "holdout")]["n_rows"])
        self.assertNotEqual(th.sha(os.path.join(root, "report_region_mapping.csv")), th.sha(os.path.join(root, "region_mapping.csv")))

    def test_report_marks_empty_declared_windows(self):
        fx = th.Fixture(12)
        pred = pd.DataFrame({"admin_code": [1, 2, 3], "iso2": ["SO", "AA", "SO"], "target_ord": [vp.parse_month(m) for m in ("2024-02", "2025-05", "2026-03")],
                             "period": ["main", "main", "supplement"], "label_kind": ["original", "copy", "copy"],
                             "phase_truth": [3, 2, 3], "phase": [3, 3, 3], "q3_truth": [0.3, 0.1, 0.4], "q3_star": [0.25, 0.2, 0.35]})
        path = os.path.join(self.tmp, "map.csv")
        pd.DataFrame({"area_id": [1, 2, 3], "region": [1, 0, 1]}).to_csv(path, index=False)
        rows, scal = vp.corrected_report(pred, path, fx.schedule, 12, {"regions": {"0": "Asia", "1": "East Africa"}, "somalia_iso2": "SO"})
        y23 = [r for r in rows if r["scope"] == "2023"]
        self.assertEqual(len(y23), 2)
        for r in y23:
            self.assertEqual((r["n_rows"], r["declared_from"], r["observed_from"]), (0, None, None))
            self.assertTrue(all("precedes the H12 historical window starting 2024-01" in v for v in r["na_reasons"].values()))
        so = {r["scope"]: r for r in rows if r["subset"] == "Somalia"}
        self.assertEqual((so["2024"]["n_rows"], so["2024"]["declared_from"], so["2024"]["observed_from"]), (1, "2024-01", "2024-02"))
        self.assertEqual(scal["report.temporal.somalia.holdout.n_rows"], 1.0)
        with self.assertRaises(vp.ValidityError):                    # an unmapped scored area
            vp.corrected_report(pred.assign(admin_code=[1, 2, 9]), path, fx.schedule, 12, {"regions": {"0": "Asia", "1": "East Africa"}, "somalia_iso2": "SO"})

    def test_corrected_gate_refuses_other_changes(self):
        from research_cloud.training.common import TrialError
        fx = th.Fixture(12)
        with th.patched(fx):
            cfg, inputs, new, gpp = self.build(fx)
        other = copy.copy(new)
        other.X = np.array(new.X, copy=True)
        j = next(i for i, c in enumerate(fx.order) if c not in gpp and c not in vf.HISTORY_FEATURES)
        other.X[:, j] = other.X[:, j] + 0.5                           # a non-GPP column changes
        relabel = copy.copy(new)
        relabel.L = new.L.copy()
        relabel.L.loc[relabel.L.index[0], "q3"] = min(1.0, float(relabel.L["q3"].iloc[0]) + 0.01)  # a label changes
        wrong = dict(inputs)
        p = os.path.join(self.tmp, "interim-other.csv")
        with open(p, "w") as f:
            f.write("different bytes\n")
        wrong["interim"] = p
        extra = {**inputs, "climate_monthly": inputs["interim"]}
        cases = [("non-GPP column", other, inputs, "unchanged_columns"), ("label", relabel, inputs, "targets_sha256"),
                 ("interim bytes", new, wrong, "input:interim"), ("unpinned role", new, extra, "unpinned_input:climate_monthly")]
        with th.patched(fx):
            for what, build, inp, needle in cases:
                with self.subTest(what):
                    with self.assertRaisesRegex(TrialError, "self-consistency digests differ") as cm:
                        self.run_formal(build, cfg, inp, gpp, f"bad-{what.replace(' ', '-')}")
                    self.assertIn(needle, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
