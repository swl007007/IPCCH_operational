"""Task 10-29: immutable IPCCH feature batches (R52) and batch-referenced inference validation/scoring (R18, R19, R32,
R36, R61) with a loadable synthetic package through the unchanged runtime path."""

import json

import numpy as np
import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import batch as bt
from cloud.ipcch import batch_inference as bi
from cloud.ipcch import binding as bd
from cloud.ipcch.stores import StoreRoot
from tests.cloud.ipcch_binding_fixtures import make_scoring_package, smoke_envelope
from tests.cloud.test_ipcch_assembly import ORDER

ROSTER = ["11", "12", "13"]
SMOKE_ROOT = "gs://b/ipcch-v2/smoke"
M = "2026-10"


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    d = tmp_path_factory.mktemp("pkg")
    return make_scoring_package(d / "package", ORDER)


def smoke_binding(tmp_path, package):
    smoke_envelope(tmp_path / "env.json", package)
    return bd.verify_combination(str(tmp_path / "env.json"), str(package), mode="smoke", fixture_root=str(tmp_path / "fx"))


def frame(seed=1, roster=ROSTER):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(len(roster), len(ORDER)))
    x[0, 5] = np.nan
    f = pd.DataFrame(x, columns=list(ORDER))
    ident = pd.DataFrame({"admin_code": roster, "area_id": roster, "population_estimate": [100.0, 200.0, 300.0][:len(roster)],
                          "population_reference_period": "2026-04",
                          "population_imputation_method": "last_observation_carried_forward"})
    return pd.concat([ident, f], axis=1)


def paired(store, binding, roster=ROSTER, mode="smoke"):
    """The store pairing initialisation records (the batch roster binds to it)."""
    root = StoreRoot(mode, f"gs://b/ipcch-v2/{mode}")
    have, generation = bd.store_pairing(store, root)
    if have is None:
        bd.commit_store_pairing(store, root, {"mode": mode, "combination_id": binding.combination_id,
                                              "package_manifest_sha256": binding.package_manifest_sha256,
                                              "feature_order_sha256": binding.feature_order_sha256,
                                              "bundle_manifest_sha256": "f" * 64,
                                              "roster_sha256": bt.roster_file_sha256(roster), "roster_size": len(roster)},
                                generation, binding)
    return store


def write(tmp_path, binding, horizons=None, run_id="run1", store=None):
    store = paired(store or LocalObjectStore(tmp_path / "store"), binding)
    bid = bt.new_batch_id(run_id, M)
    ref, man = bt.write_batch(store, SMOKE_ROOT, batch_id=bid, run_id=run_id, mode="smoke", execution_month=M,
                              binding=binding, horizons=horizons or {h: frame(h) for h in (2, 8, 14)}, roster=ROSTER,
                              generation={"coverage_end": {"GPP_mean": "2026-02"}, "gaps": {}, "warnings": []},
                              acceptance=[{"name": "fixed/roster.csv", "sha256": "0" * 64}],
                              retained_refs={"history__GPP_mean": {"version": 3}}, generated_at="2026-10-31T00:00:00Z")
    return store, bid, ref, man


def test_batch_round_trip_and_scoring_through_the_runtime(tmp_path, package):
    b = smoke_binding(tmp_path, package)
    store, bid, ref, man = write(tmp_path, b)
    assert man["feature_origin"] == "2026-08" and man["designation"] == "dummy"
    assert [man["horizons"][h]["target_month"] for h in ("2", "8", "14")] == ["2026-10", "2027-04", "2027-10"]
    assert man["horizons"]["2"]["missing_by_column"] == {ORDER[5]: 1}
    manifest, frames = bi.load_batch(store, ref, batch_root=SMOKE_ROOT, batch_id=bid, mode="smoke", execution_month=M, binding=b, roster=ROSTER)
    np.testing.assert_array_equal(frames[2][list(ORDER)].to_numpy(), frame(2)[list(ORDER)].to_numpy())   # bit-exact
    res = bi.score_batch(manifest, frames, str(package), b)
    for h in (2, 8, 14):
        out = res[h]["predictions"]
        assert set(out["mode"]) == {"smoke"} and set(out["batch_id"]) == {bid} and len(out) == 3
        assert res[h]["summary"]["thresholds"] == {t: 0.2 for t in bi.TARGETS}
        assert (out["phase2_worse_pred"] >= out["phase3_worse_pred"]).all()                 # cummax policy
    assert res[8]["predictions"]["target_period"].iloc[0] == "2027-04"


