"""Origin-ablation job packet generator for task 10-30 (local only; no cloud call). Adapted from the task 10-28 CH packet
``staging/ipcch-ch-validity-20261028/job-packet-ch/make_packet.py``.

  plan                       cloud configs (the reviewed candidate/final-r2 recipes with ONLY provenance.code_overlay
                             restated from the actual build), data-object pins (byte-equal copies of the CH-final run's
                             retained predictions), reservations
  manifests --pred-generations G0 G6 G12
                             the three cloud manifests: the CH-final run's uploaded cloud manifest of the horizon (every
                             role generation-pinned, ch_links included) with ``baseline_predictions`` replaced by the
                             uploaded copy of the CH-final run's predictions
  specs --digest sha256:...  the three CustomJob bodies on the new image digest + offline admission checks
  render --stage draft|final offline publication output with the real publication code (card, tags, names, DatasetInput
                             including the saved-membership check on the expected original-only memberships)

Run from control-plane-origin-ablation with PYTHONDONTWRITEBYTECODE=1, PYTHONPATH=. and the tooling env.
"""
import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import sys
import tempfile

W = "/home/swl007007/projects/food-crisis-research"
HERE = os.path.dirname(os.path.abspath(__file__))
TASK = "/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational/.trellis/tasks/10-30-ipcch-validity-origin-ablation"
S = f"{W}/staging/ipcch-origin-ablation-20261030"
FINAL = f"{S}/candidate/final-r2"
GATES = f"{S}/check/gates-r2"
BUILD = f"{TASK}/research/cp2/build"
CONTEXT_RECORD, CONTEXT_RECORD_SHA256 = f"{S}/image-overlay-origin.context-record.json", "c98e85577ce655e3f5243306d9ee6c85a400dec3513044fe219140b0f18f0266"
CH = f"{W}/.trellis/tasks/10-28-ipcch-ch-validity-refits/research"
CH_MANIFESTS, CH_UPLOADS = f"{W}/staging/ipcch-ch-validity-20261028/job-packet-ch/objects", f"{CH}/cp4/02-uploads.json"
CH_HARVEST = f"{W}/scratch/ch-validity-20261028/harvest"
PROJECT = "food-crisis-modeling-enso"
INPUTS = f"{PROJECT}-research-inputs"
STORE = "training-jobs/ipcch-validity-origin-ablation/r1/inputs"
IMAGE = "us-central1-docker.pkg.dev/food-crisis-modeling-enso/research/training-ipcch-validity"
BASE_IMAGE = "training-ipcch-validity@sha256:fd921dd7add8933024c4765e1c93c382f4f8b4f0ffb2dddc24778daac83ca939"
CH_IMAGE_DIGEST = "sha256:2b18cf721cb09af0d1633a20087874155e8af49aa822979c0554507bcb68ccc3"
MACHINE, TIMEOUT_S = "n1-standard-16", 7200
ARM = "validity_augmented_idp_202610_acledagg_lag1_uncal_hpt"
CH_VERSION = "gosif-v3-input-20261027+ch-validity-20261028"
VERSION = CH_VERSION + "+original-label-fit-20261030"
FAMILY_TITLE = "Original-label fit ablation (GOSIF v3 + CH validity 20261028)"
CH_RUNS = {0: "298c4718b4d64e6f8a5c315e8c22d25d", 6: "00d4e94c824343bf86a0c2b79d5b9ed0", 12: "f436da15c71c469199784db065f3b63b"}
# The CH-final runs' retained predictions in the artifacts bucket (task 10-28 harvest receipts); the packet uploads byte-equal
# copies (size/MD5/CRC32C/sha256 checked) to the task store, as task 10-28 did (trainer read access to the artifacts bucket
# is not established).
CH_PRED = {0: {"job": "6867303963549499392", "generation": 1793220741490055, "bytes": 4668775, "md5": "Iij0wvsK+4d4Zo79EpfFkQ==", "crc32c": "B/HFzw=="},
           6: {"job": "3518877640599535616", "generation": 1793220033278325, "bytes": 3774651, "md5": "ARv12uagMlnbz6y5gBFhxg==", "crc32c": "jsYDZA=="},
           12: {"job": "8594997370599505920", "generation": 1793221084575375, "bytes": 3221416, "md5": "8bdaJfF4+L5iqYcR8Jb1fw==", "crc32c": "uvhS6A=="}}
