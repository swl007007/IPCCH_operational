"""Closed per-horizon identity chain of the origin-ablation final packet (task 10-30; local only, no calls). Adapted from
the task 10-28 ``identity_chain.py``: operations/harvest paths, and the harvest receipts directory is an argument
(``--receipts``; default the task's research/cp3/jobs in the operational checkout).

pre   (before any live call): ledger terminal final.json name == its submit receipt's returned name == the harvest
      receipt's job; harvest receipt run / LoggedModel / registered model / version == the harvested publication.json;
      every identity is a non-empty string and the version a positive integer (v1 contract: "1"); the three horizons are
      distinct in every identity.
post  (in the verdict, after the calls): the pre chain again, plus logs-check job id and run id == the chain, and the
      readback formal-hHH run id / LoggedModel id / registered model / version == the chain.

  python3 -B identity_chain.py --stage pre|post --final FINAL_DIR --out JSON [--root W] [--receipts DIR]
"""
import argparse, json, os, sys

W = "/home/swl007007/projects/food-crisis-research"
HS = ("00", "06", "12")
KEYS = ("job", "run_id", "model_id", "registered_model", "model_version")
RECEIPTS = "/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational/.trellis/tasks/10-30-ipcch-validity-origin-ablation/research/cp3/jobs"


def pre(root, receipts=RECEIPTS):
    chain, problems = {}, []
    for h in HS:
        op = f"ipcch-origin-ablation-r1-formal-h{h}"
        try:
            final = json.load(open(f"{root}/ledger/vertex/{op}/final.json"))
            sub = (json.load(open(f"{root}/ledger/vertex/{op}/submit.json")).get("body") or {}).get("name")
            hv = json.load(open(f"{receipts}/06-harvest-h{h}.json"))
            pub = json.load(open(f"{root}/scratch/origin-ablation-20261030/harvest/formal-h{h}/trial-0/publication.json"))
        except (OSError, ValueError) as e:
            problems.append(f"h{h}: {type(e).__name__}: {e}")
            continue
        c = {"job": final.get("name"), "run_id": hv.get("run_id"), "model_id": hv.get("model_id"),
             "registered_model": hv.get("registered_model"), "model_version": str(hv.get("model_version"))}
        if any(not isinstance(hv.get(k), str) or not hv.get(k).strip() for k in ("run_id", "model_id", "registered_model")) \
                or not str(hv.get("model_version")).isdigit() or int(hv.get("model_version")) < 1 or str(hv.get("model_version")) != "1":
            problems.append(f"h{h}: harvest identities are missing/blank or the version is not the positive v1")
        if final.get("state") != "JOB_STATE_SUCCEEDED" or not c["job"] or c["job"] != sub or hv.get("job") != c["job"] or not hv.get("ok"):
            problems.append(f"h{h}: terminal / submit / harvest job differ or are not a succeeded harvested job")
        if (pub.get("run_id"), pub.get("model_id"), pub.get("registered_model"), str(pub.get("model_version"))) != \
                (c["run_id"], c["model_id"], c["registered_model"], c["model_version"]) or pub.get("status") != "complete":
            problems.append(f"h{h}: harvest receipt identities differ from the harvested publication.json")
        if int(((pub.get("trial") or {}).get("config") or {}).get("horizon", -1)) != int(h):
            problems.append(f"h{h}: the harvested publication is horizon {((pub.get('trial') or {}).get('config') or {}).get('horizon')}")
        chain[h] = c
    for k in KEYS:
        vals = [c[k] for c in chain.values()]
        if k != "model_version" and len(set(vals)) != len(vals):
            problems.append(f"the horizons share a {k}: {vals}")
    return chain, problems


def post(chain, final_dir):
    problems = []
    logs = json.load(open(os.path.join(final_dir, "logs", "logs-check.json")))["horizons"]
    for h, c in chain.items():
        lg = logs.get(h) or {}
        if lg.get("job_id") != c["job"].rsplit("/", 1)[1] or lg.get("run_id") != c["run_id"]:
            problems.append(f"h{h}: logs-check job/run {lg.get('job_id')}/{lg.get('run_id')} is not the chain's")
        rb = json.load(open(os.path.join(final_dir, "readback", f"formal-h{h}.json")))
        got = (rb.get("run", {}).get("id"), rb.get("logged_model", {}).get("id"), rb.get("version", {}).get("name"), str(rb.get("version", {}).get("version")))
        if got != (c["run_id"], c["model_id"], c["registered_model"], c["model_version"]):
            problems.append(f"h{h}: readback identities {got} are not the chain's")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("pre", "post"), required=True)
    ap.add_argument("--final", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--root", default=W)
    ap.add_argument("--receipts", default=RECEIPTS)
    a = ap.parse_args()
    chain, problems = pre(a.root, a.receipts)
    if a.stage == "post" and not problems:
        problems += post(chain, a.final)
    rec = {"stage": a.stage, "chain": chain, "problems": problems, "ok": not problems and len(chain) == 3}
    json.dump(rec, open(a.out, "w"), indent=1)
    print(json.dumps({"stage": a.stage, "ok": rec["ok"], "problems": problems}))
    return 0 if rec["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
