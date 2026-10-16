"""HPT attempt 3 harvest: Vertex trials vs MLflow runs vs trial.json, then the downloaded packages replayed in the pinned
training-ipcch fdbe6d1 image (bwrap sandbox, no network). Reads only (MLflow as ipcch-reader)."""
import datetime, hashlib, json, os, subprocess, sys
sys.path.insert(0, "/home/swl007007/projects/food-crisis-research/control-plane")
from research_cloud.images.rootfs_replay import sandbox
W = "/home/swl007007/projects/food-crisis-research"
H = f"{W}/scratch/hpt3-harvest"
final = json.load(open(f"{W}/ledger/vertex/ipcch-hpt2-3/final.json"))
spec = json.load(open(f"{W}/ledger/vertex/ipcch-hpt2-3/submit.json"))["body"]
env = {e["name"]: e["value"] for e in spec["trialJobSpec"]["workerPoolSpecs"][0]["containerSpec"]["env"]}
manifest_sha = hashlib.sha256(open(f"{W}/scratch/vertex/jobs/manifest-ipcch-h03.json", "rb").read()).hexdigest()
runs = json.load(open(f"{H}/runs.json"))
ts = lambda t: datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
out = {"job": final["name"].rsplit("/", 1)[1], "job_state": final["state"], "start": final["startTime"], "end": final["endTime"],
       "job_seconds": (ts(final["endTime"]) - ts(final["startTime"])).total_seconds(),
       "scheduling": spec["trialJobSpec"]["scheduling"], "parent_run": env["IPCCH_PARENT_RUN_ID"],
       "cap_note": "submitted with the 54c9ad6 launcher SIGALRM cap, which is ineffective for a PID-1 trial (fixed in "
                   "d9ede46); the trials' measured durations below stayed far inside 900 s, so no cap was exercised",
       "trials": []}
for t in final["trials"]:
    tid = t["id"]
    r = runs[tid]
    tj = json.load(open(f"{H}/trial-{tid}/trial.json"))
    vparams = {p["parameterId"]: p["value"] for p in t["parameters"]}
    vobj = t["finalMeasurement"]["metrics"][0]["value"]
    pkg = f"{H}/trial-{tid}/package"
    pj = hashlib.sha256(open(f"{pkg}/package.json", "rb").read()).hexdigest()
    checks = {
        "vertex_trial_succeeded": t["state"] == "SUCCEEDED",
        "mlflow_finished_and_succeeded": r["status"] == "FINISHED" and r["tags"].get("trial_status") == "succeeded",
        "parent_link": r["tags"].get("mlflow.parentRunId") == env["IPCCH_PARENT_RUN_ID"],
        "job_and_trial_ids": r["tags"].get("vertex.CLOUD_ML_JOB_ID") == out["job"] and r["tags"].get("vertex.CLOUD_ML_TRIAL_ID") == tid
                             and tj["runtime"]["vertex"] == {"CLOUD_ML_JOB_ID": out["job"], "CLOUD_ML_TRIAL_ID": tid},
        "image_digest_eq_spec": r["tags"].get("image_digest") == tj["runtime"]["image_digest"] == env["IPCCH_IMAGE_DIGEST"],
        "source_commit_fdbe6d1": r["tags"].get("source_commit", "").startswith("fdbe6d1") and tj["harness_code"]["control_plane_commit"].startswith("fdbe6d1"),
        "input_manifest_sha_eq_submitted": tj["input_manifest"]["sha256"] == manifest_sha,
        "params_vertex_eq_mlflow_eq_trial": all(float(r["params"][k]) == float(v) == float(tj["params"][k]) for k, v in vparams.items())
                                            and set(vparams) == set(r["params"]) == set(tj["params"]),
        "objective_vertex_eq_mlflow_eq_trial": vobj == r["crisis_f1"] == tj["metrics"]["crisis_f1"],
    }
    out["trials"].append({"trial": tid, "run_id": r["run_id"], "params": vparams, "crisis_f1": vobj,
                          "provider_seconds": (ts(t["endTime"]) - ts(t["startTime"])).total_seconds(),
                          "container_training_seconds": round(tj["finished"] - tj["started"], 1),
                          "package_json_sha256": pj, "checks": checks})
rootfs = f"{W}/scratch/image-pulls/training-ipcch-fdbe6d1.rootfs"
cfg = json.load(open(f"{W}/scratch/image-pulls/training-ipcch-fdbe6d1.config.json"))
for t in out["trials"]:
    pk, rd = f"{H}/trial-{t['trial']}", f"{H}/replay-trial-{t['trial']}"
    os.makedirs(rd, exist_ok=True)
    p = subprocess.run(sandbox(rootfs, cfg, pk, rd) + ["/usr/local/bin/python", "-m", "research_cloud.packages.replay",
                       "/packages/package", "--report", "/out/replay.json"], capture_output=True, text=True, timeout=1800)
    rep = json.load(open(f"{rd}/replay.json")) if os.path.exists(f"{rd}/replay.json") else {}
    t["replay"] = {"rc": p.returncode, "passed": rep.get("passed"), "rows": rep.get("rows"),
                   "image": "training-ipcch@" + env["IPCCH_IMAGE_DIGEST"][:19] + " (fdbe6d1)"}
out["ok"] = all(all(t["checks"].values()) and t["replay"]["passed"] is True for t in out["trials"]) and out["job_state"] == "JOB_STATE_SUCCEEDED"
json.dump(out, open(f"{H}/harvest.json", "w"), indent=1)
print(json.dumps({"ok": out["ok"], "job_seconds": out["job_seconds"], "trials": [{k: t[k] for k in ("trial", "crisis_f1", "provider_seconds",
      "container_training_seconds")} | {"failed_checks": [c for c, v in t["checks"].items() if not v], "replay": t["replay"]} for t in out["trials"]]}, indent=1))