DATA = {f"baseline_predictions_h{h:02d}": {
    "local": f"{CH_HARVEST}/formal-h{h:02d}/trial-0/predictions.csv.gz", "object": f"{STORE}/baseline-predictions-chfinal-h{h:02d}.csv.gz",
    "content_type": "application/gzip",
    "source": {**p, "uri": f"gs://{PROJECT}-research-artifacts/trials/ipcch_validity_pooled/{p['job']}/trial-0/predictions.csv.gz"}}
    for h, p in CH_PRED.items()}
OPS = {h: f"ipcch-origin-ablation-r1-formal-h{h:02d}" for h in (0, 6, 12)}
PLATFORM_OP, BUILD_OP, TASK_CAP, PLATFORM_LINE = "ipcch-origin-ablation-r1-platform", "ipcch-origin-ablation-r1-build", 7.00, 0.90
CODE_OVERLAY = "provenance.code_overlay"
MODULE_NOTES = {"research_cloud/training/dataset_input.py": "origin DatasetInput name, fit-subset tags and saved-membership check; publication only",
                "research_cloud/training/ipcch_validity_features.py": "the CH-final module, unchanged",
                "research_cloud/training/ipcch_validity_pooled.py": "fit-label policy, origin contract, gates, paired comparison and formal path"}
ALLOWED_DIFF = (f"provenance_tags.{CODE_OVERLAY}",)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def digests(path):
    import google_crc32c
    s, m, c, n = hashlib.sha256(), hashlib.md5(), google_crc32c.Checksum(), 0
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            s.update(b); m.update(b); c.update(b); n += len(b)
    return {"bytes": n, "sha256": s.hexdigest(), "md5": base64.b64encode(m.digest()).decode(),
            "crc32c": base64.b64encode(c.digest()).decode()}


def overlay():
    """(digest, composite source identifier, provenance.code_overlay value) from the ACTUAL build receipts only."""
    digest = open(f"{BUILD}/02-digest.txt").read().strip()
    summary = json.load(open(f"{BUILD}/03-build-summary.json"))
    if sha(CONTEXT_RECORD) != CONTEXT_RECORD_SHA256:
        raise SystemExit("the context record differs from the released build")
    rec = json.load(open(CONTEXT_RECORD))
    om = f"{S}/image-overlay-origin/overlay/overlay-manifest.json"
    if (summary["digest"], summary["status"], summary["tag"]) != (digest, "SUCCESS", rec["image_tag"].rsplit(":", 1)[1]) \
            or not all(summary["checks"].values()) or sha(om) != rec["files"]["overlay/overlay-manifest.json"] \
            or sha(om) != rec["overlay_manifest_sha256"] or sorted(rec["module_sha256"]) != sorted(MODULE_NOTES):
        raise SystemExit("build receipts, context record and overlay manifest disagree")
    source = json.load(open(om))["source_commit_env"]
    if source != rec["composite_source_commit"]:
        raise SystemExit("composite source identifier differs between the overlay manifest and the context record")
    mods = [f"{p} sha256 {rec['module_sha256'][p]} ({MODULE_NOTES[p]})" for p in sorted(MODULE_NOTES)]
    mods = ", ".join(mods[:-1]) + " and " + mods[-1]
    tag = (f"overlay manifest sha256 {rec['overlay_manifest_sha256']}; modules {mods}; image {IMAGE}@{digest} "
           f"(build {summary['build_id']}; source task/ipcch-validity-origin-ablation {rec['source_commit']}) = base {BASE_IMAGE} "
           "(control-plane 439a488) + these three modules")
    return digest, source, tag


