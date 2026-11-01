"""READ-ONLY: Earth Engine task status for the run's recorded task IDs, using the LOCAL operator EE credentials
(caller identity not established; NOT runtime telemetry). One getTaskStatus call, retries 0."""
import json, sys
import ee
ee.Initialize(project="feisty-flames-511718-d4"); ee.data.setDeadline(30000); ee.data.setMaxRetries(0)
d = json.load(open(sys.argv[1])); ids = [t["task_id"] for t in d["tasks"] if t.get("task_id")]
out = {"identity": "local operator EE credentials (caller not established), NOT the runtime SA", "task_ids": ids}
try:
    out["status"] = [{k: s.get(k) for k in ("id", "state", "description", "error_message", "destination_uris", "creation_timestamp_ms", "update_timestamp_ms")} for s in ee.data.getTaskStatus(ids)]
except Exception as exc:
    out["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
json.dump(out, open(sys.argv[2], "x"), indent=1, default=str)
print(json.dumps([(s.get("state"), (s.get("description") or "")[-45:]) for s in out.get("status", [])]) if "status" in out else out["error"])
