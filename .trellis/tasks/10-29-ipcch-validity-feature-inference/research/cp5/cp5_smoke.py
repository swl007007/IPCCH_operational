"""Task 10-29 CP5: local small-area smoke with the ACTUAL accepted H2/H8/H14 package and fixture-only inputs.

* model: the accepted combination envelope v2 (03b93842...) and the actual package (package manifest 18b91d45...,
  feature order 0ef1ffec..., the real q2..q5 XGBoost weights of H2/H8/H14) - verified by ``verify_combination`` in
  SMOKE mode with a declared fixture root; no synthetic fits.
* inputs: fixture-only - the existing smoke fixture bundle (manifest ``fixture: true``; 3 areas in 2 fixture
  countries AAA/BBB; synthetic histories for every family, delivered calendar, fixture ACLED tables, geometry,
  population and country references) inside the fixture root; fixture ACLED export, fixture climate providers.
  Nothing of the real handoff bundle, retained stores or real roots is read: a store spy records every URI and a
  filesystem spy every opened path; both are checked.
* executable route: ``cloud.ipcch.entrypoint_v2.run`` (validated deployment config, exact-generation request read,
  admission, locks, generation, batch, inference, delivery member, publication, run status) for
    1. generation-only (no publication),
    2. inference-only from the batch named by run 1, published to the smoke CURRENT pointer,
    3. generation + inference, published to the smoke current, REPLACING run 2's release (isolated current
       replacement: chained generation, the real pointer never exists/touched),
    4. failure preservation: generation + inference against a stale expected pointer generation - the publication
       fails (no retry/rebase), the smoke current stays run 3's, the generated batch stays reported.
Results -> cp5-results.json (this directory); artifacts under the run directory.

Run: ~/.venvs/fewsnet-test-lock-20261022/bin/python cp5_smoke.py <run dir>
"""

from __future__ import annotations

import builtins
import copy
import hashlib
import json
import sys
from pathlib import Path

OP = Path(__file__).resolve().parents[5] / "cloud_pipeline"
sys.path.insert(0, str(OP))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from cloud.common.object_store import LocalObjectStore  # noqa: E402
from cloud.ipcch import binding as bd  # noqa: E402
from cloud.ipcch import entrypoint_v2 as ep  # noqa: E402
from cloud.ipcch import initial  # noqa: E402
from cloud.ipcch import publication as pub  # noqa: E402
from cloud.ipcch.stores import StoreRoot  # noqa: E402
from tests.cloud import ipcch_smoke_fixture as fx  # noqa: E402
from tests.cloud.test_ipcch_initial import accept  # noqa: E402

R = Path("/home/swl007007/projects/food-crisis-research")
PKG = R / "scratch/h2h8h14-final/package-build/out-r1/package"
ENV = R / "scratch/h2h8h14-final/envelope/ipcch-combination-envelope-v2-accepted.json"
REAL_BUNDLE = R / "scratch/h2h8h14-final/handoff-build/out-r5-accepted-v1"
COMBINATION = "ipcch-validity-h2h8h14-final-20261030"
ROOTS = {"smoke": "gs://ops-delivery-smoke/v2", "real": "gs://ops-delivery/v2"}
STORES = {"smoke": "gs://ipcch-store/ipcch-v2/smoke", "real": "gs://ipcch-store/ipcch-v2/real"}
FORBIDDEN_PATHS = (str(REAL_BUNDLE), str(R / "staging"), "/ipcch-v2/real")


class SpyStore:
    """Every URI the route touches through the store."""

    def __init__(self, inner):
        self.inner, self.touched = inner, []

    def __getattr__(self, name):
        attr = getattr(self.inner, name)
        if not callable(attr):
            return attr

        def call(*a, **k):
            self.touched += [x for x in list(a) + list(k.values()) if isinstance(x, str) and x.startswith("gs://")]
            return attr(*a, **k)
        return call