def recipe(h):
    """The reviewed final-r2 origin-ablation recipe (gate-checked in check/gates-r2)."""
    return json.load(open(f"{FINAL}/formal-origin-h{h:02d}.json"))


def flat_diff(a, b):
    out = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if isinstance(x, dict) and isinstance(y, dict) and k in ("model_card", "provenance_tags"):
            out += [f"{k}.{j}" for j in sorted(set(x) | set(y)) if x.get(j) != y.get(j)]
        elif x != y:
            out.append(k)
    return out


def packet_config(h, tag):
    r = recipe(h)
    c = json.loads(json.dumps(r))
    if c["provenance_tags"].get(CODE_OVERLAY) == tag or CH_IMAGE_DIGEST not in c["provenance_tags"].get(CODE_OVERLAY, ""):
        raise SystemExit("the final recipe should carry the inherited CH-final provenance.code_overlay")
    c["provenance_tags"][CODE_OVERLAY] = tag
    if tuple(flat_diff(r, c)) != ALLOWED_DIFF:
        raise SystemExit(f"H{h}: packet config differs from the gate-checked recipe in {flat_diff(r, c)}, not exactly {ALLOWED_DIFF}")
    return c


def ch_manifest(h):
    """The CH-final run's cloud manifest of horizon h: local bytes equal to the uploaded object (task 10-28 receipt)."""
    rel = f"manifest-formal-h{h:02d}.json"
    up = next(o for o in json.load(open(CH_UPLOADS))["objects"] if o["key"] == rel)
    p = f"{CH_MANIFESTS}/{rel}"
    if sha(p) != up["local"]["sha256"] or not up["equal"]:
        raise SystemExit(f"{rel}: local CH manifest differs from its uploaded object")
    trial = json.load(open(f"{CH_HARVEST}/formal-h{h:02d}/trial-0/publication.json"))["trial"]
    if trial["input_manifest"]["sha256"] != up["local"]["sha256"]:
        raise SystemExit(f"{rel}: the CH-final run did not read this manifest")
    m = json.load(open(p))
    return m, {"name": m["name"], "uri": up["uri"], "gcs_generation": up["remote"]["generation"], "sha256": up["local"]["sha256"]}


def gate_view_pins(r):
    cc = r["ch_correction"]
    return {**cc["inputs"], "baseline_predictions": r["comparison"]["baseline_predictions"]}


