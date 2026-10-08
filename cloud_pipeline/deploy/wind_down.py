"""Stop exactly the listed task-owned cloud work before an authorization deadline.

Targets are explicit: Batch job names, Cloud Run job executions and Earth Engine
tasks whose description starts with an exact prepare ID (dashes as underscores).
Full raw JSON for every target is written create-only BEFORE any action (Batch
stops a job by deleting it). Commands are checked; post-action states are reported.
CANCEL_REQUESTED is pending, not a verified terminal state. No configuration,
resources or objects are removed. ``--backend rest`` uses the same Batch/Cloud Run v2 APIs through
Application Default Credentials when the gcloud CLI is unavailable (same selectors and evidence).

    python deploy/wind_down.py --project YOUR_PROJECT --location us-central1 \
        --batch-jobs YOUR_BATCH_JOB --run-executions YOUR_RUN_EXECUTION \
        --prepare-ids YOUR_PREPARE_ID --evidence-dir /private/wind-down-evidence [--execute]
"""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

TERMINAL_BATCH = {"SUCCEEDED", "FAILED"}
TERMINAL_EE = {"COMPLETED", "FAILED", "CANCELLED"}


def _run(command):
    """Full (untruncated) command result; persisted verbatim as evidence."""
    result = subprocess.run(command, capture_output=True, text=True)
    return {"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _describe(command):
    """{"command_result": full raw result, "document": parsed complete JSON or None}."""
    result = _run(command)
    document = None
    if result["returncode"] == 0:
        try:
            document = json.loads(result["stdout"])
        except ValueError:
            document = None
    return {"command_result": result, "document": document}


def _describe_batch(project, location, name):
    return _describe(["gcloud", "batch", "jobs", "describe", name, "--project", project, "--location", location,
                      "--format=json"])


def _describe_execution(project, location, name):
    return _describe(["gcloud", "run", "jobs", "executions", "describe", name, "--project", project, "--region",
                      location, "--format=json"])


class RestBackend:
    """Batch v1 / Cloud Run v2 REST with ADC; results shaped like the gcloud path's evidence."""

    def __init__(self, session=None):
        if session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            session = AuthorizedSession(credentials)
        self.session = session

    def _call(self, method, url):
        response = self.session.request(method, url)
        result = {"command": [method, url], "returncode": 0 if response.status_code < 300 else response.status_code,
                  "stdout": response.text, "stderr": ""}
        document = None
        if result["returncode"] == 0:
            try:
                document = json.loads(response.text) if response.text else {}
            except ValueError:
                document = None
        return {"command_result": result, "document": document}

    @staticmethod
    def _execution_url(project, location, name):
        job = name.rsplit("-", 1)[0]  # Cloud Run execution names are <job>-<suffix>
        return f"https://run.googleapis.com/v2/projects/{project}/locations/{location}/jobs/{job}/executions/{name}"

    def describe_batch(self, project, location, name):
        return self._call("GET", f"https://batch.googleapis.com/v1/projects/{project}/locations/{location}/jobs/{name}")

    def describe_execution(self, project, location, name):
        entry = self._call("GET", self._execution_url(project, location, name))
        raw = entry["document"]
        if isinstance(raw, dict):  # v2 fields mapped onto the v1 shape read by _execution_state
            entry["document"] = {"spec": {"taskCount": raw.get("taskCount", 1)},
                                 "status": {key: raw.get(key) or 0 for key in
                                            ("succeededCount", "failedCount", "cancelledCount")}
                                 | {"completionTime": raw.get("completionTime")}, "v2": raw}
        return entry

    def delete_batch(self, project, location, name):
        return self._call("DELETE", f"https://batch.googleapis.com/v1/projects/{project}/locations/{location}/jobs/{name}")[
            "command_result"]

    def cancel_execution(self, project, location, name):
        return self._call("POST", self._execution_url(project, location, name) + ":cancel")["command_result"]


class GcloudBackend:
    def describe_batch(self, project, location, name):
        return _describe_batch(project, location, name)

    def describe_execution(self, project, location, name):
        return _describe_execution(project, location, name)

    def delete_batch(self, project, location, name):
        return _run(["gcloud", "batch", "jobs", "delete", name, "--project", project, "--location", location, "--quiet"])

    def cancel_execution(self, project, location, name):
        return _run(["gcloud", "run", "jobs", "executions", "cancel", name, "--project", project, "--region", location,
                     "--quiet"])


def _batch_state(entry):
    document = entry["document"]
    return document.get("status", {}).get("state", "UNKNOWN") if isinstance(document, dict) else "UNKNOWN"


def _execution_state(entry):
    """TERMINAL from completionTime or task counts; RUNNING otherwise; UNKNOWN if undescribed."""
    document = entry["document"]
    if not isinstance(document, dict):
        return "UNKNOWN"
    status = document.get("status", {})
    tasks = document.get("spec", {}).get("taskCount", 1)
    finished = status.get("succeededCount", 0) + status.get("failedCount", 0) + status.get("cancelledCount", 0)
    return "TERMINAL" if status.get("completionTime") or finished >= tasks else "RUNNING"


def _ee_tasks(project, prepare_ids):
    import ee

    ee.Initialize(project=project)
    prefixes = tuple(f"{value.replace('-', '_')}_" for value in prepare_ids)
    return ee, [task for task in ee.data.getTaskList() if task.get("description", "").startswith(prefixes)]


def snapshot(args, backend):
    batch = {name: backend.describe_batch(args.project, args.location, name) for name in args.batch_jobs}
    runs = {name: backend.describe_execution(args.project, args.location, name) for name in args.run_executions}
    ee, tasks = _ee_tasks(args.project, args.prepare_ids)
    return ee, {"taken_at_utc": datetime.now(timezone.utc).isoformat(), "batch_jobs": batch,
                "run_executions": runs, "earth_engine_tasks": tasks}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--batch-jobs", default="")
    parser.add_argument("--run-executions", default="")
    parser.add_argument("--prepare-ids", default="")
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backend", choices=["gcloud", "rest"], default="gcloud")
    args = parser.parse_args()
    for field in ("batch_jobs", "run_executions", "prepare_ids"):
        setattr(args, field, [value for value in getattr(args, field).split(",") if value])
    evidence = Path(args.evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    backend = RestBackend() if args.backend == "rest" else GcloudBackend()
    ee, before = snapshot(args, backend)
    with (evidence / f"wind_down_before_{stamp}.json").open("x") as handle:
        json.dump(before, handle, indent=2, default=str)
    actions = []
    if args.execute:
        for name, job in before["batch_jobs"].items():
            state = _batch_state(job)
            if state not in TERMINAL_BATCH | {"UNKNOWN"}:
                actions.append(backend.delete_batch(args.project, args.location, name))
        for name, execution in before["run_executions"].items():
            if _execution_state(execution) == "RUNNING":
                actions.append(backend.cancel_execution(args.project, args.location, name))
        for task in before["earth_engine_tasks"]:
            if task.get("state") not in TERMINAL_EE | {"CANCEL_REQUESTED"}:
                try:
                    ee.data.cancelTask(task["id"])
                    actions.append({"cancel_ee_task": task["id"], "ok": True})
                except Exception as exc:  # recorded, not silenced
                    actions.append({"cancel_ee_task": task["id"], "ok": False, "error": str(exc)})
    _, after = snapshot(args, backend)
    summary = {
        "executed": args.execute, "actions": actions,
        "batch_states_after": {n: _batch_state(j) for n, j in after["batch_jobs"].items()},
        "run_execution_states_after": {n: _execution_state(e) for n, e in after["run_executions"].items()},
        "ee_states_after": {t["id"]: t["state"] for t in after["earth_engine_tasks"]},
        "ee_pending_cancel": [t["id"] for t in after["earth_engine_tasks"] if t["state"] == "CANCEL_REQUESTED"],
        "ee_non_terminal": [t["id"] for t in after["earth_engine_tasks"] if t["state"] not in TERMINAL_EE],
        "failed_actions": [a for a in actions if a.get("returncode", 0) != 0 or a.get("ok") is False],
    }
    unknown = [n for n, s in {**summary["batch_states_after"], **summary["run_execution_states_after"]}.items()
               if s == "UNKNOWN"]
    active = [n for n, s in summary["batch_states_after"].items() if s not in TERMINAL_BATCH] + \
             [n for n, s in summary["run_execution_states_after"].items() if s != "TERMINAL"]
    summary["active_compute"] = active
    summary["needs_followup"] = bool(unknown or active or summary["failed_actions"] or summary["ee_non_terminal"])
    summary["unknown_targets"] = unknown
    with (evidence / f"wind_down_after_{stamp}.json").open("x") as handle:
        json.dump({"after": after, "summary": summary}, handle, indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))
    return 1 if summary["needs_followup"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