class Reader:
    def __init__(self, refs, store):
        self.refs, self.store = refs, store

    def read_bytes(self, uri, generation):
        if (uri, generation) in self.refs.objects:
            return self.refs.objects[(uri, generation)]
        meta = self.store.get_metadata(uri)
        return self.store.read_bytes(uri) if meta and str(meta.generation) == str(generation) else None


def raw(validated):
    d = copy.deepcopy(validated)
    for k in ("derived", "request", "validation_level"):
        d.pop(k, None)
    return d


def put_request(refs, body):
    uri = f"gs://ops-smoke/requests/{body['run_id']}/run_manifest.json"
    refs.objects[(uri, "1")] = json.dumps(body).encode()
    return uri


def predictions(store, delivery_ref) -> dict:
    """Per published horizon: rows, unique roster, finite scores, mode labels, months (from the stored delivery)."""
    base = delivery_ref["uri"].rsplit("/", 1)[0]
    out = {}
    for lead in (0, 6, 12):
        uri = f"{base}/scopes/{lead}m/ipcch/polygon_predictions.csv"
        f = pd.read_csv(pd.io.common.StringIO(store.read_text(uri)), dtype={"polygon_id": str, "area_id": str,
                                                                              "admin_code": str})
        scores = f[[c for c in f.columns if c.endswith("_score")]].to_numpy(dtype=float)
        out[str(lead)] = {"rows": len(f), "areas": sorted(f["admin_code"].astype(str)), "finite": bool(np.isfinite(scores).all()),
                          "mode": sorted(set(f["mode"])), "feature_period": sorted(set(f["feature_period"].astype(str))),
                          "target_period": sorted(set(f["target_period"].astype(str))),
                          "sha256": hashlib.sha256(store.read_bytes(uri)).hexdigest()}
    return out


def _split_equals_combined(store, split_ref, combined_ref) -> bool:
    """Gen-only -> inf-only (run 1+2) and gen+inf (run 3) on identical inputs: every prediction column equal per
    horizon except ``source_input`` (the batch reference)."""
    out = True
    for lead in (0, 6, 12):
        frames = [pd.read_csv(pd.io.common.StringIO(store.read_text(
            f"{ref['uri'].rsplit('/', 1)[0]}/scopes/{lead}m/ipcch/polygon_predictions.csv")), dtype=str)
            for ref in (split_ref, combined_ref)]
        cols = [c for c in frames[0].columns if c != "source_input"]
        out &= list(frames[0].columns) == list(frames[1].columns) and frames[0][cols].equals(frames[1][cols])
    return bool(out)


def _batches(store) -> list[str]:
    return sorted(u for u in store.list(f"{STORES['smoke']}/feature_batches/") if u.endswith("/manifest.json"))


def _corrupt_h14(store, store_dir: Path, manifest_ref) -> str:
    """Overwrite the H14 file of a batch on disk (simulated corruption of an immutable object; one value changed)."""
    manifest = json.loads(store.read_text(manifest_ref["uri"]))
    base = manifest_ref["uri"].rsplit("/", 1)[0]
    rel = next(v["file"] for k, v in manifest["horizons"].items() if k == "14")
    uri = rel if rel.startswith("gs://") else f"{base}/{rel}"
    path = store_dir / uri.removeprefix("gs://")
    lines = path.read_text().splitlines(True)
    cells = lines[1].rstrip("\n").split(",")
    cells[-1] = "123456.0"
    lines[1] = ",".join(cells) + "\n"
    path.write_text("".join(lines))
    return uri