def plan():
    from research_cloud.training import cloud_job
    from research_cloud.training import ipcch_validity_pooled as vp, model_metadata
    digest, _, tag = overlay()
    obj = os.path.join(HERE, "objects")
    os.makedirs(obj, exist_ok=True)
    rec = {"image": f"{IMAGE}@{digest}", "code_overlay_tag": tag, "data": {}, "configs": {}, "ch_final_manifests": {}}
    for role, d in DATA.items():
        dg = digests(d["local"])
        if any(dg[k] != d["source"][k] for k in ("bytes", "md5", "crc32c")):
            raise SystemExit(f"{role}: local copy differs from the CH-final run's GCS object")
        rec["data"][role] = {**d, **dg, "uri": f"gs://{INPUTS}/{d['object']}"}
    for h in OPS:
        r = recipe(h)
        pred = rec["data"][f"baseline_predictions_h{h:02d}"]["sha256"]
        if len({r["comparison"]["baseline_predictions"], r["origin_ablation"]["ch_baseline"]["predictions_sha256"], pred}) != 1:
            raise SystemExit(f"H{h}: recipe pins differ from the data objects")
        m, src = ch_manifest(h)
        if {k: v["sha256"] for k, v in m["files"].items() if k != "baseline_predictions"} != \
                {k: v for k, v in gate_view_pins(r).items() if k != "baseline_predictions"}:
            raise SystemExit(f"H{h}: the CH-final manifest's other roles differ from the inherited ch_correction.inputs")
        rec["ch_final_manifests"][h] = src
        p = os.path.join(obj, f"config-formal-h{h:02d}.json")
        c = packet_config(h, tag)
        tmp = p + ".local.json"
        json.dump(c, open(tmp, "w"), indent=1, sort_keys=True)
        json.dump(cloud_job.cloud_config(tmp), open(p, "w"), indent=1, sort_keys=True)
        os.remove(tmp)
        if json.load(open(p)) != c:
            raise SystemExit(f"H{h}: cloud config is not the reviewed packet config")
        vp.check_config(c, h, vp.HPT_ARM)
        model_metadata.validate_recipe(c, vp.FAMILY)
        rec["configs"][h] = {"rel": os.path.basename(p), "sha256": sha(p), "uri": f"gs://{INPUTS}/{STORE}/{os.path.basename(p)}",
                             "final_r2_recipe_sha256": sha(f"{FINAL}/formal-origin-h{h:02d}.json"),
                             "difference_from_final_r2_recipe": list(ALLOWED_DIFF), "code_overlay_tag": tag}
    json.dump(rec, open(os.path.join(HERE, "objects.json"), "w"), indent=1, sort_keys=True)
    json.dump(reservations(), open(os.path.join(HERE, "reservations.json"), "w"), indent=1)
    print(json.dumps(rec, indent=1))


def reservations():
    usd_h, disk = 0.8739954, 6.301369863013698e-05
    billed = TIMEOUT_S + 600
    per = {"compute_usd": usd_h * billed / 3600, "disk_usd": disk * 100 * billed / 3600}
    per["total_usd"] = per["compute_usd"] + per["disk_usd"]
    training = [{"pool": "training", "month": "2026-10", "operation": OPS[h], "usd": per["total_usd"],
                 "detail": {"machine": MACHINE, "trials": 1, "timeout_s": TIMEOUT_S, "overhead_s": 600, "boot_disk_gib": 100,
                            "boot_disk_type": "pd-standard", "usd_per_hour": usd_h, "disk_usd_per_gib_hour": disk, "kind": "custom",
                            "task": "10-30-ipcch-validity-origin-ablation", "price_source": "preflight Q1 2026-10-26T07:00:00Z (task 10-26; via 10-28)",
                            "horizon": h, "mode": "formal", "data_version": VERSION}} for h in OPS]
    items = [
        ("gcs_storage_inputs_outputs_mlflow", 4.0, "GiB (3 baseline copies 11.7 MB + 6 store objects + 3 formal trial prefixes incl. gcs-only and the temporary annual packages ~3.0 + MLflow copies ~0.6)", 0.02, "USD/GiB-month", 3, "E5F0-6A5D-7BAD"),
        ("gcs_class_a_writes", 2500, "ops (3 data + 6 store objects, 3 x 700 job/publication writes)", 5e-06, "USD/op", 1, "4DBF-185F-A415"),
        ("gcs_class_b_reads", 5000, "ops (job FUSE/input reads, harvest lists/gets, readback, UI)", 4e-07, "USD/op", 1, "7870-010B-2763"),
        ("gcs_internet_egress_harvest", 2.0, "GiB (downloads to WSL of 3 formal prefixes without the base_X matrices)", 0.12, "USD/GiB", 1, "22EB-AAE8-FBCD"),
        ("cloud_logging", 0.2, "GiB (3 job logs, MLflow request logs)", 0.5, "USD/GiB", 1, "143F-A1B0-E0BE"),
        ("cloud_run_mlflow_cpu", 3000, "vCPU-s (3 formal publications ~500 each + readback/UI 1,500)", 2.4e-05, "USD/vCPU-s", 1, "4856-B847-F1EB"),
        ("cloud_run_mlflow_memory", 6000, "GiB-s (2 GiB x 3,000 s)", 2.5e-06, "USD/GiB-s", 1, "02A2-9231-36A6"),
        ("cloud_run_mlflow_requests", 15000, "requests", 4e-07, "USD/request", 1, "2DA5-55D3-E679"),
        ("cloud_run_internet_egress_readback", 1.0, "GiB (MLflow artifact/UI downloads by the reader)", 0.105, "USD/GiB", 1, "DDFD-AE42-E219"),
        ("secret_manager_access", 6, "accesses (3 job-writer launcher reads + reader accesses)", 3e-06, "USD/access", 1, "EBA7-264F-2D2C")]
    rows = [{"item": i, "quantity": q, "unit": u, "rate": r, "rate_unit": ru, "months": m, "source": s, "usd": q * r * m}
            for i, q, u, r, ru, m, s in items]
    total = sum(x["usd"] for x in rows)
    platform = [{"pool": "platform", "month": "2026-10", "operation": PLATFORM_OP, "usd": PLATFORM_LINE,
                 "detail": {"scope": "job phase of task 10-30: uploads, three formal jobs' storage/publication, harvest, annual-package "
                                     "cleanup deletes (free), MLflow/UI readback (the build has its own line)",
                            "items": rows, "items_total_usd": total,
                            "basis": "gross list rates copied from the task 10-28 priced plan, free tiers ignored, 90-day storage, increment only; Cloud SQL/MLflow baseline excluded"}}]
    if total > PLATFORM_LINE:
        raise SystemExit(f"platform items exceed the {PLATFORM_LINE:.2f} line")
    tr = sum(e["usd"] for e in training)
    return {"month": "2026-10", "per_job": {**per, "billed_seconds_per_trial": billed}, "training": training,
            "training_total_usd": tr, "platform": platform,
            "task_total_usd": {"build_line": 0.19, "platform_line": PLATFORM_LINE, "training": tr, "total": 0.19 + PLATFORM_LINE + tr, "cap": TASK_CAP}}


