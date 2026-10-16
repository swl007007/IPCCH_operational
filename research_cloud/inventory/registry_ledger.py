"""Exact acceptance ledger: one row per registered model version in the MLflow snapshot.

Driven from every ``model_versions`` row (LEFT JOIN to logged models): a registry identity whose
source does not resolve is kept as ``unresolved_registry_identity``, never dropped, and the
ledger's (name, version) key set must equal the snapshot's exactly.

Each resolved version is joined to its logged model, source/parent runs and identity tags; its
weight members (dashboard: the family member manifest; forecasting: the plan version's own
members) are resolved against the fresh member inventory; and any built package (status,
content digest, replay result) is attached. Reused comparators stay ``needs_resolution`` until
their underlying weight identity is established (``--resolutions``); a family's own member
status is not evidence for weights it did not fit.

  python3 -m research_cloud.inventory.registry_ledger --snapshot DB --members MEMBERS.jsonl
      --packages DIR [--replays SUMMARY.json ...] [--resolutions R.json] --out LEDGER.json
"""
import argparse
import collections
import glob
import json
import os
import sqlite3

from research_cloud.packages.common import sha256_file

TAGS = ("family", "arm", "arm_kind", "arm_role", "lead_months", "seed", "window", "zz_original_arm",
        "zz_prov.projection_key", "zz_prov.version_key", "zz_prov.source_key", "feature_set", "snapshot")


def classify(row, statuses, pkg, replay, resolution, experiment):
    if pkg and pkg["status"] == "complete" and replay and replay["replay_passed"]:
        if replay.get("package_json_sha256") != pkg.get("package_json_sha256"):
            return "packaged_replay_stale", "replay receipt was produced for a different package.json than the current package"
        return "packaged_replay_passed", None
    if row.get("arm_kind") == "reused_comparator" and not resolution:
        return "needs_resolution", ("reused comparator: the underlying weight identity is not established; "
                                    "the probe family's own member status is not sufficient")
    if resolution:
        return resolution["ledger_class"], resolution.get("evidence")
    if set(statuses) == {"missing"}:
        if experiment == 4:
            return "missing_weights_tracking_only", "every member of this plan version is verified not-found"
        return "missing_weights_tracking_only", ("every member of the family manifest is verified not-found under all "
                                                 "declared roots; this version's own-fit weights are a subset")
    if set(statuses) == {"verified"}:
        return "weights_retained_package_pending", None
    return "needs_resolution", f"mixed member statuses {statuses}"


def build_rows(db, member_status, plan_members, packages, replays, resolutions):
    rows = []
    q = """SELECT v.name, v.version, v.source, v.status, l.model_id, l.experiment_id, l.source_run_id
           FROM model_versions v LEFT JOIN logged_models l ON v.source = 'models:/' || l.model_id
           ORDER BY v.name, v.version"""
    for name, version, source, vstatus, model_id, exp, src_run in db.execute(q).fetchall():
        if model_id is None:
            rows.append({"registered_model": name, "version": version, "version_status": vstatus, "source": source,
                         "logged_model_id": None, "family": None, "ledger_class": "unresolved_registry_identity",
                         "reason": "registry source does not resolve to a LoggedModel in the snapshot"})
            continue
        tags = dict(db.execute("SELECT tag_key, tag_value FROM logged_model_tags WHERE model_id=?", (model_id,)).fetchall())
        run_tags = dict(db.execute("SELECT key, value FROM tags WHERE run_uuid=?", (src_run,)).fetchall())
        for key in ("arm_kind", "original_arm"):   # dashboard identity tags live on the source run
            tags.setdefault(key if key != "original_arm" else "zz_original_arm", run_tags.get(f"zz_prov.{key}"))
        parent = db.execute("SELECT value FROM tags WHERE run_uuid=? AND key='mlflow.parentRunId'", (src_run,)).fetchone()
        row = {"registered_model": name, "version": version, "version_status": vstatus, "source": source,
               "logged_model_id": model_id, "experiment_id": exp, "source_run_id": src_run,
               "parent_run_id": parent[0] if parent else None, **{t: tags.get(t) for t in TAGS}}
        family = tags.get("family")
        if exp == 4:
            source_key, paths = plan_members.get(tags.get("zz_prov.version_key"), (None, None))
            statuses = ({"unresolved_plan_version": 1} if paths is None else
                        dict(collections.Counter(member_status[source_key].get(p, "not_in_inventory") for p in paths)))
            row["member_scope"] = f"plan version {tags.get('zz_prov.version_key')}"
        else:
            fam = member_status.get(family, {})
            statuses = dict(collections.Counter(fam.values())) if fam else {"family_not_in_inventory": 1}
            row["member_scope"] = f"family {family} member manifest (shared across its versions)"
        row["member_status_counts"] = statuses
        row["package"], row["replay"] = packages.get(model_id), replays.get(model_id)
        resolution = resolutions.get(model_id)
        if resolution:
            row["resolution"] = resolution
        row["ledger_class"], row["reason"] = classify(row, statuses, row["package"], row["replay"], resolution, exp)
        rows.append(row)
    return rows


