"""Task-owned cleanup of the temporary ANNUAL-context weights of the three origin-ablation runs (task 10-30, R9/A6; run only
under a released cleanup packet). The retained holdout package (``package/``, published as the LoggedModel) is never
touched; nothing in MLflow is touched (the annual package was never published there).

Targets per horizon: exactly the booster files ``gcs-only/annual-package/weights/<annual context>/q{2,3,4,5}.ubj`` of the
job's trial prefix and of the local harvest copy. Everything else of the annual package (package.json with the sha256 of
every removed file, records, routing, reference sample, loader) and every keyed prediction/membership/config/receipt is
kept as evidence. Preconditions per horizon (all checked before any delete): the annual replay receipt
``07-replay-annual-hHH.json`` passed with no integrity problems and is for this package; the annual package.json routes only
annual contexts; each target's local sha256/bytes == package.json; each target's current GCS generation/size/CRC32C ==
the harvest listing (``06-harvest-hHH.json``); no target lies outside ``gcs-only/annual-package/weights/``. Source
binding (Supervisor review): the trial prefix is derived ONLY from this task's own released job record
(``ledger/vertex/ipcch-origin-ablation-r1-formal-hHH/final.json`` SUCCEEDED, name == its ``submit.json`` name, display name and
task label of this task) as ``gs://<artifacts>/trials/ipcch_validity_pooled/<that job id>/trial-0``; the harvest receipt's job
and source and every listed object must equal it; a CH-final (baseline) job id or any other prefix is refused; the replay
receipt is bound to the current annual package (path + package.json sha256; ``replay_check.py``).

  default (dry run): prints and records the plan; no delete.
  IPCCH_ORIGIN_CLEANUP_CONFIRM=r1 ... --execute: generation-pinned deletes (if_generation_match, retry=None), each read back
  as NotFound; then the local copies; one receipt (new path).

  cd $W/control-plane-origin-ablation && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $W/envs/mlflow-svc/bin/python -B cleanup_annual_weights.py --out RECEIPT.json [--execute]
"""
import argparse, base64, hashlib, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay_check  # noqa: E402

W = "/home/swl007007/projects/food-crisis-research"
TASK = "/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational/.trellis/tasks/10-30-ipcch-validity-origin-ablation"
J = f"{TASK}/research/cp3/jobs"
H = f"{W}/scratch/origin-ablation-20261030/harvest"
PREFIX = "gcs-only/annual-package/weights/"
ARTIFACTS = "gs://food-crisis-modeling-enso-research-artifacts/trials/ipcch_validity_pooled"
TASK_LABEL = "ipcch-validity-origin-ablation"
# the retained CH-final baseline jobs (task 10-28): never a cleanup source
BASELINE_JOBS = ("6867303963549499392", "3518877640599535616", "8594997370599505920")
BOOSTERS = ("q2.ubj", "q3.ubj", "q4.ubj", "q5.ubj")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def crc(p):
    import google_crc32c
    c = google_crc32c.Checksum()
    c.update(open(p, "rb").read())
    return base64.b64encode(c.digest()).decode()


def bound_source(h, root=W):
    """(job name, exact trial prefix) of this task's released, SUCCEEDED job of horizon h, from its own ledger records."""
    op = f"ipcch-origin-ablation-r1-formal-h{h:02d}"
    final = json.load(open(f"{root}/ledger/vertex/{op}/final.json"))
    sub = json.load(open(f"{root}/ledger/vertex/{op}/submit.json")).get("body") or {}
    name = final.get("name")
    labels = sub.get("labels") or {}
    if (final.get("state") != "JOB_STATE_SUCCEEDED" or not name or name != sub.get("name") or "/customJobs/" not in name
            or sub.get("displayName") != f"ipcch-origin-ablation-formal-h{h:02d}" or labels.get("task") != TASK_LABEL
            or labels.get("horizon") != f"h{h:02d}"):
        raise ValueError(f"{op}: not a succeeded, released job of this task")
    job_id = name.rsplit("/", 1)[1]
    if job_id in BASELINE_JOBS:
        raise ValueError(f"{op}: {job_id} is a CH-final baseline job")
    return name, f"{ARTIFACTS}/{job_id}/trial-0"