def manifest_content(h, gens):
    """The origin cloud manifest of horizon h; ``gens`` maps data role -> created generation (None: draft render only)."""
    objs = json.load(open(os.path.join(HERE, "objects.json")))
    base, src = ch_manifest(h)
    files = dict(base["files"])
    old = files["baseline_predictions"]
    pred = objs["data"][f"baseline_predictions_h{h:02d}"]
    files["baseline_predictions"] = {"uri": pred["uri"], "sha256": pred["sha256"], "gcs_generation": gens and int(gens[f"baseline_predictions_h{h:02d}"])}
    if {k: v["sha256"] for k, v in files.items()} != gate_view_pins(recipe(h)):
        raise SystemExit(f"H{h}: manifest pins differ from the recipe's inherited inputs with the CH-final comparison input")
    return {"name": f"ipcch-validity-origin-ablation-r1-formal-h{h:02d}", "gcp_project": PROJECT, "files": files,
            "derived_from": {"ch_final_formal_manifest": src, "replaced_roles": {"baseline_predictions": old}}}


def manifests(gens):
    out = {}
    for h in OPS:
        m = manifest_content(h, gens)
        p = os.path.join(HERE, "objects", f"manifest-formal-h{h:02d}.json")
        if os.path.exists(p):
            raise SystemExit(f"{p} exists")
        json.dump(m, open(p, "w"), indent=1, sort_keys=True)
        out[h] = {"rel": os.path.basename(p), "sha256": sha(p)}
    print(json.dumps(out, indent=1))


