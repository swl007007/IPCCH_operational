"""Task 10-31 cp5/runtime-final: local summary of the saved read-only outputs (no cloud calls)."""
import collections, csv, hashlib, io, json, os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))          # the guard runs from another cwd
O = "outputs/"
d = json.load(open(O + "01-exec-describe.json"))
c = d["spec"]["template"]["spec"]["containers"][0]
s = d["status"]
ex = {"name": d["metadata"]["name"], "job": d["metadata"]["labels"]["run.googleapis.com/job"],
      "creator": d["metadata"]["annotations"].get("run.googleapis.com/creator"),
      "image": c["image"], "args": c["args"], "limits": c["resources"]["limits"],
      "service_account": d["spec"]["template"]["spec"]["serviceAccountName"],
      "timeout_seconds": d["spec"]["template"]["spec"]["timeoutSeconds"],
      "max_retries": d["spec"]["template"]["spec"]["maxRetries"], "task_count": d["spec"]["taskCount"],
      "succeeded_count": s.get("succeededCount"), "failed_count": s.get("failedCount", 0),
      "cancelled_count": s.get("cancelledCount", 0), "running_count": s.get("runningCount", 0),
      "start": s.get("startTime"), "completion": s.get("completionTime"),
      "conditions": {x["type"]: [x["status"], x.get("message")] for x in s["conditions"]},
      "task_exit_code": "not reported by execution describe (success condition + succeededCount only)"}
ex["pins_ok"] = (ex["image"].endswith("acc3e4673fa7c133eade6e5c74b998706788e0d1af0f92b217ae74ce7e14ccf6")
                 and ex["service_account"].startswith("monthly-runtime@") and ex["limits"] == {"cpu": "8", "memory": "32Gi"}
                 and str(ex["timeout_seconds"]) == "14400" and ex["max_retries"] == 0 and "--v2-config" in ex["args"])
logs = json.load(open(O + "02-exec-logs.json"))
sev = collections.Counter(e.get("severity", "DEFAULT") for e in logs)
def text(e):
    return e.get("textPayload") or json.dumps(e.get("jsonPayload") or e.get("protoPayload") or {}, default=str)
notable = [{"ts": e.get("timestamp"), "severity": e.get("severity"), "text": text(e)[:600]}
           for e in logs if e.get("severity") in ("WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY")]
last = [{"ts": e.get("timestamp"), "severity": e.get("severity"), "text": text(e)[:300]} for e in logs[-3:]]
oct_ex = json.load(open(O + "05-exec-oct.json"))
active = lambda xs: [x["metadata"]["name"] for x in xs if (x.get("status") or {}).get("runningCount") or not (x.get("status") or {}).get("completionTime")]
wf = json.load(open(O + "07-wf.json"))
cur = json.load(open(O + "09-current-describe.json"))
post = json.load(open("../post-real.json"))
inv = json.load(open("../inventory-post-real.json"))["tables"]["gpp_availability_ledger"]
lb = open(O + "10-ledger.csv", "rb").read()
rows = list(csv.DictReader(io.StringIO(lb.decode())))
new = [r for r in rows if r["checked_at"] == "2026-11-01"]
body = {"execution": ex, "logs": {"entries": len(logs), "severity_counts": dict(sev), "warning_or_error": notable,
                                   "first_ts": logs[0].get("timestamp") if logs else None, "last": last},
        "reconciliation": {
            "locks_ls": {"exit": 1, "stderr": open(O + "03-locks.stderr").read().strip(), "objects": 0},
            "hold": {"exit": 1, "stderr": open(O + "04-hold.stderr").read().strip()},
            "oct_delivery_latest": [[x["metadata"]["name"], x["metadata"]["creationTimestamp"],
                                     (x.get("status") or {}).get("succeededCount"), (x.get("status") or {}).get("failedCount"),
                                     (x.get("status") or {}).get("completionTime")] for x in oct_ex],
            "oct_delivery_active": active(oct_ex),
            "monthly_prepare_executions_listed": len(json.load(open(O + "06-exec-prepare.json"))),
            "workflow_latest": [[w.get("name", "").split("/")[-1], w.get("state"), w.get("startTime"), w.get("endTime")] for w in wf],
            "workflow_active": [w.get("name") for w in wf if w.get("state") == "ACTIVE"],
            "batch_active_listed": len(json.load(open(O + "08-batch.json"))),
            "batch_stderr": open(O + "08-batch.stderr").read().strip()},
        "current": {"storage_url": cur["storage_url"], "generation": cur["generation"], "size": cur["size"],
                    "md5_hash": cur["md5_hash"], "crc32c_hash": cur["crc32c_hash"], "update_time": cur["update_time"],
                    "equals_readback_pinned_generation": cur["generation"] == post["post"]["generation"],
                    "readback_pointer_content": post["post"]["pointer"]},
        "gpp_ledger": {"content": inv["content"], "sha256": hashlib.sha256(lb).hexdigest(),
                       "sha_equals_post_inventory": hashlib.sha256(lb).hexdigest() == inv["content_sha256"],
                       "rows": len(rows), "probes_2026_11_01": [[r["month"], r["status"], json.loads(r["evidence"])] for r in new]}}
open(sys.argv[1], "x").write(json.dumps(body, indent=1, sort_keys=True, default=str))
print(json.dumps({"pins_ok": ex["pins_ok"], "succeeded": ex["succeeded_count"], "logs": dict(sev), "notable": len(notable),
                  "active": [body["reconciliation"][k] for k in ("oct_delivery_active", "workflow_active", "batch_active_listed")],
                  "current_eq": body["current"]["equals_readback_pinned_generation"],
                  "ledger_sha_ok": body["gpp_ledger"]["sha_equals_post_inventory"], "probes": len(new)}, indent=1))