def check_keys(db, rows):
    expected = set(db.execute("SELECT name, version FROM model_versions").fetchall())
    got = [(r["registered_model"], r["version"]) for r in rows]
    if set(got) != expected or len(got) != len(expected):
        raise SystemExit(f"ledger keys differ from snapshot: missing {sorted(expected - set(got))[:5]} "
                         f"extra {sorted(set(got) - expected)[:5]} duplicates {len(got) - len(set(got))}")


def load_inputs(args):
    member_status = collections.defaultdict(dict)
    for line in open(args.members):
        r = json.loads(line)
        member_status[r["family"]][r["path"]] = r["status"]
    plan_members = {}
    for plan_path in glob.glob(f"{args.store}/artifacts/3/*/artifacts/manifests/plan.json"):
        plan = json.load(open(plan_path))
        for vk, v in plan["versions"].items():
            plan_members[vk] = (plan["source_key"], [m["path"] for m in v["members"]])
    packages = {}
    for pj in glob.glob(f"{args.packages}/*/package.json"):
        m = json.load(open(pj))
        packages[m["identity"].get("logged_model_id")] = {"package": os.path.dirname(pj), "status": m["status"],
                                                           "content_sha256": m["content_sha256"], "gaps": m["gaps"],
                                                           "package_json_sha256": sha256_file(pj)}
    replays = {}
    for path in args.replays:
        for r in json.load(open(path)):
            replays[r["logged_model_id"]] = {"replay_passed": r["replay_passed"], "reference_rows": r["reference_rows"],
                                             "max_abs_err": r["max_abs_err"], "replay_summary": path,
                                             "package_json_sha256": r.get("package_json_sha256")}
    resolutions = json.load(open(args.resolutions)) if args.resolutions else {}
    return member_status, plan_members, packages, replays, resolutions


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--members", required=True)
    ap.add_argument("--store", default="/home/swl007007/.local/share/ipcch-mlflow")
    ap.add_argument("--packages", required=True)
    ap.add_argument("--replays", action="append", default=[])
    ap.add_argument("--resolutions")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    db = sqlite3.connect(f"file:{args.snapshot}?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    rows = build_rows(db, *load_inputs(args))
    check_keys(db, rows)
    summary = collections.Counter((str(r["family"]), r["ledger_class"]) for r in rows)
    out = {"snapshot": args.snapshot, "versions": len(rows), "key_set_equals_snapshot": True,
           "by_class": dict(collections.Counter(r["ledger_class"] for r in rows)),
           "by_family_class": {f"{f} | {c}": n for (f, c), n in sorted(summary.items())}, "rows": rows}
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1)
    print(out["versions"], out["by_class"])
    for k, n in out["by_family_class"].items():
        print(f"  {n:4d}  {k}")
    return out


if __name__ == "__main__":
    main()
