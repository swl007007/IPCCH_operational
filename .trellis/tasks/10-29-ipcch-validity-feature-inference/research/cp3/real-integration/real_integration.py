"""CP3 real-mode LOCAL integration on the accepted assets (no cloud writes, no EE, no production store/current):
accepted envelope v2 + out-r5-accepted-v1 + the actual accepted H2/H8/H14 package, a disposable local store, request
M = 2026-10 (O = 2026-08) through run_v2.run_request (admit -> IPCCH generation -> batch -> inference).
- climate/nightlight providers REFUSE if called (delivered histories reach O); any call would be reported, never faked;
- GPP: read-only public HTTPS HEAD probes of the GOSIF v3 URLs; downloads refused;
- ACLED first refresh: the research regional-aggregate exports f2 + f3 (2016-12-31 .. 2026-10-16) concatenated
  byte-faithfully into one pinned local refresh file."""
import hashlib, json, os, sys, time
from datetime import datetime, timezone
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
import pandas as pd
import requests
from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import binding as bd, climate as cl, climate_run, initial, run_v2
from cloud.ipcch.stores import AcceptanceManifest, StoreRoot

R = "/home/swl007007/projects/food-crisis-research"
PKG = f"{R}/scratch/h2h8h14-final/package-build/out-r1/package"
BUNDLE = f"{R}/scratch/h2h8h14-final/handoff-build/out-r5-accepted-v1"
ENV = f"{R}/scratch/h2h8h14-final/envelope/ipcch-combination-envelope-v2-accepted.json"
EXPORTS = f"{R}/staging/ipcch-update-202610/sources/acled_agg/raw/aggregated_2026-10-20"
OUT = sys.argv[1]
os.makedirs(OUT)                                                  # never reuse a run directory
t0, res = time.time(), {"label": "CP3 real-mode LOCAL integration (no cloud writes, no EE)"}

# --- pinned local objects (refresh file, envelope, runtime manifest)
man = json.load(open(f"{EXPORTS}/exports_manifest.json"))
roles = {v["role"]: (k, v) for k, v in man["files"].items()}
f2, f3 = (open(f"{EXPORTS}/{roles[r][0]}", "rb").read() for r in ("f2", "f3"))
assert hashlib.sha256(f2).hexdigest() == roles["f2"][1]["sha256"] and hashlib.sha256(f3).hexdigest() == roles["f3"][1]["sha256"]
body3 = f3[f3.index(b"\n") + 1:]                                  # f3 without its BOM+header line
acled_bytes = f2 + (b"" if f2.endswith(b"\n") else b"\n") + body3
regions = sorted(set(roles["f2"][1]["regions"]) | set(roles["f3"][1]["regions"]))
start = roles["f2"][1]["week_min"]
end = (pd.Timestamp(roles["f3"][1]["week_max"]) + pd.Timedelta(days=6)).strftime("%Y-%m-%d")
objects = {}


def put(name, data):
    uri = f"gs://local-integration/inputs/{name}"
    objects[(uri, "1")] = data
    return {"uri": uri, "generation": "1", "sha256": hashlib.sha256(data).hexdigest()}


acled_ref = put("acled_regional_aggregate_f2f3.csv", acled_bytes)
env_ref = put("ipcch-combination-envelope-v2-accepted.json", open(ENV, "rb").read())
runtime_ref = put("environment.json", b'{"lock": "fewsnet-test-lock-20261022"}\n')
read_ref = lambda ref: objects[(ref["uri"], ref["generation"])]
res["acled_refresh"] = {"bytes": len(acled_bytes), "sha256": acled_ref["sha256"], "start": start, "end": end, "regions": regions}

# --- store: real-mode binding, acceptance, initialisation
binding = bd.verify_combination(ENV, PKG, mode="real", expected_envelope_sha256=env_ref["sha256"])
store, root = LocalObjectStore(os.path.join(OUT, "store")), StoreRoot("real", "gs://local-integration-store/ipcch-v2/real")
initial.install_acceptance(store, root, BUNDLE, binding=binding)
rep = initial.initialise(store, root, BUNDLE, binding=binding)
res["initialise"] = {"initialised": len(rep["initialised"]), "seconds": round(time.time() - t0, 1)}
roster = [str(a) for a in initial._read(store, root, "fixed/roster.csv")["admin_code"]]


class Refuse:
    def __init__(self, what):
        self.what, self.calls = what, []

    def __call__(self, *a, **k):
        self.calls.append(repr(a)[:120])
        raise cl.ClimateProcessingFailure(f"{self.what}: live provider calls are not part of this local integration {a!r}")


refuse_climate = Refuse("climate")
providers = climate_run.ClimateProviders(lambda base: refuse_climate, lambda base: refuse_climate)


