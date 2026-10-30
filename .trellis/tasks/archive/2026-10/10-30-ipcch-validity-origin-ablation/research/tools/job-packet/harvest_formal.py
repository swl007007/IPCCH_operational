"""Origin-ablation job packet step (reads only; the task 10-28 ``harvest_formal.py`` with the origin pins and checks):
download one succeeded formal job's trial prefix once (per-object generation-pinned, CRC32C-validated Python GCS client;
no gcloud), without the immutable base_X matrix, into a new scratch/origin-ablation-20261030/harvest/formal-hXX/trial-0
and check it. The temporary annual package (gcs-only/annual-package) IS downloaded: its replay is required before the
task-owned cleanup.

Checks: publication.json complete (no owner); trial succeeded / publication complete; recipe == uploaded config; image
digest == the origin build digest; source identifier == the composite overlay identifier; adapter features/pooled module
sha256 == the reviewed modules; the retained package verifies and routes ONLY the 2026 holdout context; the annual package
verifies and routes exactly the annual contexts; predictions == the pinned cohort (rows, 2026 holdout rows);
equivalence.json passed with the inherited CH contract, the origin gate and the pre-fit A2 score pairing all passed; actual
fits (fit_ledger contexts == the final gate's scheduled contexts with the PINNED original-only training rows / key digests,
zero copies, the gate's scored rows; q2..q5 regressors per context across the two packages; scalar_fits = 4 x contexts);
saved fitting memberships contain originals only and equal the pinned key digests; origin comparison files, pairing rows
== cohort with 0 unmatched, origin.* metrics; 20 report rows and report.* metrics; region_mapping.csv == frozen pairing map
and report_region_mapping.csv == the report-only map; registered model, version 1 and DatasetInput name/digest == the final
offline render.

  cd $W/control-plane-origin-ablation && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $W/envs/mlflow-svc/bin/python -B harvest_formal.py H --out RECEIPT.json
"""
import hashlib, json, os, sys

import numpy as np
import pandas as pd

W = "/home/swl007007/projects/food-crisis-research"
HERE = os.path.dirname(os.path.abspath(__file__))
TASK = "/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational/.trellis/tasks/10-30-ipcch-validity-origin-ablation"
S = f"{W}/staging/ipcch-origin-ablation-20261030"
MODULE_SHA = {"research_cloud/training/ipcch_validity_features.py": "eace18fd6b6bdfd1304cbe9c50d034fc9f5fcc770b2edc14b5a109b000d9c0a6",
              "research_cloud/training/ipcch_validity_pooled.py": "d2c07d7d0d5527a8da788edf98ad0ca1b05c182e0bef920f1683c1c301c4de0f"}
CODE_OVERLAY = json.load(open(os.path.join(HERE, "objects.json")))["code_overlay_tag"]   # restated from the origin build
ORIGIN_FILES = ("origin_comparison.json", "origin_comparison.csv", "origin_tui.csv")
GATES = f"{S}/check/gates-r2"
N_CONTEXTS = {0: 4, 6: 4, 12: 3}
OLD_MAP, NEW_MAP = "18ab5099ce2d1154fb5686183ee399124e18427cc1594923f7abe2769da1611d", "5d1fd7f8b0dbf5e43e9644280bab7e521da6b9897531cba4fc1479f8deef5676"
SKIP = "gcs-only/dataset/base_X_h{h:02d}.npy"   # immutable feature matrix: not read by publication, replay or recompute


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def keys_sha(admin, target):
    k = np.ascontiguousarray(np.column_stack([np.asarray(admin, np.int64), np.asarray(target, np.int64)]))
    return hashlib.sha256(str(k.dtype).encode() + str(k.shape).encode() + k.tobytes()).hexdigest()


