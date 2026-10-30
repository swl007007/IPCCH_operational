"""Offline fixtures for identity_chain.py (task 10-28): a consistent fabricated receipt tree passes pre and post; swapping
H0/H6 identities in the readback, in the logs check, or in one harvest receipt (publication untouched) is refused, as is a
terminal record naming another job; r3: missing, null or blank identities (or version 0) present identically in BOTH the
harvest receipt and the publication are refused.

  python3 -B test_identity_chain.py
"""
import importlib.util, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("identity_chain", os.path.join(HERE, "identity_chain.py"))
ic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ic)


def tree(root):
    final = os.path.join(root, "final")
    for i, h in enumerate(ic.HS):
        job = f"projects/1/locations/us-central1/customJobs/{9000 + i}"
        ids = {"run_id": f"{i}" * 32, "model_id": f"m-{i}", "registered_model": f"IPCCH CH | {h}", "model_version": "1"}
        led = os.path.join(root, "ledger/vertex", f"ipcch-ch-validity-r1-formal-h{h}")
        os.makedirs(led)
        json.dump({"name": job, "state": "JOB_STATE_SUCCEEDED"}, open(f"{led}/final.json", "w"))
        json.dump({"status": 200, "body": {"name": job}}, open(f"{led}/submit.json", "w"))
        cp4 = os.path.join(root, ".trellis/tasks/10-28-ipcch-ch-validity-refits/research/cp4")
        os.makedirs(cp4, exist_ok=True)
        json.dump({"job": job, "ok": True, **ids}, open(f"{cp4}/06-harvest-h{h}.json", "w"))
        tr = os.path.join(root, f"scratch/ch-validity-20261028/harvest/formal-h{h}/trial-0")
        os.makedirs(tr)
        json.dump({"status": "complete", **ids, "trial": {"config": {"horizon": int(h)}}}, open(f"{tr}/publication.json", "w"))
        os.makedirs(os.path.join(final, "readback"), exist_ok=True)
        json.dump({"run": {"id": ids["run_id"]}, "logged_model": {"id": ids["model_id"]},
                   "version": {"name": ids["registered_model"], "version": "1"}}, open(os.path.join(final, "readback", f"formal-h{h}.json"), "w"))
    os.makedirs(os.path.join(final, "logs"))
    json.dump({"horizons": {h: {"job_id": str(9000 + i), "run_id": f"{i}" * 32} for i, h in enumerate(ic.HS)}},
              open(os.path.join(final, "logs", "logs-check.json"), "w"))
    return final


def verdict(root, final):
    chain, problems = ic.pre(root)
    pre_ok = not problems
    if pre_ok:
        problems += ic.post(chain, final)
    return pre_ok, not problems


def swap(path_a, path_b, keys):
    a, b = json.load(open(path_a)), json.load(open(path_b))
    for k in keys:
        a[k], b[k] = b[k], a[k]
    json.dump(a, open(path_a, "w")), json.dump(b, open(path_b, "w"))


def main():
    res = {}
    with tempfile.TemporaryDirectory() as t:
        base = os.path.join(t, "base")
        final = tree(base)
        res["consistent"] = (verdict(base, final), (True, True))
        cases = {
            "readback_h00_h06_swapped": lambda r, f: swap(f"{f}/readback/formal-h00.json", f"{f}/readback/formal-h06.json", ("run", "logged_model", "version")),
            "logs_h00_h06_run_swapped": lambda r, f: (lambda p: json.dump({"horizons": {**json.load(open(p))["horizons"],
                "00": {**json.load(open(p))["horizons"]["00"], "run_id": json.load(open(p))["horizons"]["06"]["run_id"]},
                "06": {**json.load(open(p))["horizons"]["06"], "run_id": json.load(open(p))["horizons"]["00"]["run_id"]}}}, open(p + ".tmp", "w"))
                or os.replace(p + ".tmp", p))(f"{f}/logs/logs-check.json"),
            "harvest_receipt_h00_h06_run_swapped": lambda r, f: swap(
                f"{r}/.trellis/tasks/10-28-ipcch-ch-validity-refits/research/cp4/06-harvest-h00.json",
                f"{r}/.trellis/tasks/10-28-ipcch-ch-validity-refits/research/cp4/06-harvest-h06.json", ("run_id", "model_id")),
            # missing/null/blank identities in BOTH the harvest receipt and the publication (they still "agree")
            "identities_missing_both_sides": lambda r, f: [
                (lambda p, drop: json.dump({k: v for k, v in json.load(open(p)).items() if k not in drop}, open(p + ".t", "w")) or os.replace(p + ".t", p))(p, ("run_id", "model_id", "registered_model", "model_version"))
                for p in (f"{r}/.trellis/tasks/10-28-ipcch-ch-validity-refits/research/cp4/06-harvest-h06.json",
                          f"{r}/scratch/ch-validity-20261028/harvest/formal-h06/trial-0/publication.json")],
            "identities_null_both_sides": lambda r, f: [
                (lambda p: json.dump({**json.load(open(p)), "run_id": None, "model_id": None, "registered_model": None, "model_version": None},
                                     open(p + ".t", "w")) or os.replace(p + ".t", p))(p)
                for p in (f"{r}/.trellis/tasks/10-28-ipcch-ch-validity-refits/research/cp4/06-harvest-h12.json",
                          f"{r}/scratch/ch-validity-20261028/harvest/formal-h12/trial-0/publication.json")],
            "identities_blank_version0_both_sides": lambda r, f: [
                (lambda p: json.dump({**json.load(open(p)), "run_id": " ", "model_version": "0"}, open(p + ".t", "w")) or os.replace(p + ".t", p))(p)
                for p in (f"{r}/.trellis/tasks/10-28-ipcch-ch-validity-refits/research/cp4/06-harvest-h00.json",
                          f"{r}/scratch/ch-validity-20261028/harvest/formal-h00/trial-0/publication.json")],
            "terminal_record_other_job": lambda r, f: json.dump({"name": "projects/1/locations/us-central1/customJobs/9001", "state": "JOB_STATE_SUCCEEDED"},
                open(f"{r}/ledger/vertex/ipcch-ch-validity-r1-formal-h00/final.json", "w")),
        }
        for name, fn in cases.items():
            r = os.path.join(t, name)
            shutil.copytree(base, r)
            f = os.path.join(r, "final")
            fn(r, f)
            got = verdict(r, f)
            res[name] = (got, "refused")
    ok = res["consistent"][0] == (True, True) and all(not v[0][1] for k, v in res.items() if k != "consistent")
    print(json.dumps({"ok": ok, "cases": {k: {"pre_ok": v[0][0], "chain_ok": v[0][1], "expected": v[1]} for k, v in res.items()}}, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
