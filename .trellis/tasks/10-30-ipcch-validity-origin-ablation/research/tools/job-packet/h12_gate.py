"""H12 gate of the origin-ablation job packet (task 10-30; the task 10-28 r2 gate with only paths/operations/labels changed).
Rule (failure checked FIRST): any wave-1 job (h00/h06) in FAILED/CANCELLED/EXPIRED BLOCKS H12, even if the other wave-1
job SUCCEEDED; otherwise the first SUCCEEDED opens the gate; no automatic refit or resubmission of any horizon; then occupancy wave 2 (planned 1) must be ok; then ONE vertex_submit submit of the released
H12 spec and its poller. Guards: a lock file prevents a second watcher; any existing H12 ledger dir or submit receipt
stops before submitting (never a second submit).
r2 (Supervisor review): the pollers' final.json files are only the waiting hint (they can lag a provider failure by up to
one poll interval). Right before the paid submit, ``pre_submit`` reads BOTH bound wave-1 CustomJobs fresh (two read-only
GETs of the exact resource names bound in the ledger and returned in the submit receipts), persists each response,
requires the bound identity (name, claim label, task/horizon labels, display name) and a known state, and applies the same
failure-first rule; an error, identity mismatch or unknown state stops. Not an atomic multi-job snapshot. Self-test
(decision cases, the stale-file + fresh-failure refusal and the stop cases, all mocked): --selftest.

  cd $W/control-plane-origin-ablation && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $W/envs/mlflow-svc/bin/python -B h12_gate.py [--selftest]
"""
import fcntl, json, os, subprocess, sys, tempfile, time

W = "/home/swl007007/projects/food-crisis-research"
D = "/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational/.trellis/tasks/10-30-ipcch-validity-origin-ablation/research/cp3/jobs"
P = f"{W}/staging/ipcch-origin-ablation-20261030/job-packet"
CP = f"{W}/control-plane-origin-ablation"
PY = f"{W}/envs/mlflow-svc/bin/python"
OK, BAD = "JOB_STATE_SUCCEEDED", ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED")
OP12 = "ipcch-origin-ablation-r1-formal-h12"
KNOWN = {OK, *BAD, "JOB_STATE_QUEUED", "JOB_STATE_PENDING", "JOB_STATE_RUNNING", "JOB_STATE_CANCELLING", "JOB_STATE_UPDATING",
         "JOB_STATE_PAUSED"}
TASK_LABEL = "ipcch-validity-origin-ablation"


def decide(states):
    """states: {h: terminal state or None}. Failure is checked FIRST."""
    if any(s in BAD for s in states.values()):
        return "block"
    if any(s == OK for s in states.values()):
        return "go"
    return "wait"


def bound(h):
    """(exact bound CustomJob name, claim id) of wave-1 operation h: the shared ledger's bound resource, which must equal
    the resource returned in its submit receipt; the claim id of its claim receipt."""
    from research_cloud.cost import ledger as L
    from research_cloud.training import vertex_submit as vs
    out = f"{W}/ledger/vertex/ipcch-origin-ablation-r1-formal-h{h}"
    marker = json.load(open(f"{out}/claim.json"))["claim"]
    name = (json.load(open(f"{out}/submit.json")).get("body") or {}).get("name")
    status, resource, _, _ = vs.current(L.connect(vs.LEDGER), f"ipcch-origin-ablation-r1-formal-h{h}")
    if status != "reserved" or not name or resource != name or "/customJobs/" not in name:
        raise ValueError(f"ledger resource {resource} and submit receipt {name} are not one bound CustomJob")
    return name, marker.split(":")[1]


def provider_get(name):
    """One read-only GET of a CustomJob (the poller's request: vertex_submit BASE and headers)."""
    import requests
    from research_cloud.training import vertex_submit as vs
    r = requests.get(f"{vs.BASE}/{name}", headers=vs.headers(), timeout=60)
    return r.status_code, (r.json() if r.content else None)


def pre_submit(out=D, get=provider_get, binding=bound):
    """('go' | 'block' | 'stop', record) from fresh reads of both wave-1 jobs; each response is persisted (new files)."""
    states, problems = {}, []
    for h in ("00", "06"):
        path = os.path.join(out, f"05c-h12-fresh-h{h}.json")
        rec = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "horizon": h}
        try:
            if os.path.exists(path):
                raise FileExistsError(f"{path} exists; the fresh read is made once")
            name, claim = binding(h)
            status, job = get(name)
            rec.update(bound=name, claim=claim, status=status, body=job)
            labels = (job or {}).get("labels") or {}
            if status != 200 or (job or {}).get("name") != name or labels.get("ipcch-claim") != claim or labels.get("task") != TASK_LABEL \
                    or labels.get("horizon") != f"h{h}" or job.get("displayName") != f"ipcch-origin-ablation-formal-h{h}":
                raise ValueError(f"HTTP {status}: the response is not the bound job {name}")
            if job.get("state") not in KNOWN:
                raise ValueError(f"unknown state {job.get('state')!r}")
            states[h] = job["state"]
        except Exception as e:      # noqa: BLE001 - any failure to establish a fresh known state stops the paid submit
            rec["error"] = f"{type(e).__name__}: {e}"
            problems.append(f"h{h}: {rec['error']}")
        if not os.path.exists(path):
            json.dump(rec, open(path, "w"), indent=1, default=str)
    if problems:
        return "stop", {"problems": problems, "states": states}
    d = decide(states)
    return ("go" if d == "go" else "block"), {"states": states}