def fits(trial, h, t, cfg, pkg, ann):
    """Actual fitted contexts against the final gate schedule and the recipe's pinned original-only memberships."""
    gate = json.load(open(f"{GATES}/final-h{h:02d}/gate.json"))["assertions"]
    pins = cfg["origin_ablation"]["fit_counts"]
    led = pd.read_csv(os.path.join(trial, "contexts", "fit_ledger.csv"))
    ctx = list(gate)
    w = {}
    for root in ("package", "gcs-only/annual-package"):
        for c in os.listdir(os.path.join(trial, root, "weights")):
            w[c] = sorted(os.listdir(os.path.join(trial, root, "weights", c)))
    rows = pd.read_csv(os.path.join(trial, "contexts", "arm_rows.csv.gz"))
    kind, admin, target = rows["label_kind"].to_numpy(dtype=object), rows["admin_code"].to_numpy(), rows["target_ord"].to_numpy()
    members = dict(np.load(os.path.join(trial, "contexts", "memberships.npz")))
    mem_ok = all((kind[members[f"{c}|backbone|train"]] == "original").all()
                 and keys_sha(admin[members[f"{c}|backbone|train"]], target[members[f"{c}|backbone|train"]]) == pins[c]["train_keys_sha256"]
                 and len(members[f"{c}|backbone|train"]) == pins[c]["train_rows"] for c in ctx)
    ok = (len(ctx) == N_CONTEXTS[h] and list(led["context"]) == ctx and set(led["role"]) == {"backbone"} and sorted(pins) == sorted(ctx)
          and all(r.train_keys_sha256 == pins[r.context]["train_keys_sha256"] == gate[r.context]["train_keys_sha256"]
                  and int(r.train_rows) == pins[r.context]["train_rows"] == gate[r.context]["train_rows"] and int(r.train_copies) == 0
                  and int(r.predicted_rows) == gate[r.context]["score_rows"] for r in led.itertuples())
          and sorted(w) == sorted(ctx) and all({f"q{k}.ubj" for k in (2, 3, 4, 5)} <= set(x) for x in w.values())
          and pkg["routing"]["contexts"] == [c for c in ctx if "_supp_" in c] and ann["routing"]["contexts"] == [c for c in ctx if "_supp_" not in c]
          and pkg.get("fitted_units") + ann.get("fitted_units") == len(ctx) and (t.get("identity") or {}).get("contexts") == ctx
          and (t.get("identity") or {}).get("scalar_fits") == 4 * len(ctx) and (t.get("metrics") or {}).get("scalar_fits") == 4 * len(ctx)
          and mem_ok)
    return ok, {"contexts": list(led["context"]), "train_rows": dict(zip(led["context"], map(int, led["train_rows"]))),
                "train_copies": int(led["train_copies"].sum()), "memberships_exact": bool(mem_ok),
                "retained_package_contexts": pkg["routing"]["contexts"], "annual_package_contexts": ann["routing"]["contexts"],
                "scalar_fits_packaged": sum(4 for x in w.values() if {f"q{k}.ubj" for k in (2, 3, 4, 5)} <= set(x))}


