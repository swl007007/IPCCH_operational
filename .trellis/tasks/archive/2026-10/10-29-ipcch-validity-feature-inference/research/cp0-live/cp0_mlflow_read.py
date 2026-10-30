import json, subprocess, urllib.request, urllib.parse, base64, socket, sys
URL = "https://mlflow.weilunshi.com"
RUNS = ["298c4718b4d64e6f8a5c315e8c22d25d", "00d4e94c824343bf86a0c2b79d5b9ed0", "f436da15c71c469199784db065f3b63b"]
p = subprocess.run(["gcloud", "secrets", "versions", "access", "latest", "--secret=mlflow-reader",
                    "--project=food-crisis-modeling-enso"], capture_output=True, text=True, timeout=120)
log = {"secret_read": {"secret": "projects/food-crisis-modeling-enso/secrets/mlflow-reader/versions/latest",
                       "exit": p.returncode, "stderr_head": p.stderr.strip()[:200]}}
if p.returncode != 0:
    print(json.dumps(log, indent=1)); sys.exit(0)
c = json.loads(p.stdout); user = c["username"]; auth = "Basic " + base64.b64encode(f"{user}:{c['password']}".encode()).decode()
del c, p
log["identity_username"] = user
def get(path, **q):
    u = URL + path + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(u, headers={"Authorization": auth}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, {"error": e.read()[:300].decode(errors="replace")}
    except (socket.timeout, urllib.error.URLError) as e: return None, {"error": repr(e)[:200]}
socket.setdefaulttimeout(30)
st, cur = get("/api/2.0/mlflow/users/current"); log["users_current"] = {"status": st, "user": (cur.get("user") or {}).get("username") if st == 200 else cur}
log["runs"] = {}
for rid in RUNS:
    st, d = get("/api/2.0/mlflow/runs/get", run_id=rid)
    if st != 200: log["runs"][rid] = {"status": st, "body": d}; continue
    run = d["run"]; info = run["info"]; data = run.get("data", {})
    tags = {t["key"]: t["value"] for t in data.get("tags", [])}
    params = {t["key"]: t["value"] for t in data.get("params", [])}
    st2, ex = get("/api/2.0/mlflow/experiments/get", experiment_id=info["experiment_id"])
    st3, mv = get("/api/2.0/mlflow/model-versions/search", filter=f"run_id='{rid}'", max_results=50)
    log["runs"][rid] = {"status": st, "run_name": info.get("run_name"), "lifecycle": info.get("lifecycle_stage"),
        "run_status": info.get("status"), "experiment_id": info["experiment_id"],
        "experiment_name": ex.get("experiment", {}).get("name") if st2 == 200 else {"status": st2},
        "artifact_uri": info.get("artifact_uri"), "start_time": info.get("start_time"), "end_time": info.get("end_time"),
        "n_params": len(params), "n_tags": len(tags), "n_metrics": len(data.get("metrics", [])),
        "selected_tags": {k: v for k, v in tags.items() if any(s in k for s in ("horizon", "arm", "trial", "cutoff", "image", "context", "package", "source", "git", "mlflow.runName", "mlflow.source"))},
        "selected_params": {k: v for k, v in params.items() if any(s in k.lower() for s in ("horizon", "cutoff", "eta", "learning", "depth", "lambda", "alpha", "subsample", "colsample", "n_estimators", "min_child", "gamma", "rounds", "trial"))},
        "model_versions_search": {"status": st3, "versions": [{k: v.get(k) for k in ("name", "version", "current_stage", "status", "source", "run_id", "creation_timestamp")} for v in mv.get("model_versions", [])] if st3 == 200 else mv}}
print(json.dumps(log, indent=1))