def specs(digest):
    from research_cloud.training import cloud_job, vertex_submit
    if digest != overlay()[0]:
        raise SystemExit("the spec digest must be the actual origin-ablation build digest")
    out = os.path.join(HERE, "specs")
    os.makedirs(out)
    plan = json.load(open(os.path.join(HERE, "reservations.json")))
    check = {}
    for h in OPS:
        r = json.load(open(os.path.join(HERE, "objects", f"config-formal-h{h:02d}.json")))
        body = cloud_job.spec("research_cloud.training.ipcch_validity_pooled", f"{IMAGE}@{digest}", MACHINE,
                              f"/gcs/{INPUTS}/{STORE}/manifest-formal-h{h:02d}.json", f"/gcs/{INPUTS}/{STORE}/config-formal-h{h:02d}.json",
                              "ipcch_validity_pooled", TIMEOUT_S, entry="/usr/local/bin/train-entry", recipe=r)
        body["displayName"] = f"ipcch-origin-ablation-formal-h{h:02d}"
        body["labels"].update(task="ipcch-validity-origin-ablation", horizon=f"h{h:02d}")
        p = os.path.join(out, f"spec-formal-h{h:02d}.json")
        json.dump(body, open(p, "w"), indent=1)
        detail = next(e["detail"] for e in plan["training"] if e["operation"] == OPS[h])
        cloud_job.tracking_config(body, "custom")
        env = {e["name"]: e["value"] for e in body["jobSpec"]["workerPoolSpecs"][0]["containerSpec"]["env"]}
        check[h] = {"spec": os.path.basename(p), "sha256": sha(p), "operation": OPS[h],
                    "within_reservation_problems": vertex_submit.within_reservation(body, "custom", detail),
                    "tracking_config": "ok", "image": body["jobSpec"]["workerPoolSpecs"][0]["containerSpec"]["imageUri"],
                    "env_image_digest": env["IPCCH_IMAGE_DIGEST"] == digest,
                    "env_model_card_equal": json.loads(env["IPCCH_MODEL_RECIPE"])["model_card"] == r["model_card"]}
    json.dump(check, open(os.path.join(HERE, "specs-check.json"), "w"), indent=1)
    print(json.dumps(check, indent=1))


# ---- offline publication render: card/name/tag/DatasetInput output checks on the final configs ----

SAMENESS = re.compile(r"\b(only|identical|same|unchanged|equal|equals|otherwise|every other|preserved|not refitted|keeps?)\b", re.I)
LABELISH = re.compile(r"label|cohort|histor|cop(y|ies)|fitting|schedule|membership|keyed|keys|rows|report famil", re.I)
# Texts that are false for this ablation wherever they would appear (inherited CH-final statements about copy training,
# the GOSIF-v3 comparison or its predictions as the comparison input).
FORBIDDEN = ("training and evaluation rows include", "Versus the linked GOSIF-v3 run", "common support with the GOSIF-v3 run",
             "compared on common keys", "every eligible label up to the cutoff", "with baseline_predictions = the GOSIF-v3 run's retained predictions",
             "only the declared feature suffix differs", "same keyed cohort")


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.;])\s+|\n+", text) if s.strip()]


def expected_memberships(h):
    """The original-only fitting memberships derived from the CH-final run's saved memberships and label kinds (equal to the
    gate pins; verify_nofit proves it) plus its scored rows: a faithful stand-in for the job's memberships.npz."""
    import numpy as np
    import pandas as pd
    T = f"{CH_HARVEST}/formal-h{h:02d}/trial-0"
    kind = pd.read_csv(f"{T}/contexts/arm_rows.csv.gz")["label_kind"].to_numpy(dtype=object)
    m = dict(np.load(f"{T}/contexts/memberships.npz"))
    return {k: (v[kind[v] == "original"].astype(np.int32) if k.endswith("|backbone|train") else v) for k, v in m.items()}