def main(run_dir: Path) -> dict:
    run_dir.mkdir(parents=True, exist_ok=False)
    fixture_root = run_dir / "fixture-root"
    fixture_root.mkdir()
    bundle, man = fx.build_bundle(fixture_root)               # fixture-only inputs (manifest fixture: true)
    binding = bd.verify_combination(str(ENV), str(PKG), mode="smoke", fixture_root=str(fixture_root))
    assert binding.combination_id == COMBINATION and binding.status == "accepted"
    inner = LocalObjectStore(run_dir / "store")
    root = StoreRoot("smoke", STORES["smoke"])
    accept(inner, root, man)                                   # fixture acceptance records (smoke validates them)
    initial.initialise(inner, root, str(bundle), binding=binding)
    store = SpyStore(inner)
    refs = fx.Refs()
    cfg_path = run_dir / "deployment.json"
    cfg_path.write_text(json.dumps({
        "roots": ROOTS, "store_roots": STORES, "namespaces": {"production": "prod", "smoke": "smoke"},
        "trusted_prefixes": {"smoke": ["gs://ops-smoke/inputs/"], "real": ["gs://ops-real/inputs/"]},
        "installed": {"smoke": {"envelope": str(ENV), "package_root": str(PKG), "bundle_dir": str(bundle),
                                "fixture_root": str(fixture_root)},
                      "real": {"envelope": str(ENV), "package_root": str(PKG), "bundle_dir": str(REAL_BUNDLE)}},
        "providers": {"smoke": "tests.cloud.ipcch_smoke_fixture:entrypoint_providers",
                      "real": "cloud.ipcch.entrypoint_v2:real_providers"},
        "earth_engine_project": "unused-in-smoke", "export_root": "gs://ops-smoke/exports",
        "work_dir": str(run_dir / "work")}, indent=2))
    cfg = ep.load_config(str(cfg_path))
    opened = []
    real_open = builtins.open

    def spy_open(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)
    results = {"model": {"envelope_sha256": hashlib.sha256(ENV.read_bytes()).hexdigest(),
                         "package_manifest_sha256": binding.package_manifest_sha256,
                         "feature_order_sha256": binding.feature_order_sha256, "combination_id": COMBINATION},
               "fixture": {"bundle_manifest_sha256": hashlib.sha256((bundle / "handoff_manifest.json").read_bytes()).hexdigest(),
                           "roster": [str(a) for a in fx.ROSTER], "countries": ["AAA", "BBB"],
                           "neighbours": "fixture geometries are adjacent unit boxes (11|12 in AAA, 13 in BBB): "
                                         "a contiguous neighbour subset across two fixture countries"}, "runs": {}}
    builtins.open = spy_open
    try:
        # 1. generation-only
        gen = raw(fx.smoke_request(refs, ENV, run_id="cp5-gen", combination_id=COMBINATION))
        out1 = ep.run(cfg, request_uri=put_request(refs, gen), request_generation="1", store=store,
                      reader=Reader(refs, inner))
        batch = out1["systems"]["ipcch"]["result"]["batch"]
        # 2. inference-only from that batch, published to the smoke current
        inf = raw(fx.smoke_request(refs, ENV, run_id="cp5-inf", combination_id=COMBINATION, inference=True))
        inf["operations"].update(ipcch_generation=False)
        inf["ipcch"] = {"model_combination": inf["ipcch"]["model_combination"],
                        "country_reference": inf["ipcch"]["country_reference"],
                        "feature_batch": {"batch_id": batch["batch_id"], "manifest": batch["manifest_ref"]}}
        inf["publication"] = "current"
        inf["release"]["expected_pointer_generation"] = pub.read_current(inner, ROOTS["smoke"], "smoke")["generation"]
        out2 = ep.run(cfg, request_uri=put_request(refs, inf), request_generation="1", store=store,
                      reader=Reader(refs, inner))
        after2 = pub.read_current(inner, ROOTS["smoke"], "smoke")
        # 3. generation + inference, replacing run 2's current release
        comb = raw(fx.smoke_request(refs, ENV, run_id="cp5-comb", combination_id=COMBINATION, inference=True))
        comb["publication"] = "current"
        comb["release"]["expected_pointer_generation"] = after2["generation"]
        out3 = ep.run(cfg, request_uri=put_request(refs, comb), request_generation="1", store=store,
                      reader=Reader(refs, inner))
        after3 = pub.read_current(inner, ROOTS["smoke"], "smoke")
        # 4. failure preservation: generation + inference against a STALE expected pointer generation -> publication
        #    fails without retry/rebase, the smoke current stays run 3's, the generated batch stays reported/reusable
        stale = raw(fx.smoke_request(refs, ENV, run_id="cp5-stale", combination_id=COMBINATION, inference=True))
        stale["publication"] = "current"
        stale["release"]["expected_pointer_generation"] = after2["generation"]
        out4 = ep.run(cfg, request_uri=put_request(refs, stale), request_generation="1", store=store,
                      reader=Reader(refs, inner))
        after4 = pub.read_current(inner, ROOTS["smoke"], "smoke")
        # 5. generation failure: the fixture climate provider reports the origin month unavailable (R13) -> the
        #    generation stops after the saved ACLED refresh (kept + reported, R29/R41), no batch, current unchanged
        cfg_fail = dict(cfg, providers={**cfg["providers"],
                                        "smoke": "tests.cloud.test_ipcch_entrypoint_v2:unavailable_climate"})
        # (the next execution month: its origin month has no saved climate yet, so the provider is actually needed)
        genfail = raw(fx.smoke_request(refs, ENV, execution_month="2027-04", run_id="cp5-genfail",
                                       combination_id=COMBINATION, inference=True))
        genfail["publication"] = "current"
        genfail["release"]["expected_pointer_generation"] = after4["generation"]
        batches_before = _batches(inner)
        out5 = ep.run(cfg_fail, request_uri=put_request(refs, genfail), request_generation="1", store=store,
                      reader=Reader(refs, inner))
        after5 = pub.read_current(inner, ROOTS["smoke"], "smoke")
        new_batches_5 = sorted(set(_batches(inner)) - set(batches_before))
        # 6. inference/horizon failure: run 4's (unpublished) batch with its H14 file corrupted on disk -> inference
        #    refuses it (no fallback batch), current unchanged
        b4 = out4["systems"]["ipcch"]["result"]["batch"]
        h14 = _corrupt_h14(inner, run_dir / "store", b4["manifest_ref"])
        inf6 = raw(fx.smoke_request(refs, ENV, run_id="cp5-inffail", combination_id=COMBINATION, inference=True))
        inf6["operations"].update(ipcch_generation=False)
        inf6["ipcch"] = {"model_combination": inf6["ipcch"]["model_combination"],
                         "country_reference": inf6["ipcch"]["country_reference"],
                         "feature_batch": {"batch_id": b4["batch_id"], "manifest": b4["manifest_ref"]}}
        inf6["publication"] = "current"
        inf6["release"]["expected_pointer_generation"] = after5["generation"]
        batches_before6 = _batches(inner)
        out6 = ep.run(cfg, request_uri=put_request(refs, inf6), request_generation="1", store=store,
                      reader=Reader(refs, inner))
        after6 = pub.read_current(inner, ROOTS["smoke"], "smoke")
    finally:
        builtins.open = real_open
    for name, out in (("generation_only", out1), ("inference_only", out2), ("combined", out3),
                      ("stale_publication", out4), ("generation_failure", out5), ("inference_horizon_failure", out6)):
        ip = out["systems"]["ipcch"]
        results["runs"][name] = {"status": out["status"], "ipcch_status": ip["status"], "reason": ip.get("reason"),
                                 "status_uri": out["status_uri"],
                                 "publication": (ip.get("result") or {}).get("publication"),
                                 "batch": (ip.get("result") or {}).get("batch")}
    rec2, rec3 = after2["record"], after3["record"]
    results["failures"] = {"generation_failure_report_steps": (out5["systems"]["ipcch"].get("report") or {}).get("steps"),
                           "inference_failure_reason": out6["systems"]["ipcch"].get("reason"),
                           "corrupted_h14": h14}
    results["current"] = {
        "after_inference_only": {"generation": after2["generation"], "run_id": rec2["run_id"],
                                 "ipcch_mode": rec2["systems"]["ipcch"]["mode"], "activation": rec2["activation"],
                                 "predictions": predictions(inner, rec2["systems"]["ipcch"]["delivery"]["manifest"])},
        "after_combined": {"generation": after3["generation"], "run_id": rec3["run_id"],
                           "previous": rec3["previous"], "activation": rec3["activation"],
                           "predictions": predictions(inner, rec3["systems"]["ipcch"]["delivery"]["manifest"])}}
    real_uris = [u for u in store.touched if u.startswith((ROOTS["real"], STORES["real"]))]
    forbidden = sorted({p for p in opened if any(f in p for f in FORBIDDEN_PATHS)})
    results["isolation"] = {"real_store_or_root_uris_touched": real_uris, "forbidden_paths_opened": forbidden,
                            "real_pointer_exists": inner.get_metadata(pub.pointer_uri(ROOTS["real"], "prod")) is not None,
                            "store_uris_touched": len(set(store.touched)), "paths_opened": len(set(opened))}
    results["checks"] = {
        "generation_failure_preserved": (out5["systems"]["ipcch"]["status"] == "failed"
                                         and out5["systems"]["ipcch"].get("failed_operation") == "generation"
                                         and out5["systems"]["ipcch"]["report"]["steps"]["acled"]["action"] == "refresh"
                                         and new_batches_5 == [] and after5["generation"] == after4["generation"]),
        "inference_failure_preserved": (out6["systems"]["ipcch"]["status"] == "failed"
                                        and out6["systems"]["ipcch"].get("failed_operation") == "inference"
                                        and _batches(inner) == batches_before6
                                        and "inference" not in (out6["systems"]["ipcch"].get("result") or {})
                                        and after6["generation"] == after5["generation"]),
        "runs_1_3_succeeded": all(results["runs"][r]["status"] == "succeeded"
                                  for r in ("generation_only", "inference_only", "combined")),
        "failure_preserved": (results["runs"]["stale_publication"]["ipcch_status"] == "failed"
                              and out4["systems"]["ipcch"].get("failed_operation") == "publication"
                              and after4["generation"] == after3["generation"]
                              and bool(results["runs"]["stale_publication"]["batch"])),
        "generation_only_not_published": results["runs"]["generation_only"]["publication"] is None,
        "inference_only_used_named_batch": results["runs"]["inference_only"]["batch"] is None,
        "combined_replaced_current": rec3["previous"]["pointer_generation"] == after2["generation"]
                                     and rec3["run_id"] == "cp5-comb-ipcch" and rec2["run_id"] == "cp5-inf-ipcch",
        "smoke_never_activates": rec2["activation"] is None and rec3["activation"] is None,
        "predictions_complete_finite_smoke": all(
            h["rows"] == len(fx.ROSTER) and h["finite"] and h["mode"] == ["smoke"]
            for snap in (results["current"]["after_inference_only"], results["current"]["after_combined"])
            for h in snap["predictions"].values()),
        "zero_real_touch": not real_uris and not forbidden and not results["isolation"]["real_pointer_exists"],
        "split_equals_combined_except_source_input": _split_equals_combined(
            inner, rec2["systems"]["ipcch"]["delivery"]["manifest"], rec3["systems"]["ipcch"]["delivery"]["manifest"])}
    return results


if __name__ == "__main__":
    run = Path(sys.argv[1])
    res = main(run)
    text = json.dumps(res, indent=2, sort_keys=True, default=str) + "\n"
    (run / "cp5-results.json").write_text(text)
    Path(__file__).with_name("cp5-results.json").write_text(text)
    print(json.dumps(res["checks"], indent=2))