def download(src, trial, skip):
    from google.cloud import storage
    bucket_name, _, prefix = src[5:].partition("/")
    client = storage.Client(project="food-crisis-modeling-enso", client_options={"quota_project_id": "food-crisis-modeling-enso"})
    bucket = client.bucket(bucket_name)
    objects = []
    try:
        for b in client.list_blobs(bucket_name, prefix=prefix + "/"):
            rel = b.name[len(prefix) + 1:]
            if rel == skip:
                objects.append({"name": b.name, "generation": b.generation, "size": b.size, "crc32c": b.crc32c, "md5": b.md5_hash,
                                "not_downloaded": "immutable feature matrix; retained in GCS"})
                continue
            path = os.path.join(trial, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            bucket.blob(b.name, generation=b.generation).download_to_filename(path, checksum="crc32c")
            objects.append({"name": b.name, "generation": b.generation, "size": b.size, "crc32c": b.crc32c, "md5": b.md5_hash,
                            "local_bytes": os.path.getsize(path)})
            if os.path.getsize(path) != b.size:
                return objects, 1, f"size mismatch {rel}"
        return objects, 0, ""
    except Exception as e:
        return objects, 1, f"{type(e).__name__}: {e}"


def main(h, out):
    from research_cloud.packages.common import verify_package
    if os.path.exists(out):
        raise SystemExit(f"{out} exists; harvest once")
    op = f"ipcch-origin-ablation-r1-formal-h{h:02d}"
    final = json.load(open(f"{W}/ledger/vertex/{op}/final.json"))
    if final.get("state") != "JOB_STATE_SUCCEEDED":
        raise SystemExit(f"H{h}: job state {final.get('state')}; not harvested")
    digest = open(f"{TASK}/research/cp2/build/02-digest.txt").read().strip()
    overlay = json.load(open(f"{S}/image-overlay-origin/overlay/overlay-manifest.json"))
    expect = json.load(open(os.path.join(HERE, "render-final", "render-check.json")))["horizons"][str(h)]
    job = final["name"].rsplit("/", 1)[1]
    dest = f"{W}/scratch/origin-ablation-20261030/harvest/formal-h{h:02d}"
    os.makedirs(dest)
    src = f"gs://food-crisis-modeling-enso-research-artifacts/trials/ipcch_validity_pooled/{job}/trial-0"
    trial = os.path.join(dest, "trial-0")
    objects, rc, err = download(src, trial, SKIP.format(h=h))
    files = [os.path.join(r, n) for r, _, ns in os.walk(trial) for n in ns]
    rec = {"horizon": h, "job": final["name"], "job_id": job, "source": src, "trial_dir": trial, "cp_rc": rc, "cp_error": err[-600:],
           "files": len(files), "bytes": sum(os.path.getsize(f) for f in files), "objects": objects, "ok": False}
    if rc == 0 and len(files) == len([o for o in objects if "not_downloaded" not in o]) and sum("not_downloaded" in o for o in objects) == 1:
        pub = json.load(open(os.path.join(trial, "publication.json")))
        t, cfg = pub["trial"], json.load(open(os.path.join(HERE, "objects", f"config-formal-h{h:02d}.json")))
        p = pd.read_csv(os.path.join(trial, "predictions.csv.gz"), usecols=["period", "target_ord"])
        eq = json.load(open(os.path.join(trial, "equivalence.json")))
        rep = json.load(open(os.path.join(trial, "report_tables.json")))
        comp = json.load(open(os.path.join(trial, "origin_comparison.json")))
        adapter = ((t.get("trial_code") or {}).get("adapter") or {}).get("files") or {}
        pkg = json.load(open(os.path.join(trial, "package", "package.json")))
        ann = json.load(open(os.path.join(trial, "gcs-only", "annual-package", "package.json")))
        fits_ok, rec["fits"] = fits(trial, h, t, cfg, pkg, ann)
        o = eq.get("origin_ablation") or {}
        m = t.get("metrics") or {}
        rec["checks"] = {
            "publication": pub.get("status") == "complete" and not pub.get("owner"),
            "trial": (t.get("status"), t.get("fit_status"), t.get("publication_status")) == ("succeeded", "succeeded", "complete"),
            "recipe_equal": json.dumps(t.get("config"), sort_keys=True) == json.dumps(cfg, sort_keys=True),
            "image_ok": t["runtime"].get("image_digest") == digest,
            "source_commit_composite": t["runtime"].get("source_commit") == overlay["source_commit_env"],
            "adapter_module_sha": all(adapter.get(k) == v for k, v in MODULE_SHA.items()),
            "retained_package_verifies": not verify_package(os.path.join(trial, "package")),
            "annual_package_verifies": not verify_package(os.path.join(trial, "gcs-only", "annual-package")),
            "rows": len(p) == cfg["cohort"]["final_rows"] and int((p["period"] == "supplement").sum()) == cfg["cohort"]["holdout_rows"],
            "gates_passed": bool(eq.get("passed")) and not eq.get("differing") and bool((eq.get("ch_correction") or {}).get("passed"))
                            and bool(o.get("passed")) and bool((o.get("score_pairing") or {}).get("passed")) and "corrected_input" not in eq,
            "fits": fits_ok,
            "origin_outputs": all(os.path.exists(os.path.join(trial, f)) for f in ORIGIN_FILES)
                              and comp["pairing"]["rows"] == cfg["cohort"]["final_rows"] and comp["pairing"]["unmatched"] == 0
                              and any(k.startswith("origin.") for k in m) and "historical_pooled.binary_f1" in m,
            "report_rows": len(rep["rows"]) == 20,
            "report_metrics": any(k.startswith("report.region.") for k in m),
            "maps": sha(os.path.join(trial, "region_mapping.csv")) == OLD_MAP and sha(os.path.join(trial, "report_region_mapping.csv")) == NEW_MAP,
            "code_overlay_tag": (t.get("config") or {}).get("provenance_tags", {}).get("provenance.code_overlay") == CODE_OVERLAY
                                and digest in CODE_OVERLAY and all(v in CODE_OVERLAY for v in MODULE_SHA.values()),
            "names_and_dataset": (pub.get("registered_model"), str(pub.get("model_version")), (pub.get("dataset_input") or {}).get("name"),
                                  (pub.get("dataset_input") or {}).get("digest"), (pub.get("dataset_input") or {}).get("action"))
                                 == (expect["names"]["registered_model"], "1", expect["dataset"]["name"], expect["dataset"]["digest"], "logged")}
        rec["code_overlay_tag"] = (t.get("config") or {}).get("provenance_tags", {}).get("provenance.code_overlay")
        rec.update(run_id=pub.get("run_id"), model_id=pub.get("model_id"), registered_model=pub.get("registered_model"),
                   model_version=pub.get("model_version"), elapsed_seconds=(t.get("identity") or {}).get("elapsed_seconds"),
                   ok=all(rec["checks"].values()))
    json.dump(rec, open(out, "w"), indent=1, default=str)
    print(json.dumps({k: rec.get(k) for k in ("horizon", "job_id", "trial_dir", "files", "bytes", "run_id", "model_id", "ok")}, default=str))
    return 0 if rec["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]), sys.argv[sys.argv.index("--out") + 1]))