def offline_root(h, tmp):
    import numpy as np
    import pandas as pd
    g = f"{GATES}/final-h{h:02d}/dataset"
    os.makedirs(f"{tmp}/contexts"); os.makedirs(f"{tmp}/dataset"); os.makedirs(f"{tmp}/package/deps")
    for rel in ("labels.csv.gz", f"idp_local_ledger_h{h:02d}.csv.gz"):
        os.symlink(f"{g}/{rel}", f"{tmp}/dataset/{rel}")
    os.symlink(f"{g}/feature_order_h{h:02d}.csv", f"{tmp}/package/deps/feature_order.csv")
    lab = pd.read_csv(f"{g}/labels.csv.gz", keep_default_na=False, na_values=[""],
                      usecols=["admin_code", "month_ord", "label_kind", "source_family", "source_available_ord"])
    rows = pd.DataFrame({"row": np.arange(len(lab)), "admin_code": lab["admin_code"], "target_ord": lab["month_ord"],
                         "label_kind": lab["label_kind"], "source_family": lab["source_family"],
                         "source_available_ord": lab["source_available_ord"]})
    text = rows.to_csv(index=False)
    with gzip.open(f"{tmp}/contexts/arm_rows.csv.gz", "wt") as f:
        f.write(text)
    np.savez_compressed(f"{tmp}/contexts/memberships.npz", **expected_memberships(h))
    return hashlib.sha256(text.encode()).hexdigest()


