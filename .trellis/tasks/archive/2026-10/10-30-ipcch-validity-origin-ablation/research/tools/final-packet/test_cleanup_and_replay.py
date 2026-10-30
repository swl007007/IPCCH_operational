"""Offline refusal tests (Supervisor review of cleanup 9b26fe2b / run_final 8967ee9d): the cleanup plan is bound to this task's
released job record and its exact output prefix; replay receipts are bound to the current package. A consistent fabricated
tree plans its 4 x contexts targets with no problems; each single mutation is refused. No cloud call.

  $W/envs/mlflow-svc/bin/python -B test_cleanup_and_replay.py
"""
import base64, copy, hashlib, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cleanup_annual_weights as cw  # noqa: E402
import replay_check  # noqa: E402

JOB = "projects/76571749286/locations/us-central1/customJobs/1111111111111111111"
CTX = ("h06_main_2023", "h06_main_2024")


def crc(b):
    import google_crc32c
    c = google_crc32c.Checksum()
    c.update(b)
    return base64.b64encode(c.digest()).decode()


def tree(job=JOB, source=None, state="JOB_STATE_SUCCEEDED", task=cw.TASK_LABEL, hv_job=None, outside=False):
    root = tempfile.mkdtemp()
    jobs, harvest = f"{root}/jobs", f"{root}/harvest"
    op = f"{root}/ledger/vertex/ipcch-origin-ablation-r1-formal-h06"
    os.makedirs(op), os.makedirs(jobs)
    json.dump({"name": job, "state": state}, open(f"{op}/final.json", "w"))
    json.dump({"body": {"name": job, "displayName": "ipcch-origin-ablation-formal-h06", "labels": {"task": task, "horizon": "h06"}}},
              open(f"{op}/submit.json", "w"))
    trial = f"{harvest}/formal-h06/trial-0"
    pkg = f"{trial}/gcs-only/annual-package"
    src = source or f"{cw.ARTIFACTS}/{job.rsplit('/', 1)[1]}/trial-0"
    prefix = src[5:].partition("/")[2]
    files, objects = {}, []
    for c in CTX:
        for q in cw.BOOSTERS:
            b = f"{c}-{q}".encode()
            os.makedirs(f"{pkg}/weights/{c}", exist_ok=True)
            open(f"{pkg}/weights/{c}/{q}", "wb").write(b)
            files[f"weights/{c}/{q}"] = {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
            objects.append({"name": f"{prefix}/gcs-only/annual-package/weights/{c}/{q}", "generation": 7, "size": len(b), "crc32c": crc(b)})
    if outside:
        objects.append({"name": "trials/ipcch_validity_pooled/6867303963549499392/trial-0/predictions.csv.gz", "generation": 1, "size": 1, "crc32c": "x"})
    json.dump({"routing": {"contexts": list(CTX)}, "files": files}, open(f"{pkg}/package.json", "w"))
    json.dump({"ok": True, "job": hv_job or job, "source": src, "trial_dir": trial, "objects": objects}, open(f"{jobs}/06-harvest-h06.json", "w"))
    json.dump({"passed": True, "integrity_problems": [], "package": pkg,
               "package_json_sha256": hashlib.sha256(open(f"{pkg}/package.json", "rb").read()).hexdigest()},
              open(f"{jobs}/07-replay-annual-h06.json", "w"))
    return root, jobs, harvest, pkg


def plan(t):
    root, jobs, harvest, _ = t
    return cw.plan(6, root=root, jobs=jobs, harvest=harvest)


def main():
    res = {}
    ok = plan(tree())
    res["valid_plans_4x_contexts"] = ok["problems"] == [] and len(ok["targets"]) == 4 * len(CTX)
    ch_src = f"{cw.ARTIFACTS}/6867303963549499392/trial-0"
    res["ch_baseline_source_refused"] = bool(plan(tree(source=ch_src))["problems"])            # the Supervisor's scout case
    res["ledger_baseline_job_refused"] = any("baseline" in p for p in plan(tree(job="projects/1/locations/us-central1/customJobs/6867303963549499392"))["problems"])
    res["harvest_job_mismatch_refused"] = bool(plan(tree(hv_job="projects/1/locations/us-central1/customJobs/999"))["problems"])
    res["failed_job_refused"] = bool(plan(tree(state="JOB_STATE_FAILED"))["problems"])
    res["other_task_label_refused"] = bool(plan(tree(task="ipcch-ch-validity-refits"))["problems"])
    res["listing_outside_prefix_refused"] = any("outside the bound" in p for p in plan(tree(outside=True))["problems"])
    t = tree()
    r = json.load(open(f"{t[1]}/07-replay-annual-h06.json"))
    json.dump({**r, "package": "/elsewhere/package"}, open(f"{t[1]}/07-replay-annual-h06.json", "w"))
    res["replay_other_package_refused"] = any("replay is of" in p for p in plan(t)["problems"])
    t = tree()
    pj = f"{t[3]}/package.json"
    d = json.load(open(pj)); d["note"] = "changed after replay"; json.dump(d, open(pj, "w"))
    res["replay_stale_package_refused"] = any("sha256 differs" in p for p in plan(t)["problems"])
    t = tree()
    r = json.load(open(f"{t[1]}/07-replay-annual-h06.json"))
    json.dump({**r, "passed": False}, open(f"{t[1]}/07-replay-annual-h06.json", "w"))
    res["replay_not_passed_refused"] = any("did not pass" in p for p in plan(t)["problems"])
    # replay_check alone (as used by run_final.sh for both packages)
    t = tree()
    res["replay_check_valid"] = replay_check.problems(f"{t[1]}/07-replay-annual-h06.json", t[3]) == []
    res["replay_check_wrong_dir"] = bool(replay_check.problems(f"{t[1]}/07-replay-annual-h06.json", f"{t[3]}/.."))
    res["replay_check_missing_receipt"] = bool(replay_check.problems(f"{t[1]}/missing.json", t[3]))
    ok_all = all(res.values())
    print(json.dumps({"ok": ok_all, "cases": res}, indent=1))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