class GppHeadOnly:
    """Read-only public HTTPS HEAD probes; downloads refused."""
    def __init__(self):
        self.probes = []

    def _head(self, url):
        if len(self.probes) >= 8:                                  # Supervisor approval: exactly <= 8 probes
            raise RuntimeError("probe budget (8 HEAD requests) exhausted")
        at = datetime.now(timezone.utc).isoformat()
        try:
            status = requests.head(url, timeout=60, allow_redirects=True).status_code
        except Exception as exc:
            self.probes.append({"url": url, "status": None, "error": f"{type(exc).__name__}: {exc}", "at": at})
            raise
        self.probes.append({"url": url, "status": status, "at": at})
        return status

    def _acquire_http(self, *a, **k):
        raise RuntimeError("GPP download is not part of this local integration (a month answered 200)")


class NoViirs:
    def published_months(self, *a, **k):
        raise RuntimeError("VIIRS calls are not part of this local integration")


gpp = GppHeadOnly()
ctx = run_v2.IpcchContext(store=store, root=root, binding=binding, package_root=PKG, bundle_dir=BUNDLE, read_ref=read_ref,
                          climate_providers=lambda windows, origin: providers, gpp_acquirer=gpp, nightlight_acquirer=NoViirs(),
                          workdir=OUT, roster=roster)
keep = {"action": "keep"}
request = {"schema_version": "fewsnet-ipcch-delivery-request-v2", "run_id": "local-real-integration-1", "mode": "real",
           "execution_month": "2026-10",
           "operations": {"ipcch_generation": True, "ipcch_inference": True, "fewsnet_generation": False, "fewsnet_inference": False},
           "ipcch": {"model_combination": {"combination_id": binding.combination_id, "envelope": env_ref},
                     "acled": {"action": "refresh", "file": acled_ref, "start": start, "end": end, "regions": regions},
                     "research_inputs": {f: keep for f in ("nino34_anom", "bbg_staple_food", "bbg_oilgas", "bbg_soybean_oil",
                                                           "bbg_global_food", "food_price_index_WB", "idp_national", "idp_local")},
                     "history_snapshot": keep, "wfp": keep},
           "fewsnet": None, "publication": "candidate",
           "runtime": {"image_uri": "us-central1-docker.pkg.dev/p/r/img@sha256:" + "a" * 64, "environment_manifest": runtime_ref},
           "release": {"namespace": "prod", "expected_pointer_generation": "0"},
           "operator": "executor-local-integration", "prepared_at": "2026-10-30T12:00:00Z"}
admit = dict(request_uri="gs://local-integration/requests/local-real-integration-1/run_manifest.json", request_generation="1",
             now_utc=datetime(2026, 10, 30, 12, tzinfo=timezone.utc), production_namespace="prod", smoke_namespace="smoke",
             current_ipcch_execution_month=None,
             resolve=lambda u, g: hashlib.sha256(objects[(u, g)]).hexdigest() if (u, g) in objects else None,
             trusted_prefixes={"real": ["gs://local-integration/inputs/"]}, batch_roots={"real": root.uri})
out = run_v2.run_request(request, admit_kwargs=admit, ipcch_context=lambda r: ctx)
ip = out["systems"]["ipcch"]
res["status"], res["ipcch_status"] = out["status"], ip["status"]
res["climate_provider_calls"], res["gpp_probes"] = refuse_climate.calls[:10], gpp.probes
if ip["status"] == "failed":
    res["failure"] = {k: ip.get(k) for k in ("reason", "step", "failed_operation")}
    rep = ip.get("report") or {}
    res["failure_report_steps"] = sorted((rep.get("steps") or {}).keys())
    res["failure_warnings"] = rep.get("warnings")
result = ip.get("result") or {}
if "batch" in result:
    res["batch"] = result["batch"]
if "inference" in result:
    inf = result["inference"]
    res["inference"] = {str(h): {"rows": int(len(v["predictions"])), "target_period": v["predictions"]["target_period"].iloc[0],
                                 "feature_period": v["predictions"]["feature_period"].iloc[0],
                                 "phase_counts": {str(k): int(n) for k, n in v["predictions"]["overall_phase_pred"].value_counts().sort_index().items()},
                                 "raw_scores_outside_0_1": v["summary"]["raw_scores_outside_0_1"],
                                 "contract_report": v["summary"]["contract_report"], "mode": sorted(set(v["predictions"]["mode"]))}
                        for h, v in inf["horizons"].items()}
    import cloud.ipcch.batch_inference as bi
    manifest = json.loads(bi.read_pinned(store, res["batch"]["manifest_ref"]))
    res["manifest_generation"] = {k: manifest["generation"][k] for k in ("coverage_end", "gaps", "warnings")}
    res["manifest_identity"] = {k: manifest[k] for k in ("batch_id", "mode", "designation", "execution_month", "feature_origin")}
    res["manifest_combination"] = manifest["combination"]
rec = AcceptanceManifest(store, root).records()
res["acceptance"] = {"delivered": int((rec["kind"] == "delivered").sum()), "runtime": int((rec["kind"] == "runtime").sum())}
res["seconds"] = round(time.time() - t0, 1)
json.dump(res, open(os.path.join(OUT, "result.json"), "w"), indent=1, default=str)
print(json.dumps(res, default=str)[:4000])
sys.exit(0 if res["status"] == "succeeded" else 2)
