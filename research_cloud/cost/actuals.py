"""Read-only usage facts for the revised quote: what was actually created and run in food-crisis-modeling-enso.

Metadata only - names, states, sizes, machine types and times; never secret payloads. Every call pins the project
(URL + ``x-goog-user-project``). The Earth Engine bucket ``food-crisis-modeling-enso-han`` is excluded (not part of
this migration; not read).

  python -m research_cloud.cost.actuals --out ACTUALS.json
"""
import argparse
import datetime
import json
import sys

PROJECT = "food-crisis-modeling-enso"
REGION = "us-central1"
EXCLUDED_BUCKETS = {"food-crisis-modeling-enso-han"}


def pages(api, url, key):
    out, token = [], None
    while True:
        sep = "&" if "?" in url else "?"
        status, body = api.call("GET", url + (f"{sep}pageToken={token}" if token else ""))
        if status != 200:
            raise SystemExit(f"GET {url.split('?')[0]} -> {status}")
        out += body.get(key, [])
        token = body.get("nextPageToken")
        if not token:
            return out


def seconds(a, b):
    if not a or not b:
        return None
    f = lambda t: datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))  # noqa: E731
    return round((f(b) - f(a)).total_seconds(), 1)


def collect(api):
    r = {"project": PROJECT, "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    sm = f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets"
    secrets = {}
    for s in pages(api, sm + "?pageSize=100", "secrets"):
        name = s["name"].rsplit("/", 1)[1]
        vs = pages(api, f"https://secretmanager.googleapis.com/v1/{s['name']}/versions?pageSize=100", "versions")
        secrets[name] = sorted(v["state"] for v in vs)
    r["secrets"] = {"secrets": len(secrets), "versions_by_state": {}, "per_secret": secrets}
    for states in secrets.values():
        for st in states:
            r["secrets"]["versions_by_state"][st] = r["secrets"]["versions_by_state"].get(st, 0) + 1
    builds = []
    for loc in ("global", REGION):
        url = (f"https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds?pageSize=100" if loc == "global" else
               f"https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/locations/{loc}/builds?pageSize=100")
        for b in pages(api, url, "builds"):
            builds.append({"location": loc, "status": b.get("status"), "machine": (b.get("options") or {}).get("machineType", "default"),
                           "seconds": seconds(b.get("startTime"), b.get("finishTime")), "create": b.get("createTime")})
    r["builds"] = {"count": len(builds), "minutes": round(sum(b["seconds"] or 0 for b in builds) / 60, 1), "rows": builds}
    repos = pages(api, f"https://artifactregistry.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/repositories", "repositories")
    r["artifact_registry"] = [{"name": x["name"].rsplit("/", 1)[1], "format": x.get("format"),
                               "size_bytes": int(x.get("sizeBytes", 0))} for x in repos]
    buckets = []
    for b in pages(api, f"https://storage.googleapis.com/storage/v1/b?project={PROJECT}&maxResults=100", "items"):
        if b["name"] in EXCLUDED_BUCKETS:
            buckets.append({"name": b["name"], "excluded": "Earth Engine workload, not read"})
            continue
        objs = pages(api, f"https://storage.googleapis.com/storage/v1/b/{b['name']}/o?maxResults=1000&fields="
                     "nextPageToken,items(size)", "items")
        buckets.append({"name": b["name"], "location": b.get("location"), "class": b.get("storageClass"),
                        "soft_delete_s": (b.get("softDeletePolicy") or {}).get("retentionDurationSeconds"),
                        "objects": len(objs), "bytes": sum(int(o["size"]) for o in objs)})
    r["gcs"] = buckets
    status, svc = api.call("GET", f"https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/research-mlflow")
    t = svc.get("template", {}) if status == 200 else {}
    r["cloud_run"] = {"status": status, "scaling": t.get("scaling"), "max_concurrency": t.get("maxInstanceRequestConcurrency"),
                      "resources": [c.get("resources") for c in t.get("containers", [])], "revision": svc.get("latestReadyRevision")}
    status, sql = api.call("GET", f"https://sqladmin.googleapis.com/v1/projects/{PROJECT}/instances")
    r["cloud_sql"] = [{"name": i["name"], "tier": i["settings"].get("tier"), "disk_gb": i["settings"].get("dataDiskSizeGb"),
                       "edition": i["settings"].get("edition"), "availability": i["settings"].get("availabilityType"),
                       "backup": {k: (i["settings"].get("backupConfiguration") or {}).get(k) for k in
                                  ("enabled", "pointInTimeRecoveryEnabled", "transactionLogRetentionDays")},
                       "ipv4": (i["settings"].get("ipConfiguration") or {}).get("ipv4Enabled")}
                      for i in (sql.get("items", []) if status == 200 else [])]
    va = f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}"
    jobs = []
    for j in pages(api, va + "/customJobs?pageSize=100", "customJobs"):
        pool = j["jobSpec"]["workerPoolSpecs"][0]
        jobs.append({"kind": "custom", "id": j["name"].rsplit("/", 1)[1], "display": j.get("displayName"), "state": j.get("state"),
                     "machine": pool["machineSpec"]["machineType"], "seconds": seconds(j.get("startTime"), j.get("endTime")),
                     "create": j.get("createTime")})
    for j in pages(api, va + "/hyperparameterTuningJobs?pageSize=100", "hyperparameterTuningJobs"):
        jobs.append({"kind": "hpt", "id": j["name"].rsplit("/", 1)[1], "display": j.get("displayName"), "state": j.get("state"),
                     "machine": j["trialJobSpec"]["workerPoolSpecs"][0]["machineSpec"]["machineType"],
                     "seconds": seconds(j.get("startTime"), j.get("endTime")), "create": j.get("createTime"),
                     "trials": [{"id": t.get("id"), "state": t.get("state"), "seconds": seconds(t.get("startTime"), t.get("endTime"))}
                                for t in j.get("trials", [])]})
    r["vertex_jobs"] = sorted(jobs, key=lambda j: j["create"] or "")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    from research_cloud.deploy import provision_secrets as ps
    r = collect(ps.Api())
    json.dump(r, open(args.out, "w"), indent=1)
    print(json.dumps({"secrets": r["secrets"]["versions_by_state"], "builds": [r["builds"]["count"], r["builds"]["minutes"]],
                      "ar": r["artifact_registry"], "gcs": [(b["name"], b.get("objects"), b.get("bytes")) for b in r["gcs"]],
                      "run": r["cloud_run"], "sql": r["cloud_sql"],
                      "jobs": [(j["display"], j["kind"], j["state"], j["machine"], j["seconds"]) for j in r["vertex_jobs"]]},
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