def test_batches_are_immutable_and_unique(tmp_path, package):
    b = smoke_binding(tmp_path, package)
    store, bid, ref, _ = write(tmp_path, b)
    with pytest.raises(bt.BatchError, match="never overwritten"):
        bt.write_batch(store, SMOKE_ROOT, batch_id=bid, run_id="run1", mode="smoke", execution_month=M, binding=b,
                       horizons={h: frame(h) for h in (2, 8, 14)}, roster=ROSTER, generation={}, acceptance=[],
                       retained_refs={}, generated_at="t")
    assert bt.new_batch_id("run1", M) != bt.new_batch_id("run1", M)


@pytest.mark.parametrize("mutate,match", [
    (lambda f: pd.concat([f, f.head(1)], ignore_index=True), "duplicate area keys"),
    (lambda f: f.iloc[1:].reset_index(drop=True), "exactly the roster"),
    (lambda f: f.assign(**{ORDER[3]: [np.inf, 0.0, 0.0]}), "infinite value at area 11"),
    (lambda f: f[[*bt.IDENTITY, *reversed(ORDER)]], "package feature order"),
])
def test_write_refuses_invalid_batches(tmp_path, package, mutate, match):
    b = smoke_binding(tmp_path, package)
    with pytest.raises(bt.BatchError, match=match):
        write(tmp_path, b, horizons={2: mutate(frame(2)), 8: frame(8), 14: frame(14)})
    assert not list((tmp_path / "store").rglob("manifest.json")) if (tmp_path / "store").exists() else True


def test_load_refuses_other_combination_mode_month_and_tampering(tmp_path, package):
    b = smoke_binding(tmp_path, package)
    store, bid, ref, man = write(tmp_path, b)
    other = make_scoring_package(tmp_path / "other", ORDER, combination_id="ipcch-other", seed=3)   # same 527 names
    smoke_envelope(tmp_path / "env-other.json", other)
    b2 = bd.verify_combination(str(tmp_path / "env-other.json"), str(other), mode="smoke", fixture_root=str(tmp_path / "fx"))
    with pytest.raises(bi.BatchValidationError, match="combination differs|bound to another combination"):
        bi.load_batch(store, ref, batch_root=SMOKE_ROOT, batch_id=bid, mode="smoke", execution_month=M, binding=b2, roster=ROSTER)
    with pytest.raises(bi.BatchValidationError, match="do not match the request M"):
        bi.load_batch(store, ref, batch_root=SMOKE_ROOT, batch_id=bid, mode="smoke", execution_month="2026-11", binding=b, roster=ROSTER)
    with pytest.raises(bi.BatchValidationError, match="batch id|refused before reading"):    # path names the batch id
        bi.load_batch(store, ref, batch_root=SMOKE_ROOT, batch_id="ipcch-other", mode="smoke", execution_month=M, binding=b, roster=ROSTER)
    with pytest.raises(bi.BatchValidationError, match="roster"):
        bi.load_batch(store, ref, batch_root=SMOKE_ROOT, batch_id=bid, mode="smoke", execution_month=M, binding=b, roster=ROSTER[:2])
    with pytest.raises(bi.BatchValidationError, match="sha256"):
        bi.load_batch(store, {**ref, "sha256": "0" * 64}, batch_root=SMOKE_ROOT, batch_id=bid, mode="smoke", execution_month=M, binding=b, roster=ROSTER)
    h2 = man["horizons"]["2"]["file"]
    store.write_text(h2, store.read_text(h2).replace("11,11", "11,99", 1))          # tampered data file
    with pytest.raises(bi.BatchValidationError, match="not the current immutable object|sha256"):
        bi.load_batch(store, ref, batch_root=SMOKE_ROOT, batch_id=bid, mode="smoke", execution_month=M, binding=b, roster=ROSTER)


def test_parse_reorders_ignores_extras_and_rejects_bad_columns_and_values():
    f = frame(2)
    shuffled = f[[*bt.IDENTITY, *reversed(ORDER)]].assign(qa_note="x", source_count=3)
    got = bi.parse_horizon(shuffled.to_csv(index=False), 2, ORDER, ROSTER)
    assert list(got.columns) == [*bt.IDENTITY, *ORDER]                               # model order, extras dropped
    np.testing.assert_array_equal(got[list(ORDER)].to_numpy(), f[list(ORDER)].to_numpy())
    text = f.to_csv(index=False)
    dup = text.replace(f",{ORDER[1]},", f",{ORDER[0]},", 1)
    with pytest.raises(bi.BatchValidationError, match="duplicate column names"):
        bi.parse_horizon(dup, 2, ORDER, ROSTER)
    with pytest.raises(bi.BatchValidationError, match="missing model-required columns"):
        bi.parse_horizon(f.drop(columns=[ORDER[7]]).to_csv(index=False), 2, ORDER, ROSTER)
    for bad, match in (("abc", "unparseable value 'abc' at area 12 column"), ("-inf", "infinite value '-inf' at area 12")):
        g = f.astype({ORDER[9]: object})
        g.loc[1, ORDER[9]] = bad
        with pytest.raises(bi.BatchValidationError, match=match):
            bi.parse_horizon(g.to_csv(index=False), 2, ORDER, ROSTER)


