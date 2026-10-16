"""Build the eight window-probe reused-comparator packages from the read-only snapshot identities.

  python -m research_cloud.packages.build_window_probe --snapshot DB --out PACKAGES_DIR
"""
import argparse
import json
import os
import sqlite3

from research_cloud.packages import window_probe
from research_cloud.packages.build_geoxgb import ART, LINUX, SOURCES

PROBE = "/home/swl007007/.local/share/ipcch-mlflow/artifacts/1/e9cfa99f94dd4a67b0e3b6ed511708ad/artifacts/source"


def versions(snapshot):
    db = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    tag = "(SELECT tag_value FROM logged_model_tags t WHERE t.model_id=l.model_id AND t.tag_key='{}')"
    q = f"""SELECT v.name, v.version, l.model_id, {tag.format('arm')}, {tag.format('lead_months')}, l.source_run_id
            FROM model_versions v JOIN logged_models l ON v.source='models:/'||l.model_id
            WHERE {tag.format('family')}='geoxgb_window_probe'"""
    out = []
    for name, version, model_id, arm, lead, run_id in db.execute(q):
        kind = db.execute("SELECT value FROM tags WHERE run_uuid=? AND key='zz_prov.arm_kind'", (run_id,)).fetchone()
        if kind and kind[0] == "reused_comparator":
            out.append(dict(name=name, version=version, model_id=model_id, arm=arm, lead=int(lead), source_run_id=run_id))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    src = SOURCES["geoxgb_reference"]
    art = f"{ART}/{src['family_run_id']}/artifacts"
    sc = f"{art}/{src['source_code']}"
    lock = json.load(open(f"{sc}/config/runtime-lock.json"))
    found = versions(args.snapshot)
    if len(found) != 8:
        raise SystemExit(f"expected 8 reused-comparator versions, found {len(found)}")
    for v in sorted(found, key=lambda v: (v["arm"], v["lead"])):
        out = os.path.join(args.out, f"geoxgb_window_probe-{v['arm']}-h{v['lead']:02d}")
        if os.path.exists(os.path.join(out, "package.json")):
            print(os.path.basename(out), "exists")
            continue
        meta = window_probe.build(
            out, probe_dir=PROBE, p6_root=src["run_root"], p6_source_code=sc,
            p6_members_manifest=f"{art}/manifests/models.tar.members.json",
            version={"registered_model": v["name"], "version": v["version"], "logged_model_id": v["model_id"],
                     "source_run_id": v["source_run_id"], "parent_run_id": "e9cfa99f94dd4a67b0e3b6ed511708ad"},
            lead=v["lead"], registered_arm=v["arm"],
            code_identity={"commit": src["commit"], "source_code_artifact": f"runs:/{src['family_run_id']}/source_code"},
            original_runtime={k: lock[k] for k in ("python", "platform_system", "packages", "model_runtime") if k in lock},
            linux_runtime=LINUX)
        print(os.path.basename(out), meta["status"], meta["fitted_units"], meta["reference"]["rows"], meta["gaps"][:2], flush=True)


if __name__ == "__main__":
    main()