def selftest():
    cases = {("JOB_STATE_SUCCEEDED", None): "go", ("JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED"): "block",
             ("JOB_STATE_FAILED", None): "block", (None, None): "wait", ("JOB_STATE_SUCCEEDED", "JOB_STATE_SUCCEEDED"): "go",
             (None, "JOB_STATE_CANCELLED"): "block", ("JOB_STATE_EXPIRED", "JOB_STATE_SUCCEEDED"): "block"}
    res = {f"{a}|{b}": (decide({"00": a, "06": b}), want) for (a, b), want in cases.items()}

    def job(h, state, **over):
        j = {"name": f"projects/1/locations/us-central1/customJobs/{h}", "displayName": f"ipcch-origin-ablation-formal-h{h}",
             "labels": {"ipcch-claim": f"claim{h}", "task": TASK_LABEL, "horizon": f"h{h}"}, "state": state}
        return {**j, **over}

    def run(jobs, status=200):
        binding = lambda h: (f"projects/1/locations/us-central1/customJobs/{h}", f"claim{h}")
        get = lambda name: (status, next(j for j in jobs.values() if j["name"] == name))
        with tempfile.TemporaryDirectory() as t:
            d, rec = pre_submit(t, get, binding)
            persisted = sorted(os.listdir(t))
        return d, persisted
    # stale poller files say go (h00 SUCCEEDED recorded, h06 not yet), the fresh provider read shows h06 FAILED: refuse
    stale = decide({"00": OK, "06": None})
    fresh_fail = run({"00": job("00", OK), "06": job("06", "JOB_STATE_FAILED")})
    scenarios = {
        "stale_file_go_fresh_failure_blocks": ((stale, fresh_fail), ("go", ("block", ["05c-h12-fresh-h00.json", "05c-h12-fresh-h06.json"]))),
        "fresh_success_running_goes": (run({"00": job("00", OK), "06": job("06", "JOB_STATE_RUNNING")})[0], "go"),
        "http_error_stops": (run({"00": job("00", OK), "06": job("06", OK)}, status=500)[0], "stop"),
        "identity_mismatch_stops": (run({"00": job("00", OK), "06": job("06", OK, labels={"ipcch-claim": "other", "task": TASK_LABEL, "horizon": "h06"})})[0], "stop"),
        "unknown_state_stops": (run({"00": job("00", OK), "06": job("06", "JOB_STATE_UNSPECIFIED")})[0], "stop"),
    }
    res.update({k: v for k, v in scenarios.items()})
    ok = all(g == w for g, w in res.values())
    print(json.dumps({"selftest": ok, "cases": res}, indent=1))
    return 0 if ok else 1


def states():
    out = {}
    for h in ("00", "06"):
        f = f"{W}/ledger/vertex/ipcch-origin-ablation-r1-formal-h{h}/final.json"
        out[h] = json.load(open(f)).get("state") if os.path.exists(f) else None
    return out


def log(msg):
    with open(f"{D}/05b-h12-gate.log", "a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}\n")


def main():
    lock = open(f"{D}/h12_gate.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("another H12 gate watcher holds the lock")
    log(f"watcher start pid {os.getpid()}")
    while True:
        s = states()
        d = decide(s)
        if d == "block":
            log(f"BLOCK: wave-1 non-success {s}; H12 not submitted")
            return 1
        if d == "go":
            log(f"GO: first success {s}")
            break
        time.sleep(30)
    if os.path.exists(f"{W}/ledger/vertex/{OP12}") or os.path.exists(f"{D}/04-submit-h12.log"):
        log("H12 ledger dir or submit receipt already exists; never a second submit")
        return 1
    env = {**os.environ, "PYTHONPATH": CP, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([PY, "-B", f"{P}/occupancy.py", "--out", f"{D}/03-occupancy-wave2.json", "--planned", "1"],
                       cwd=CP, env=env, capture_output=True, text=True)
    open(f"{D}/03-occupancy-wave2.log", "w").write(r.stdout + r.stderr + f"rc={r.returncode}\n")
    if r.returncode:
        log("occupancy wave 2 not ok; H12 not submitted")
        return 1
    d, rec = pre_submit()       # fresh provider reads of both wave-1 jobs right before the paid submit (r2)
    if d != "go":
        log(f"{d.upper()} at submit time (fresh provider reads 05c-h12-fresh-h0{{0,6}}.json): {rec}; H12 not submitted")
        return 1
    log(f"GO at submit time (fresh provider reads): {rec['states']}")
    with open(f"{D}/04-submit-h12.log", "w") as f:
        r = subprocess.run([PY, "-B", "-m", "research_cloud.training.vertex_submit", "submit", "--spec", f"{P}/specs/spec-formal-h12.json",
                            "--kind", "custom", "--operation", OP12, "--out", f"{W}/ledger/vertex/{OP12}"],
                           cwd=CP, env=env, stdout=f, stderr=subprocess.STDOUT)
    open(f"{D}/04-submit-h12.log", "a").write(f"rc={r.returncode}\n")
    log(f"H12 submit rc={r.returncode}")
    if r.returncode:
        return 1
    with open(f"{D}/05-poll-h12.log", "w") as f:
        r = subprocess.run([PY, "-B", "-m", "research_cloud.training.vertex_submit", "poll", "--kind", "custom", "--operation", OP12,
                            "--out", f"{W}/ledger/vertex/{OP12}", "--every", "120"], cwd=CP, env=env, stdout=f, stderr=subprocess.STDOUT)
    open(f"{D}/05-poll-h12.log", "a").write(f"rc={r.returncode}\n")
    log(f"H12 poll rc={r.returncode}")
    return r.returncode


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