def test_nonfinite_model_output_fails_with_area_horizon_field(tmp_path, package, monkeypatch):
    b = smoke_binding(tmp_path, package)
    store, bid, ref, _ = write(tmp_path, b)
    manifest, frames = bi.load_batch(store, ref, batch_root=SMOKE_ROOT, batch_id=bid, mode="smoke", execution_month=M, binding=b, roster=ROSTER)
    import xgboost
    real = xgboost.XGBRegressor.predict

    def predict(self, X, *a, **k):
        out = real(self, X, *a, **k).astype("float64")
        out[1] = np.nan
        return out
    monkeypatch.setattr(xgboost.XGBRegressor, "predict", predict)
    with pytest.raises(bi.InferenceOutputError, match=r"H2 phase2_worse_score nonfinite at areas \['12'\]"):
        bi.score_batch(manifest, frames, str(package), b)


def test_real_request_rejects_a_dummy_batch(tmp_path, package):
    import dataclasses
    b = smoke_binding(tmp_path, package)
    store, bid, ref, _ = write(tmp_path, b)
    real = dataclasses.replace(b, mode="real", fixture_root=None)
    with pytest.raises(bi.BatchValidationError, match="batch root|real request cannot use a smoke/dummy batch"):
        bi.load_batch(store, ref, batch_root=SMOKE_ROOT, batch_id=bid, mode="real", execution_month=M, binding=real, roster=ROSTER)
    with pytest.raises(bi.BatchValidationError, match="combination binding"):
        bi.load_batch(store, ref, batch_root=SMOKE_ROOT, batch_id=bid, mode="real", execution_month=M, binding=b, roster=ROSTER)



# ---------------------------------------------------------------- Supervisor review ced8e52 regressions


class SpyStore:
    """Records every read/list/metadata touch of a URI."""

    def __init__(self, inner):
        self.inner, self.touched = inner, []

    def __getattr__(self, name):
        fn = getattr(self.inner, name)
        if name in ("read_text", "get_metadata", "list"):
            def wrapped(uri, *a, **k):
                self.touched.append(uri)
                return fn(uri, *a, **k)
            return wrapped
        return fn


def crafted(store, man, batch_id, mutate):
    """A manifest variant written (create-only) as another batch id's canonical manifest; returns its ref."""
    import copy
    import hashlib
    m = copy.deepcopy(man)
    m["batch_id"] = batch_id
    for h, entry in m["horizons"].items():                  # same bytes at the crafted batch's canonical paths
        path = bt.batch_paths(SMOKE_ROOT, batch_id)[h]
        entry["generation"] = store.write_text(path, store.read_text(entry["file"]), if_generation_match=0).generation
        entry["file"] = path
    mutate(m)
    text = json.dumps(m, indent=1, sort_keys=True) + "\n"
    uri = f"{SMOKE_ROOT}/feature_batches/{batch_id}/manifest.json"
    meta = store.write_text(uri, text, if_generation_match=0)
    return {"uri": uri, "generation": meta.generation, "sha256": hashlib.sha256(text.encode()).hexdigest()}


def test_namespace_admission_before_any_read(tmp_path, package):
    b = smoke_binding(tmp_path, package)
    store, bid, ref, man = write(tmp_path, b)
    spy = SpyStore(store)
    real_ref = {**ref, "uri": ref["uri"].replace("/smoke/", "/real/")}
    with pytest.raises(bi.BatchValidationError, match="refused before reading"):
        bi.load_batch(spy, real_ref, batch_root=SMOKE_ROOT, batch_id=bid, mode="smoke", execution_month=M, binding=b,
                      roster=ROSTER)
    with pytest.raises(bi.BatchValidationError, match="batch root"):
        bi.load_batch(spy, real_ref, batch_root="gs://b/ipcch-v2/real", batch_id=bid, mode="smoke", execution_month=M,
                      binding=b, roster=ROSTER)
    other = "ipcch-2026-10-run1-crafted0001"
    bad = crafted(store, man, other, lambda m: m["horizons"]["2"].update(file=m["horizons"]["2"]["file"].replace("/smoke/", "/real/")))
    with pytest.raises(bi.BatchValidationError, match="refused before reading"):
        bi.load_batch(spy, bad, batch_root=SMOKE_ROOT, batch_id=other, mode="smoke", execution_month=M, binding=b,
                      roster=ROSTER)
    assert not [u for u in spy.touched if "/real/" in u]