def render(stage):
    from research_cloud.training import dataset_input, model_metadata, publication
    digest, source, tag = overlay()
    out = os.path.join(HERE, f"render-{stage}")
    os.makedirs(out)
    pins = json.load(open(f"{TASK}/research/cp0/cp0-pins.json"))["baseline_runs"]
    report = {"stage": stage, "image": f"{IMAGE}@{digest}", "horizons": {}}
    for h in OPS:
        cfg = json.load(open(os.path.join(HERE, "objects", f"config-formal-h{h:02d}.json")))
        mpath = os.path.join(HERE, "objects", f"manifest-formal-h{h:02d}.json")
        manifest = ({"sha256": sha(mpath), "content": json.load(open(mpath))} if stage == "final"
                    else {"sha256": "draft (generations pending upload)", "content": manifest_content(h, None)})
        cpub = json.load(open(f"{CH_HARVEST}/formal-h{h:02d}/trial-0/publication.json"))
        record = {"config": cfg, "identity": {"family": "ipcch_validity_pooled", "mode": "formal", "arm": ARM, "horizon": h,
                                              "data_version": VERSION, "note": "offline render; the job records its own identity"},
                  "runtime": {"gcp_project": PROJECT, "image_digest": digest, "source_commit": source},
                  "resolved_params": cpub["trial"]["resolved_params"], "input_manifest": manifest, "metrics": {},
                  "output": f"gs://{PROJECT}-research-artifacts/trials/ipcch_validity_pooled/OFFLINE-RENDER/trial-0",
                  "harness_code": {"control_plane_commit": source}, "trial_code": "recorded by the job"}
        with tempfile.TemporaryDirectory() as tmp:
            arm_rows_sha = offline_root(h, tmp)
            tags, full = model_metadata.build(record, __import__("pathlib").Path(tmp) / "package", "<run_id>", "<model_id>")
            card = model_metadata.validate_recipe(cfg, "ipcch_validity_pooled")
            run_name, model_name, registered = publication.names(card, h, "<publication.identity>")
            p = dataset_input.payload(tmp, record, generation=lambda uri: "<created by the job>")
        open(os.path.join(out, f"model-card-h{h:02d}.md"), "w").write(full)
        json.dump({"names": {"run": run_name, "logged_model": model_name, "registered_model": registered},
                   "tags": tags, "dataset_input": p}, open(os.path.join(out, f"publication-h{h:02d}.json"), "w"), indent=1, sort_keys=True)
        b = pins[f"{h:02d}"]
        texts = [full, *map(str, tags.values()), *map(str, p["input_tags"].values()), p["dataset"]["name"], run_name, model_name, registered]
        blob = "\n".join(texts)
        flagged = sorted({s for t in texts for s in sentences(t) if SAMENESS.search(s) and LABELISH.search(s)})
        fc = cfg["origin_ablation"]["fit_counts"]
        checks = {
            "registered_name": registered == f"IPCCH {FAMILY_TITLE} | {ARM} | {h}-month" and registered != b["registered_model"],
            "run_and_model_names_new": run_name == f"{FAMILY_TITLE} | {ARM} | {h}-month" and model_name == f"{run_name} | seed 42"
                                       and cpub["trial"]["config"]["model_card"]["family_title"] not in run_name,
            "code_overlay_tag_from_build": tags.get(CODE_OVERLAY) == tag and digest in tag and all(
                m in tag for m in json.load(open(CONTEXT_RECORD))["module_sha256"].values()),
            "no_ch_final_image_or_changed_modules": not any(x in blob for x in (CH_IMAGE_DIGEST[7:23], "d7f78e3a8a10fd83", "a6d05b24759e60f4")),
            "baseline_tags_ch_final_run": all(tags.get(f"baseline.{k}") == str(b[k]) for k in ("run_id", "model_id", "registered_model", "model_version"))
                                          and tags.get("baseline.arm") == ARM and b["run_id"] == CH_RUNS[h],
            "family_and_versions": tags.get("family_title") == FAMILY_TITLE and tags.get("provenance.data_version") == CH_VERSION
                                   and tags.get("provenance.origin_ablation", "").startswith(VERSION)
                                   and tags.get("status") == "research_not_accepted" and tags.get("lead_months") == f"{h:02d}",
            "dataset_name": p["dataset"]["name"] == f"IPCCH validity ({VERSION}) | {ARM} | H{h:02d} | modeling panel index"
                            and p["dataset"]["name"] != cpub["dataset_input"]["name"],
            "dataset_digest_is_the_inherited_panel": arm_rows_sha == cfg["ch_correction"]["self_consistency"]["arm_rows_csv_sha256"]
                                                     and p["dataset"]["digest"] == arm_rows_sha[:32] == cpub["dataset_input"]["digest"],
            "dataset_fit_subset_tags": p["input_tags"]["fit_labels"] == "original_only"
                                       and json.loads(p["input_tags"]["fit_rows_by_context"]) == {c: v["train_rows"] for c, v in fc.items()}
                                       and p["input_tags"]["ablation_baseline.run_id"] == CH_RUNS[h],
            "no_forbidden_text": not any(f.lower() in blob.lower() for f in FORBIDDEN),
        }
        report["horizons"][h] = {"checks": checks, "ok": all(checks.values()),
                                 "names": {"run": run_name, "logged_model": model_name, "registered_model": registered},
                                 "dataset": {k: p["dataset"][k] for k in ("name", "digest")},
                                 "label_kind_counts": json.loads(p["input_tags"]["label_kind_counts"]),
                                 "forbidden_found": [f for f in FORBIDDEN if f.lower() in blob.lower()],
                                 "sameness_sentences_for_review": flagged}
    report["ok"] = all(v["ok"] for v in report["horizons"].values())
    json.dump(report, open(os.path.join(out, "render-check.json"), "w"), indent=1)
    print(json.dumps({h: {"ok": v["ok"], **{k: x for k, x in v["checks"].items() if not x}} for h, v in report["horizons"].items()}, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    m = sub.add_parser("manifests")
    m.add_argument("--pred-generations", nargs=3, required=True, metavar=("G0", "G6", "G12"))
    s = sub.add_parser("specs")
    s.add_argument("--digest", required=True)
    r = sub.add_parser("render")
    r.add_argument("--stage", choices=("draft", "final"), required=True)
    a = ap.parse_args()
    if a.cmd == "plan":
        plan()
    elif a.cmd == "manifests":
        manifests({f"baseline_predictions_h{h:02d}": g for h, g in zip(OPS, a.pred_generations)})
    elif a.cmd == "specs":
        specs(a.digest)
    else:
        sys.exit(render(a.stage))
