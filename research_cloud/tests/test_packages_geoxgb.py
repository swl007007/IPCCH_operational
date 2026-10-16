"""Behavioral package tests: build from a synthetic GeoXGB run, load through the keyed loader,
replay, and check tamper/path/unknown-key failures. Needs xgboost (run in rt-geoxgb-x300) and the
archived P6 source_code artifact for the vendored loader."""
import hashlib
import json
import os
import shutil
import tempfile
import unittest

import numpy as np
import pandas as pd

SRC = ("/home/swl007007/.local/share/ipcch-mlflow/artifacts/1/bdbafe393d694439a1c35ccec4d5816a/"
       "artifacts/source_code/IPCCHGeoXGBExperiment")
try:
    import xgboost as xgb
except ImportError:
    xgb = None


def booster(X, y, seed):
    d = xgb.DMatrix(X, label=y, missing=np.nan)
    return bytes(xgb.train({"objective": "reg:squarederror", "max_depth": 2, "seed": seed, "nthread": 1,
                            "base_score": 0.5}, d, 5).save_raw("ubj"))


def make_run(root):
    """Two target months, two regions + unmapped area; gated arm: region r1 local in month 11."""
    rng = np.random.default_rng(0)
    areas = [1, 2, 3, 4]
    keys = pd.DataFrame([(a, t) for t in (10, 11) for a in areas], columns=["admin_code", "target_ord"])
    X = rng.normal(size=(len(keys), 6)); X[::3, 1] = np.nan
    os.makedirs(f"{root}/prepared"); os.makedirs(f"{root}/stage1"); os.makedirs(f"{root}/stage3/h03")
    keys.to_csv(f"{root}/prepared/keys_h03.csv.gz", index=False)
    np.save(f"{root}/prepared/X_rich561_h03.npy", X)
    pd.DataFrame({"position": range(6), "name": [f"f{i}" for i in range(6)], "block": "x"}).to_csv(
        f"{root}/prepared/feature_order.csv", index=False)
    pd.DataFrame({"admin_code": [1, 2, 3], "node_id": ["r1", "r1", "r2"]}).to_csv(f"{root}/stage1/frozen_map_h03.csv", index=False)
    for name in ("stage1/frozen_h03.json", "stage3/h03/gate_decisions.jsonl", "stage3/h03/fold_ledger.csv"):
        open(f"{root}/{name}", "w").write("{}\n")
    members, units = [], {}
    for label, seed in (("g10", 1), ("g11", 2), ("l11", 3)):
        payloads = {q: booster(X, rng.uniform(size=len(X)), seed + k) for k, q in enumerate(["q2", "q3", "q4", "q5"])}
        d = hashlib.sha256(label.encode()).hexdigest()
        units[label] = d
        base = f"{root}/models/{d[:2]}/{d}"
        os.makedirs(base)
        for q, data in payloads.items():
            open(f"{base}/{q}.ubj", "wb").write(data)
        open(f"{base}/record.json", "w").write(json.dumps({
            "fit_records": {q: {} for q in payloads},
            "booster_sha256": {q: hashlib.sha256(b).hexdigest() for q, b in payloads.items()}}))
        for name in ["q2.ubj", "q3.ubj", "q4.ubj", "q5.ubj", "record.json"]:
            b = open(f"{base}/{name}", "rb").read()
            members.append({"path": f"models/{d[:2]}/{d}/{name}", "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()})
    json.dump(members, open(f"{root}/members.json", "w"))
    import sys
    sys.path.insert(0, SRC)
    from ipcch_geoxgb import projection, quartet
    rows = []
    region_of = {1: "r1", 2: "r1", 3: "r2"}
    for i, (a, t) in enumerate(zip(keys.admin_code, keys.target_ord)):
        g = units["g10"] if t == 10 else units["g11"]
        region = region_of.get(a, "")
        if t == 11 and region == "r1":
            prov, route = units["l11"], "local"
        else:
            prov, route = g, "unmapped_area_global" if region == "" else "global_fallback:gain_not_above_threshold"
        rows.append(dict(admin_code=a, target_ord=t, origin_ord=t - 3, fold_id=f"F{t}", region=region or np.nan,
                         route=route, provider=prov, global_identity=g, row=i))
    pred = pd.DataFrame(rows)
    for arm_prefix, col in (("pool_", "global_identity"), ("geo_", "provider")):
        raw = np.zeros((len(pred), 4))
        for u in pred[col].unique():
            idx = np.flatnonzero(pred[col] == u)
            base = f"{root}/models/{u[:2]}/{u}"
            payloads = {}
            for k in quartet.TARGETS:
                with open(f"{base}/{k}.ubj", "rb") as fh:
                    payloads[k] = fh.read()
            q = quartet.Quartet(payloads, {k: {} for k in quartet.TARGETS})
            raw[idx] = q.predict_raw(X[pred.row.to_numpy()[idx]])
        star, phase = projection.project_and_decode(raw)
        for j, k in enumerate(quartet.TARGETS):
            pred[f"{arm_prefix}{k}_raw"], pred[f"{arm_prefix}{k}_star"] = raw[:, j], star[:, j]
        pred[f"{arm_prefix}phase"] = phase
    pred.drop(columns="row").to_csv(f"{root}/stage3/h03/predictions.csv.gz", index=False)
    return units


@unittest.skipUnless(xgb is not None and os.path.isdir(SRC), "needs xgboost and the archived P6 source_code")
class GeoXGBPackageBehaviour(unittest.TestCase):
    def setUp(self):
        from research_cloud.packages import geoxgb
        self.geoxgb = geoxgb
        self.tmp = tempfile.mkdtemp()
        self.run_root = os.path.join(self.tmp, "run")
        self.units = make_run(self.run_root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build(self, arm):
        out = os.path.join(self.tmp, f"pkg-{arm}")
        self.geoxgb.build(out, family="geoxgb_reference", run_root=self.run_root, source_code_dir=SRC, members_manifest=f"{self.run_root}/members.json",
                          version={"registered_model": "t", "version": 1}, lead=3, arm=arm, code_identity={},
                          original_runtime={}, linux_runtime={})
        return out

    def replay(self, pkg):
        from research_cloud.packages import replay
        report = os.path.join(self.tmp, "r.json")
        rc = replay.main([pkg, "--report", report])
        return rc, json.load(open(report))

    def test_gated_package_resolves_routes_and_replays(self):
        pkg = self.build("partitioned_gated")
        meta = json.load(open(f"{pkg}/package.json"))
        self.assertEqual(meta["status"], "complete")
        self.assertEqual(set(meta["reference"]["routes_covered"]),
                         {"local", "unmapped_area_global", "global_fallback:gain_not_above_threshold"})
        self.assertGreater(meta["reference"]["rows_with_missing_features"], 0)
        rc, rep = self.replay(pkg)
        self.assertEqual((rc, rep["passed"], rep["routing_mismatches"]), (0, True, 0))
        import importlib.util
        spec = importlib.util.spec_from_file_location("e", f"{pkg}/loader/entry.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        model = mod.load(pkg)
        got = model.resolve(pd.DataFrame({"admin_code": [1, 4], "target_ord": [11, 11]}))
        self.assertEqual(got[0], (self.units["l11"], "local"))
        self.assertEqual(got[1], (self.units["g11"], "unmapped_area_global"))
        with self.assertRaises(KeyError):
            model.resolve(pd.DataFrame({"admin_code": [1], "target_ord": [99]}))

    def test_pooled_package_uses_global_units(self):
        pkg = self.build("pooled")
        rc, rep = self.replay(pkg)
        self.assertEqual((rc, rep["passed"]), (0, True))
        self.assertEqual(json.load(open(f"{pkg}/package.json"))["fitted_units"], 2)

    def test_altered_weight_or_expected_value_fails(self):
        pkg = self.build("pooled")
        exp = pd.read_csv(f"{pkg}/reference/expected.csv")
        exp.loc[0, "q3_raw"] += 0.01
        exp.to_csv(f"{pkg}/reference/expected.csv", index=False)
        rc, rep = self.replay(pkg)
        self.assertEqual(rc, 1)
        self.assertTrue(any("altered reference/expected.csv" in p for p in rep["integrity_problems"]))

    def test_tolerance_violation_fails_even_with_consistent_manifest(self):
        from research_cloud.packages.replay import compare
        exp = pd.DataFrame({**{f"q{k}_{t}": [0.5] for k in range(2, 6) for t in ("raw", "star")}, "phase": [5]})
        raw = np.full((1, 4), 0.5); star = raw.copy(); star[0, 1] = 0.5 + 0.0016
        self.assertFalse(compare(exp, raw, star, np.array([5]))["passed"])

    def test_reordered_or_wrong_key_output_fails(self):
        from research_cloud.packages.replay import check_output
        pkg = self.build("partitioned_gated")
        exp = pd.read_csv(f"{pkg}/reference/expected.csv", dtype={"unit": str})
        got = exp.copy()
        self.assertTrue(check_output(got, exp)["passed"])
        self.assertFalse(check_output(got.iloc[::-1].reset_index(drop=True), exp)["passed"])
        wrong = got.copy(); wrong.loc[0, "admin_code"] = 999
        self.assertFalse(check_output(wrong, exp)["passed"])
        rerouted = got.copy(); rerouted.loc[0, "unit"] = "0" * 64
        self.assertEqual(check_output(rerouted, exp)["routing_mismatches"], 1)

    def test_invalid_phase_near_threshold_is_not_boundary_drift(self):
        from research_cloud.packages.replay import compare
        star_ref = [0.6, 0.2005, 0.1, 0.05]
        exp = pd.DataFrame({**{f"q{k}_raw": [v] for k, v in zip(range(2, 6), star_ref)},
                            **{f"q{k}_star": [v] for k, v in zip(range(2, 6), star_ref)}, "phase": [3]})
        drift = np.array([[0.6, 0.1999, 0.1, 0.05]])
        self.assertTrue(compare(exp, drift, drift, np.array([2]))["passed"])   # genuine crossing, correct decode
        self.assertFalse(compare(exp, drift, drift, np.array([4]))["passed"])  # wrong phase despite a near crossing
        self.assertFalse(compare(exp, drift, drift, np.array([3]))["passed"])  # phase not the decode of new scores

    def test_reference_cap_respected_with_route_coverage(self):
        from research_cloud.packages.common import select_reference
        frame = pd.DataFrame({"unit": ["u"] * 100, "route": ["a"] * 90 + ["b"] * 10,
                              "k": range(100), "t": 0})
        sel = select_reference(frame, "unit", pd.Series(np.linspace(0, 1, 100)), ["k", "t"], per_unit=8,
                               cover_cols=("route",))
        self.assertLessEqual(len(sel), 8)
        self.assertEqual(set(sel["route"]), {"a", "b"})

    def test_truncated_member_manifest_is_not_complete(self):
        members = json.load(open(f"{self.run_root}/members.json"))
        u = self.units["g10"]
        json.dump([m for m in members if m["path"] != f"models/{u[:2]}/{u}/q3.ubj"], open(f"{self.run_root}/members.json", "w"))
        pkg = self.build("pooled")
        meta = json.load(open(f"{pkg}/package.json"))
        self.assertEqual(meta["status"], "retained_weights_missing_dependencies")
        self.assertTrue(any("q3.ubj" in g for g in meta["gaps"]))

    def test_record_digest_mismatch_is_not_complete(self):
        u = self.units["g11"]
        path = f"{self.run_root}/models/{u[:2]}/{u}/record.json"
        rec = json.load(open(path)); rec["booster_sha256"]["q4"] = "0" * 64
        open(path, "w").write(json.dumps(rec))
        members = json.load(open(f"{self.run_root}/members.json"))
        for m in members:
            if m["path"].endswith(f"{u}/record.json"):
                b = open(path, "rb").read(); m["bytes"], m["sha256"] = len(b), hashlib.sha256(b).hexdigest()
        json.dump(members, open(f"{self.run_root}/members.json", "w"))
        meta = json.load(open(f"{self.build('pooled')}/package.json"))
        self.assertEqual(meta["status"], "retained_weights_missing_dependencies")

    def test_unsafe_paths_refused(self):
        from research_cloud.packages.common import PackageBuilder, PackageError
        b = PackageBuilder(os.path.join(self.tmp, "p"))
        for rel in ("../x", "/etc/passwd", "a/../../x", ""):
            with self.assertRaises(PackageError):
                b.add_bytes(rel, b"x")

    def test_member_hash_mismatch_refused(self):
        u = self.units["g10"]
        with open(f"{self.run_root}/models/{u[:2]}/{u}/q2.ubj", "r+b") as f:
            f.seek(0); first = f.read(1); f.seek(0); f.write(bytes([first[0] ^ 1]))
        from research_cloud.packages.common import PackageError
        with self.assertRaises(PackageError):
            self.build("pooled")


if __name__ == "__main__":
    unittest.main()


def make_yearly_run(root):
    """Yearly layout from the P6 synthetic run: ungated local models exist only for region r1."""
    units = make_run(root)
    os.makedirs(f"{root}/inputs/run")
    for d in ("prepared", "stage1"):
        shutil.move(f"{root}/{d}", f"{root}/inputs/run/{d}")
    os.rename(f"{root}/inputs/run/stage1/frozen_h03.json", f"{root}/inputs/run/stage1/frozen_h03.json")
    os.makedirs(f"{root}/predict/h03")
    for name in ("gate_decisions.jsonl", "fold_ledger.csv"):
        shutil.move(f"{root}/stage3/h03/{name}", f"{root}/predict/h03/{name}")
    open(f"{root}/predict/h03/block_ledger.json", "w").write("{}\n")
    p = pd.read_csv(f"{root}/stage3/h03/predictions.csv.gz")
    local = p["provider"] == units["l11"]
    p = p.rename(columns={"global_identity": "pool_provider"})
    p["local_provider"] = np.where(local, units["l11"], "")
    p["route"] = np.where(local, "local", "pool_fallback:gain_not_above_threshold")
    for q in ("q2", "q3", "q4", "q5"):
        for t in ("raw", "star"):
            p[f"local_{q}_{t}"] = np.where(local, p[f"geo_{q}_{t}"], np.nan)
    p["local_phase"] = np.where(local, p["geo_phase"], 0)
    p.drop(columns=["provider"]).to_csv(f"{root}/predict/h03/predictions.csv.gz", index=False)
    return units


YEARLY_SRC = ("/home/swl007007/.local/share/ipcch-mlflow/artifacts/1/a6dc32cda52f45a7a5f12e87a72c6749/"
              "artifacts/source_code/IPCCHYearlyGeoXGBExperiment")


@unittest.skipUnless(xgb is not None and os.path.isdir(SRC) and os.path.isdir(YEARLY_SRC), "needs xgboost and archived source_code")
class YearlyUngatedUnavailableKeys(unittest.TestCase):
    def test_ungated_serves_only_keys_with_a_local_model(self):
        import importlib.util
        from research_cloud.packages import geoxgb, replay
        tmp = tempfile.mkdtemp()
        try:
            root = os.path.join(tmp, "run")
            units = make_yearly_run(root)
            pkg = os.path.join(tmp, "pkg")
            meta = geoxgb.build(pkg, family="geoxgb_yearly_refit", run_root=root, source_code_dir=YEARLY_SRC,
                                members_manifest=f"{root}/members.json", version={}, lead=3, arm="regional_ungated",
                                code_identity={}, original_runtime={}, linux_runtime={})
            self.assertEqual(meta["status"], "complete")
            self.assertGreater(meta["routing"]["unserved_keys_in_saved_predictions"], 0)
            self.assertEqual(replay.main([pkg, "--report", os.path.join(tmp, "r.json")]), 0)
            spec = importlib.util.spec_from_file_location("e", f"{pkg}/loader/entry.py")
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            model = mod.load(pkg)
            self.assertEqual(model.resolve(pd.DataFrame({"admin_code": [1], "target_ord": [11]}))[0][0], units["l11"])
            for area, month in ((3, 11), (4, 11), (1, 10)):  # other region, unmapped, no local fit that month
                with self.assertRaises(KeyError):
                    model.resolve(pd.DataFrame({"admin_code": [area], "target_ord": [month]}))
        finally:
            shutil.rmtree(tmp)