def plan(h, root=W, jobs=J, harvest=H):
    hh = f"{h:02d}"
    trial = f"{harvest}/formal-h{hh}/trial-0"
    pkg_dir = f"{trial}/gcs-only/annual-package"
    hv = json.load(open(f"{jobs}/06-harvest-h{hh}.json"))
    pkg = json.load(open(f"{pkg_dir}/package.json"))
    problems = []
    try:
        job, source = bound_source(h, root)
    except (OSError, ValueError) as e:
        job, source = None, None
        problems.append(f"source binding: {e}")
    if not hv.get("ok"):
        problems.append("harvest not ok")
    if source is None or hv.get("job") != job or hv.get("source") != source \
            or os.path.realpath(hv.get("trial_dir", "")) != os.path.realpath(trial):
        problems.append(f"harvest receipt (job {hv.get('job')}, source {hv.get('source')}) is not this task's bound job/output")
    prefix_rel = (source or "")[5:].partition("/")[2] + "/"
    if source is None or any(not o["name"].startswith(prefix_rel) for o in hv.get("objects") or []):
        problems.append("harvest listing contains objects outside the bound trial prefix")
    problems += [f"annual replay: {p}" for p in replay_check.problems(f"{jobs}/07-replay-annual-h{hh}.json", pkg_dir)]
    ctx = pkg["routing"]["contexts"]
    if not ctx or any("_supp_" in c for c in ctx):
        problems.append(f"annual package routes {ctx}")
    files = pkg.get("files") or {}
    listing = {o["name"].split("/trial-0/", 1)[1]: o for o in hv["objects"]}
    targets = []
    for c in ctx:
        for q in BOOSTERS:
            rel = f"{PREFIX}{c}/{q}"
            local = f"{trial}/{rel}"
            entry = files.get(f"weights/{c}/{q}") or {}
            obj = listing.get(rel)
            t = {"rel": rel, "local": local, "package_sha256": entry.get("sha256"), "gcs": obj}
            if not os.path.isfile(local) or sha(local) != entry.get("sha256") or os.path.getsize(local) != entry.get("bytes"):
                problems.append(f"{rel}: local bytes differ from the annual package.json")
            if not obj or obj["size"] != os.path.getsize(local) or obj["crc32c"] != crc(local):
                problems.append(f"{rel}: harvest listing missing or differs from the local bytes")
            targets.append(t)
    return {"horizon": h, "trial": trial, "job": job, "source": source, "contexts": ctx, "targets": targets, "problems": problems,
            "replay_receipt_sha256": sha(f"{jobs}/07-replay-annual-h{hh}.json")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"{a.out} exists")
    plans = {f"h{h:02d}": plan(h) for h in (0, 6, 12)}
    rec = {"kind": "task-owned annual-weight cleanup (task 10-30)", "mode": "execute" if a.execute else "dry-run", "plans": plans,
           "retained": "holdout package/ (LoggedModel), annual package.json/records/routing/reference/loader, every prediction, "
                       "membership, config and receipt; nothing in MLflow touched"}
    bad = [f"{g}: {p}" for g, v in plans.items() for p in v["problems"]]
    rec["precheck_problems"] = bad
    if bad or not a.execute:
        rec["deleted"] = []
        json.dump(rec, open(a.out, "w"), indent=1, default=str)
        print(json.dumps({"mode": rec["mode"], "targets": sum(len(v["targets"]) for v in plans.values()), "problems": bad}))
        return 1 if bad else 0
    if os.environ.get("IPCCH_ORIGIN_CLEANUP_CONFIRM") != "r1":
        raise SystemExit("needs IPCCH_ORIGIN_CLEANUP_CONFIRM=r1 to execute")
    from google.cloud import storage
    from google.api_core.exceptions import NotFound
    client = storage.Client(project="food-crisis-modeling-enso", client_options={"quota_project_id": "food-crisis-modeling-enso"})
    rec["deleted"] = []
    for g, v in plans.items():
        bucket_name, _, prefix = v["source"][5:].partition("/")
        bucket = client.bucket(bucket_name)
        for t in v["targets"]:
            name = f"{prefix}/{t['rel']}"
            if not t["rel"].startswith(PREFIX) or not name.startswith(prefix + "/" + PREFIX):
                raise SystemExit(f"refusing a target outside {PREFIX}: {name}")
            item = {"object": f"gs://{bucket_name}/{name}", "generation": t["gcs"]["generation"]}
            try:
                bucket.blob(name).delete(if_generation_match=t["gcs"]["generation"], retry=None)
                item["gcs"] = "deleted"
            except Exception as e:
                item["gcs"] = f"error {type(e).__name__}: {e}"
            try:
                bucket.blob(name).reload()
                item["readback"] = "still present"
            except NotFound:
                item["readback"] = "not found"
            if item["readback"] == "not found":
                os.remove(t["local"])
                item["local"] = "removed"
            rec["deleted"].append(item)
            json.dump(rec, open(a.out, "w"), indent=1, default=str)
            if item["readback"] != "not found":
                raise SystemExit(f"{name}: delete not confirmed; stopping")
    rec["ok"] = all(d["readback"] == "not found" and d.get("local") == "removed" for d in rec["deleted"])
    json.dump(rec, open(a.out, "w"), indent=1, default=str)
    print(json.dumps({"mode": "execute", "deleted": len(rec["deleted"]), "ok": rec["ok"]}))
    return 0 if rec["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