def test_horizon_metadata_must_follow_from_m(tmp_path, package):
    b = smoke_binding(tmp_path, package)
    store, bid, ref, man = write(tmp_path, b)
    for i, (key, value) in enumerate((("target_month", "1999-01"), ("public_lead_months", 0), ("feature_origin", "2026-07"),
                                      ("model_horizon_months", 2))):
        other = f"ipcch-2026-10-run1-crafted100{i}"
        h = "8"
        bad = crafted(store, man, other, lambda m: m["horizons"][h].update({key: value}))
        with pytest.raises(bi.BatchValidationError, match="horizon metadata differs"):
            bi.load_batch(store, bad, batch_root=SMOKE_ROOT, batch_id=other, mode="smoke", execution_month=M, binding=b,
                          roster=ROSTER)


def test_score_batch_verifies_the_package_itself(tmp_path, package):
    b = smoke_binding(tmp_path, package)
    store, bid, ref, _ = write(tmp_path, b)
    manifest, frames = bi.load_batch(store, ref, batch_root=SMOKE_ROOT, batch_id=bid, mode="smoke", execution_month=M,
                                     binding=b, roster=ROSTER)
    unrelated = make_scoring_package(tmp_path / "unrelated", ORDER, combination_id="ipcch-test-scoring", seed=9)
    with pytest.raises(bi.BatchValidationError, match="not the bound combination package"):     # same id/order/cutoffs
        bi.score_batch(manifest, frames, str(unrelated), b)
    import shutil
    tampered = tmp_path / "tampered"
    shutil.copytree(package, tampered)
    (tampered / "scope_6m" / "phase3_worse_model.json").write_text("{}")
    with pytest.raises(bi.BatchValidationError, match="differs from package_manifest.json"):
        bi.score_batch(manifest, frames, str(tampered), b)


def test_roster_binds_to_the_store_pairing(tmp_path, package):
    import dataclasses
    b = smoke_binding(tmp_path, package)
    store = LocalObjectStore(tmp_path / "real-store")
    real = dataclasses.replace(b, mode="real", fixture_root=None,
                               handoff={"manifest_sha256": "f" * 64, "roster_sha256": bt.roster_file_sha256(ROSTER + ["14", "15"]),
                                        "roster_size": 5})
    paired(store, real, roster=ROSTER + ["14", "15"], mode="real")
    with pytest.raises(bt.BatchError, match="not the store's bound roster"):          # 3-area caller roster
        bt.write_batch(store, "gs://b/ipcch-v2/real", batch_id=bt.new_batch_id("run1", M), run_id="run1", mode="real",
                       execution_month=M, binding=real, horizons={h: frame(h) for h in (2, 8, 14)}, roster=ROSTER,
                       generation={}, acceptance=[], retained_refs={}, generated_at="t")
    assert not list((tmp_path / "real-store").rglob("feature_batches"))
    sm, bid, ref, _ = write(tmp_path, b)
    with pytest.raises(bi.BatchValidationError, match="not the store's bound roster"):
        bi.load_batch(sm, ref, batch_root=SMOKE_ROOT, batch_id=bid, mode="smoke", execution_month=M, binding=b,
                      roster=ROSTER[:2])


def test_area_id_identity_and_ragged_rows(tmp_path, package):
    b = smoke_binding(tmp_path, package)
    bad = frame(2)
    bad.loc[1, "area_id"] = "99"
    with pytest.raises(bt.BatchError, match="area_id must equal admin_code"):
        write(tmp_path, b, horizons={2: bad, 8: frame(8), 14: frame(14)})
    text = frame(2).to_csv(index=False)
    with pytest.raises(bi.BatchValidationError, match="area_id must equal admin_code"):
        bi.parse_horizon(text.replace("\n12,12,", "\n12,99,", 1), 2, ORDER, ROSTER)
    lines = text.split("\n")
    lines[2] = "9999," + lines[2]                                                     # one extra leading field
    with pytest.raises(bi.BatchValidationError, match="ragged rows"):
        bi.parse_horizon("\n".join(lines), 2, ORDER, ROSTER)
    short = text.split("\n")
    short[3] = short[3].rsplit(",", 1)[0]
    with pytest.raises(bi.BatchValidationError, match="ragged rows"):
        bi.parse_horizon("\n".join(short), 2, ORDER, ROSTER)
