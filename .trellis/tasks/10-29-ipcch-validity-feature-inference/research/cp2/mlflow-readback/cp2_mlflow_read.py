"""CP2 live MLflow readback (GET only; mlflow-reader secret kept in memory, never echoed/persisted).
Usage: python cp2_mlflow_read.py HARVEST_RECEIPT.json [...] > out.json
For each harvested receipt: run get (status/lifecycle/experiment/dataset inputs), registered model version 1 get,
logged model get, and compare to the harvested publication identity."""
import base64, json, socket, subprocess, sys, urllib.error, urllib.parse, urllib.request
URL = "https://mlflow.weilunshi.com"
p = subprocess.run(["gcloud", "secrets", "versions", "access", "latest", "--secret=mlflow-reader",
                    "--project=food-crisis-modeling-enso"], capture_output=True, text=True, timeout=120)
log = {"secret_read": {"exit": p.returncode, "stderr_head": p.stderr.strip()[:200]}, "method": "GET only"}
if p.returncode != 0:
    print(json.dumps(log, indent=1)); sys.exit(1)
c = json.loads(p.stdout); auth = "Basic " + base64.b64encode(f"{c['username']}:{c['password']}".encode()).decode()
log["identity_username"] = c["username"]; del c, p
socket.setdefaulttimeout(30)
def get(path, **q):
    u = URL + path + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization": auth}, method="GET"), timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, {"error": e.read()[:300].decode(errors="replace")}
    except (socket.timeout, urllib.error.URLError) as e: return None, {"error": repr(e)[:200]}
ok_all = True
log["horizons"] = {}
for path in sys.argv[1:]:
    rec = json.load(open(path)); rid, mid, name = rec["run_id"], rec["model_id"], rec["registered_model"]
    out = {"receipt": path, "run_id": rid, "model_id": mid, "registered_model": name}
    st, d = get("/api/2.0/mlflow/runs/get", run_id=rid)
    out["run_status_http"] = st
    if st == 200:
        info, data = d["run"]["info"], d["run"].get("data", {})
        st2, ex = get("/api/2.0/mlflow/experiments/get", experiment_id=info["experiment_id"])
        ds = [{"name": x["dataset"].get("name"), "digest": x["dataset"].get("digest")} for x in (d["run"].get("inputs") or {}).get("dataset_inputs", [])]
        out.update(run_status=info.get("status"), lifecycle=info.get("lifecycle_stage"), run_name=info.get("run_name"),
                   experiment=ex.get("experiment", {}).get("name") if st2 == 200 else st2, n_metrics=len(data.get("metrics", [])),
                   dataset_inputs=ds)
    st, mv = get("/api/2.0/mlflow/model-versions/get", name=name, version="1")
    out["model_version_http"] = st
    if st == 200:
        v = mv["model_version"]; out["model_version"] = {k: v.get(k) for k in ("name", "version", "status", "run_id", "source", "model_id")}
    st, lm = get(f"/api/2.0/mlflow/logged-models/{mid}")
    out["logged_model_http"] = st
    if st == 200:
        m = lm.get("model", {}).get("info", {}); out["logged_model"] = {k: m.get(k) for k in ("model_id", "name", "status", "source_run_id", "experiment_id")}
    exp_ds = rec.get("dataset_input") or {}
    out["checks"] = {
        "run_finished_active": out.get("run_status") == "FINISHED" and out.get("lifecycle") == "active",
        "experiment": out.get("experiment") == "IPCCH dashboard",
        "version1_ready_bound": (out.get("model_version") or {}).get("status") == "READY" and (out.get("model_version") or {}).get("run_id") == rid,
        "logged_model_bound": (out.get("logged_model") or {}).get("model_id") == mid and (out.get("logged_model") or {}).get("source_run_id") == rid,
        "dataset_logged": len(out.get("dataset_inputs") or []) >= 1}
    out["ok"] = all(out["checks"].values()); ok_all &= out["ok"]
    log["horizons"][str(rec["horizon"])] = out
log["ok"] = ok_all
print(json.dumps(log, indent=1))
sys.exit(0 if ok_all else 1)
