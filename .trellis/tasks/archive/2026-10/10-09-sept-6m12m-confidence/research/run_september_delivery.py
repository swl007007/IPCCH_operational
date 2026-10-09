"""Step 5 (gate G5): September-origin (O=2026-09) delivery through the cloud delivery code.

No training and no runtime code change. Subcommands, run in order with the lock-equivalent
interpreter from ``cloud_pipeline/``:

    prepare   read-only GCS downloads (pinned generation + sha256, fail closed); operator
              ``pipeline.initialize`` of the bound bootstrap against a local create-only object
              store; request built in ``pipeline.run`` shape; structural validation and
              ``verify_reference_identities``; the ``delivery_job.prepare_inputs`` checks
              (see PREPARE_DEVIATION) -> spec.json
    system S  ``python -m cloud.orchestrator.delivery_job system`` under ``/usr/bin/time -v``
    package   ``delivery_job.package_delivery`` (finalize, runtime/models, validation,
              inventory, archive) inside the workdir; archive is a validation gate only (D16)
    report    run/september_run.json + G5 checks -> research/september_run_g5.json

Workdir (Linux FS): ~/work/sept-6m12m-20261009/
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
CP = REPO / "cloud_pipeline"
sys.path.insert(0, str(CP))

WORK = Path.home() / "work/sept-6m12m-20261009"
RUN_ID = "sept-6m12m-20261009a"
ORIGIN = "2026-09"
PREPARE_ID = "full-window-20261008c"
LOCAL_BUCKET = "sept-local-baseline"           # local object store standing in for the operator bucket
LOCAL_REQUEST_BUCKET = "sept-local-requests"
NAMESPACE = "sept-local"
OCT_REQUEST = {"uri": "gs://manuel-remote-sensing-oct-delivery-requests/requests/oct-final-20261008a/run_manifest.json",
               "generation": "1791484415757028",
               "sha256": "0a519a265605bcefc9c6e70621d31d2f6e50542c88fc02194cab221fc9594c6a"}
PREPARED = {"uri": f"gs://manuel-remote-sensing-oct-delivery-debug/prepared/{PREPARE_ID}/prepared_manifest.json",
            "generation": "1791484258622845",
            "sha256": "bb367e21854643ecaf16a0603082c96d331c19233624f36dc076980f0864bcec"}
PREPARE_DEVIATION = (
    "delivery_job.prepare_inputs requires prepared_manifest.origin_month == request origin_month. The reused October "
    "snapshot is labelled 2026-10 while this run's origin is 2026-09 (D2/D6). All other prepare_inputs checks run "
    "unchanged through the same functions (reference identities, extraction contract, roster/geometry binding, "
    "family outputs, environment, acceptance, package materialisation, feature schema, keep-family projection). "
    "The prepared manifest is not edited; the request declares prepared_snapshot.origin_month=2026-09 because "
    "structural validation requires it to equal origin_month. Content bound: every prepared feature month <= 2026-08.")


def sha_file(path) -> str:
    digest = hashlib.sha256()
    for attempt in range(5):
        try:
            with open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 22), b""):
                    digest.update(block)
            return digest.hexdigest()
        except OSError:  # Dropbox DrvFS intermittent EIO
            if attempt == 4:
                raise
            digest = hashlib.sha256()
            time.sleep(2)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gcs_download(ref: dict, target: Path) -> Path:
    """Read-only ``gcloud storage cp`` at the pinned generation; fail closed on sha256 mismatch."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        partial = target.with_name(target.name + ".partial")
        if partial.exists():
            partial.unlink()
        # Sliced parallel downloads hung at finalisation on this host; single-stream instead.
        env = {**os.environ, "CLOUDSDK_STORAGE_SLICED_OBJECT_DOWNLOAD_THRESHOLD": "0"}
        subprocess.run(["gcloud", "storage", "cp", f"{ref['uri']}#{ref['generation']}", str(partial)], check=True,
                       capture_output=True, text=True, env=env, timeout=1800)
        partial.rename(target)
    actual = sha_file(target)
    if actual != ref["sha256"]:
        raise SystemExit(f"sha256 mismatch for {ref['uri']}#{ref['generation']}: {actual}")
    return target


def local_name(uri: str, generation: str) -> str:
    bucket, _, name = uri.removeprefix("gs://").partition("/")
    return f"{bucket}/{name}#{generation}"


class LocalStore:
    """Create-only local object store with the ``pipeline.Cloud`` put/latest/launch surface.

    ``put`` copies the file onto the Linux FS (isolates the run from DrvFS) and returns a pinned
    ref with generation "1"; a second put of the same URI must have identical bytes.
    """

    def __init__(self, root: Path):
        self.root, self.index = Path(root), {}
        self.index_path = self.root / "index.json"
        if self.index_path.exists():
            self.index = json.loads(self.index_path.read_text())

    def put(self, uri, path):
        key = f"{uri}#1"
        digest = sha_file(path)
        if key in self.index:
            if sha_file(self.index[key]) != digest:
                raise ValueError(f"create-only conflict at {uri}")
        else:
            target = self.root / "objects" / local_name(uri, "1")
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "rb") as source, target.open("xb") as handle:
                shutil.copyfileobj(source, handle, length=1 << 22)
            if sha_file(target) != digest:
                raise ValueError(f"copy changed bytes: {path}")
            self.index[key] = str(target)
            self.index_path.write_text(json.dumps(self.index, indent=1, sort_keys=True) + "\n")
        return {"uri": uri, "generation": "1", "sha256": digest}

    def latest(self, uri):
        return None

    def launch(self, ref, deadline):
        raise AssertionError("no launch in a local run")


class LocalDownloader:
    """``PinnedDownloader`` surface (resolve/fetch/paths) over local verified copies; no network."""

    def __init__(self, index: dict[str, str]):
        self.paths = {key: Path(path) for key, path in index.items()}

    def resolve(self, uri, generation):
        path = self.paths.get(f"{uri}#{generation}")
        return None if path is None or not path.exists() else sha_file(path)

    def fetch(self, ref):
        from cloud.orchestrator.delivery_job import AcceptanceError

        actual = self.resolve(ref["uri"], ref["generation"])
        if actual is None:
            raise AcceptanceError(f"{ref['uri']}#{ref['generation']} not found")
        if actual != ref["sha256"]:
            raise AcceptanceError(f"sha256 mismatch for {ref['uri']}#{ref['generation']}")
        return self.paths[f"{ref['uri']}#{ref['generation']}"]


def prepare_inputs_except_origin(request, downloader, work: Path, *, image_uri: str) -> tuple[dict, dict]:
    """``delivery_job.prepare_inputs`` with the single PREPARE_DEVIATION; returns (spec, checks)."""
    from cloud.batch.remote_sources import EXTRACTION_CONTRACT_VERSION, SYSTEM_FAMILIES
    from cloud.orchestrator import delivery_job as dj
    from cloud.orchestrator.delivery_manifest import verify_reference_identities

    checks = {}
    if request["runtime"]["image_uri"] != image_uri:
        raise dj.AcceptanceError("image mismatch")
    verified = verify_reference_identities(request, downloader.resolve)
    checks["reference_identities_verified"] = len(verified)
    index = {f"{ref['uri']}#{ref['generation']}": str(downloader.paths[f"{ref['uri']}#{ref['generation']}"])
             for ref in verified}
    prepared_path = downloader.fetch(request["prepared_snapshot"]["manifest"])
    prepared = json.loads(prepared_path.read_text())
    if (prepared.get("prepare_id"), prepared.get("status")) != (request["prepared_snapshot"]["prepare_id"], "succeeded"):
        raise dj.AcceptanceError("prepared manifest is not a succeeded snapshot for the requested prepare_id")
    checks["prepared_status"] = prepared["status"]
    checks["prepared_manifest_origin_label"] = prepared["origin_month"]
    checks["request_origin_month"] = request["origin_month"]
    checks["origin_equality_check"] = "skipped (PREPARE_DEVIATION)"
    if prepared.get("extraction_contract_version") != EXTRACTION_CONTRACT_VERSION:
        raise dj.AcceptanceError("extraction contract mismatch")
    checks["extraction_contract_version"] = EXTRACTION_CONTRACT_VERSION
    for system, kinds in request["assets"].items():
        for kind in ("roster", "geometry"):
            prepared_ref = prepared.get("systems", {}).get(system, {}).get(kind, {}).get("sha256")
            if prepared_ref != kinds[kind]["sha256"]:
                raise dj.AcceptanceError(f"{system}: prepared {kind} {prepared_ref} != delivery {kinds[kind]['sha256']}")
        for family in SYSTEM_FAMILIES[system]:
            if system not in prepared["families"].get(family, {}).get("outputs", {}):
                raise dj.AcceptanceError(f"prepared snapshot lacks {family} outputs for {system}")
    checks["prepared_roster_geometry_bound"] = True
    for family in prepared["families"].values():
        for ref in family.get("outputs", {}).values():
            index[f"{ref['uri']}#{ref['generation']}"] = str(downloader.fetch(ref))
    dj.check_environment(downloader.fetch(request["runtime"]["environment_manifest"]), request["runtime"])
    checks["environment"] = "passed"
    packages = {"fewsnet": {}, "ipcch": None}
    for model in request["models"]:
        system, horizon = model["system"], model["horizon_months"]
        dj.check_acceptance(downloader.fetch(model["acceptance_report"]), model, request["runtime"])
        target = work / ("packages/fewsnet" if system == "fewsnet" else "packages/ipcch") / (
            f"{horizon}m" if system == "fewsnet" else "")
        dj.materialize_package(downloader.fetch(model["package_manifest"]), downloader, target, system=system,
                               horizon=horizon, package_id=model["package_id"])
        if system == "fewsnet":
            packages["fewsnet"][horizon] = str(target)
        else:
            packages["ipcch"] = str(work / "packages/ipcch")
    for model in request["models"]:
        directory = packages["fewsnet"][model["horizon_months"]] if model["system"] == "fewsnet" else packages["ipcch"]
        actual = dj.package_schema_sha256(model["system"], model["horizon_months"], Path(directory))
        if actual != model["feature_schema_sha256"]:
            raise dj.AcceptanceError(f"{model['system']}/{model['horizon_months']}m feature schema mismatch")
    checks["acceptance_and_feature_schema"] = "passed (6 packages)"
    assets = {system: {kind: str(downloader.fetch(ref)) for kind, ref in kinds.items()}
              for system, kinds in request["assets"].items()}
    history = {system: assets[system]["history_panel"] for system in assets}
    for name in ("acled", "wfp"):
        if request[name]["action"] == "keep":
            expected = dj.retained_family_sha256(history, name)
            if expected != request[name]["retained_snapshot"]["sha256"]:
                raise dj.AcceptanceError(f"{name}: retained snapshot != family projection ({expected})")
            checks[f"{name}_keep_projection_sha256"] = expected
    sources = {name: {"action": request[name]["action"],
                      "path": str(downloader.fetch(request[name]["retained_snapshot" if request[name]["action"] == "keep"
                                                             else "raw_upload"]))}
               for name in ("acled", "wfp")}
    spec = {"origin": request["origin_month"], "prepared_manifest": str(prepared_path), "reader_index": index,
            "packages": packages, "assets": assets, "sources": sources, "verified_refs": verified}
    return spec, checks


def cmd_prepare() -> None:
    import pipeline as p
    from cloud.orchestrator.delivery_manifest import validate_delivery_request

    WORK.mkdir(parents=True, exist_ok=True)
    gcs = WORK / "inputs/gcs"
    record = {"started_at": now(), "downloads": {}}
    # 1. Read-only pinned downloads.
    oct_request_path = gcs_download(OCT_REQUEST, gcs / "oct_run_manifest.json")
    oct_request = json.loads(oct_request_path.read_text())
    if oct_request["prepared_snapshot"]["manifest"] != PREPARED:
        raise SystemExit("October request does not reference the expected prepared manifest")
    prepared_path = gcs_download(PREPARED, gcs / "objects" / local_name(PREPARED["uri"], PREPARED["generation"]))
    prepared = json.loads(prepared_path.read_text())
    gcs_index = {f"{PREPARED['uri']}#{PREPARED['generation']}": str(prepared_path)}
    feature_months = {}
    import pandas as pd

    for family, entry in prepared["families"].items():
        for system, ref in entry["outputs"].items():
            path = gcs_download(ref, gcs / "objects" / local_name(ref["uri"], ref["generation"]))
            gcs_index[f"{ref['uri']}#{ref['generation']}"] = str(path)
            record["downloads"][f"prepared.{family}.{system}"] = ref
            months = pd.read_csv(path, dtype={"admin_code": str, "month": str}, usecols=["month"])["month"]
            feature_months[f"{family}/{system}"] = {"min": months.min(), "max": months.max(), "rows": int(len(months))}
    if max(v["max"] for v in feature_months.values()) > ORIGIN:
        raise SystemExit(f"prepared features contain months after origin {ORIGIN}: {feature_months}")
    retained_oct = {}
    for family in ("acled", "wfp"):
        ref = oct_request[family]["retained_snapshot"]
        path = gcs_download(ref, gcs / "objects" / local_name(ref["uri"], ref["generation"]))
        retained_oct[family] = {"ref": ref, "path": str(path)}
        record["downloads"][f"october_retained.{family}"] = ref
    record["downloads"]["october_request"] = OCT_REQUEST
    record["downloads"]["prepared_manifest"] = PREPARED
    record["prepared_feature_months"] = feature_months
    # 2. Operator init of the bound bootstrap (real pipeline.initialize, local create-only store).
    baseline_path = CP / "bootstrap/baseline.json"
    baseline = json.loads(baseline_path.read_text())
    cfg = dict(project="sept-local", bucket=LOCAL_BUCKET, request_bucket=LOCAL_REQUEST_BUCKET,
               image_uri=baseline["runtime"]["image_uri"], namespace=NAMESPACE, work_dir=str(WORK / "init"),
               region="us-central1", service_account="sept-local@example.com", prepare_job="none",
               earth_engine_project="sept-local", operator="trellis-implement 10-09-sept-6m12m-confidence")
    store = LocalStore(WORK / "store")
    record["initialize_preview"] = p.initialize(NS(baseline=str(CP / "bootstrap"), execute=False), cfg)
    record["initialize"] = p.initialize(NS(baseline=str(CP / "bootstrap"), execute=True), cfg, cloud=store)
    init = json.loads((WORK / "init/initialized.json").read_text())
    if init["baseline_id"] != sha_file(baseline_path):
        raise SystemExit("initialized baseline id differs from bootstrap/baseline.json")
    # October retained snapshots == bootstrap retained assets (same bytes; keep binds the same projection).
    record["october_retained_equals_bootstrap"] = {
        family: retained_oct[family]["ref"]["sha256"] == init["refs"][f"assets/retained_{family}.csv"]["sha256"]
        for family in ("acled", "wfp")}
    if not all(record["october_retained_equals_bootstrap"].values()):
        raise SystemExit(f"October retained snapshots differ from bootstrap: {record['october_retained_equals_bootstrap']}")
    # 3. Request in pipeline.run shape (pipeline.py run(): request = deepcopy(init['delivery']) ...).
    refs = init["refs"]
    request = copy.deepcopy(init["delivery"])
    request.update(run_id=RUN_ID, origin_month=ORIGIN, models=init["models"], runtime=init["runtime"],
                   prepared_snapshot={"prepare_id": PREPARE_ID, "origin_month": ORIGIN, "manifest": PREPARED},
                   operator=cfg["operator"], prepared_at=now())
    request["assets"] = {s: {k: refs[f"assets/{s}/{filename}"] for k, filename in [
        ("geometry", "geometry.geojson"), ("roster", "roster.csv"), ("population", "population.csv"),
        ("country_reference", "population.csv"), ("history_panel", "history_panel.csv")]} for s in p.SYSTEMS}
    request["assets"]["ipcch"]["fixed_features"] = refs["assets/ipcch/fixed_features.csv"]
    for family in ("acled", "wfp"):
        request[family] = {"action": "keep", "converter_contract": init["sources"][family],
                           "retained_snapshot": refs[f"assets/retained_{family}.csv"]}
    request["release"] = {"namespace": NAMESPACE, "expected_pointer_generation": "0"}
    raw = json.dumps(request, indent=2, sort_keys=True).encode()
    run = WORK / "run"
    run.mkdir(exist_ok=True)
    request_path = run / "request.json"
    if request_path.exists() and request_path.read_bytes() != raw:
        raise SystemExit("run/request.json exists with different content; use a new run ID")
    request_path.write_bytes(raw)
    request_uri = f"gs://{LOCAL_REQUEST_BUCKET}/requests/{RUN_ID}/run_manifest.json"
    validated = validate_delivery_request(json.loads(raw), request_uri=request_uri, request_generation="1",
                                          expected_release_namespace=NAMESPACE)
    # 4. prepare_inputs checks over local verified copies.
    downloader = LocalDownloader({**store.index, **gcs_index})
    spec, checks = prepare_inputs_except_origin(validated, downloader, run, image_uri=cfg["image_uri"])
    spec_path = run / "spec.json"
    spec_path.write_text(json.dumps({**spec, "request_path": str(request_path)}, default=str, indent=1))
    record.update(finished_at=now(), baseline_id=init["baseline_id"], request_sha256=hashlib.sha256(raw).hexdigest(),
                  request_uri_local_label=request_uri, prepare_checks=checks, prepare_deviation=PREPARE_DEVIATION,
                  spec=str(spec_path))
    (run / "prepare_record.json").write_text(json.dumps(record, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({k: record[k] for k in ("baseline_id", "request_sha256", "prepare_checks",
                                              "october_retained_equals_bootstrap")}, indent=1))


def cmd_system(system: str) -> None:
    run = WORK / "run"
    out = WORK / "delivery"
    log = run / f"system_{system}.time.log"
    started = time.time()
    with log.open("w") as handle:
        result = subprocess.run(["/usr/bin/time", "-v", sys.executable, "-B", "-m", "cloud.orchestrator.delivery_job",
                                 "system", "--spec", str(run / "spec.json"), "--system", system, "--out", str(out)],
                                cwd=CP, stdout=handle, stderr=subprocess.STDOUT)
    elapsed = round(time.time() - started, 1)
    text = log.read_text()
    rss = next((int(line.split(":")[1]) for line in text.splitlines() if "Maximum resident set size" in line), None)
    summary = {"system": system, "exit": result.returncode, "elapsed_seconds": elapsed, "peak_rss_kb": rss,
               "interpreter": sys.executable, "finished_at": now()}
    (run / f"system_{system}.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary))
    if result.returncode:
        raise SystemExit(result.returncode)


def cmd_package() -> None:
    from cloud.orchestrator import delivery_job as dj

    run = WORK / "run"
    spec = json.loads((run / "spec.json").read_text())
    request = json.loads((run / "request.json").read_text())
    request = {**request, "request": {"uri": f"gs://{LOCAL_REQUEST_BUCKET}/requests/{RUN_ID}/run_manifest.json",
                                      "generation": "1"}}
    started = time.time()
    packaged = dj.package_delivery(WORK / "delivery", spec, request, image_uri=request["runtime"]["image_uri"])
    summary = {"validation": packaged["validation"], "archive": str(packaged["archive"]),
               "archive_sha256": sha_file(packaged["archive"]), "elapsed_seconds": round(time.time() - started, 1),
               "steps": ["finalize", "reports/delivery.json", "install_runtime_and_models", "write_bundle_docs",
                         "write_inventory (validate_delivery)", "build_archive"], "finished_at": now()}
    (run / "package.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    if packaged["validation"] != "passed":
        raise SystemExit(1)


def cmd_report() -> None:
    import pandas as pd

    run, out = WORK / "run", WORK / "delivery"
    prepare = json.loads((run / "prepare_record.json").read_text())
    systems = {s: json.loads((run / f"system_{s}.json").read_text()) for s in ("ipcch", "fewsnet")}
    package = json.loads((run / "package.json").read_text())
    manifest = json.loads((out / "manifest.json").read_text())
    availability = pd.read_csv(out / "reports/diagnostic_availability.csv", dtype=str, keep_default_na=False)
    g5 = {"validation_passed": manifest["validation"]["status"] == "passed"}
    tables = sorted(p.relative_to(out).as_posix() for p in out.glob("scopes/*/*/*.csv"))
    g5["scope_table_count"] = len(tables)
    months = {}
    for horizon, target in ((0, "2026-09"), (6, "2027-03"), (12, "2027-09")):
        for system in ("fewsnet", "ipcch"):
            frame = pd.read_csv(out / f"scopes/{horizon}m/{system}/polygon_model_mapping.csv", dtype=str,
                                keep_default_na=False)
            months[f"{system}/{horizon}m"] = {
                "feature": sorted(frame["feature_month"].unique()), "target": sorted(frame["target_month"].unique()),
                "horizon": sorted(frame["horizon_months"].unique()),
                "expected_target": target, "rows": len(frame)}
    g5["months"] = months
    g5["months_ok"] = all(v["feature"] == [ORIGIN] and v["target"] == [v["expected_target"]] for v in months.values())
    reasons = availability.groupby(["model_system", "horizon_months", "status", "reason"], dropna=False).size()
    g5["availability_counts"] = {"/".join(map(str, k)): int(v) for k, v in reasons.items()}
    missing = availability[availability["reason"].eq("missing_evidence")]
    g5["missing_evidence_6m_12m_rows"] = int(missing["horizon_months"].isin(["6", "12"]).sum())
    g5["fewsnet_0m_missing_evidence_rows"] = int((missing["model_system"].eq("fewsnet") & missing["horizon_months"].eq("0")).sum())
    g5["passed"] = (g5["validation_passed"] and g5["scope_table_count"] == 30 and g5["months_ok"]
                    and g5["missing_evidence_6m_12m_rows"] == 0 and g5["fewsnet_0m_missing_evidence_rows"] > 0
                    and set(missing["model_system"] + "/" + missing["horizon_months"]) == {"fewsnet/0"})
    september_run = {
        "schema_version": "september-origin-run-v1", "run_id": RUN_ID, "origin_month": ORIGIN,
        "targets": {"0m": "2026-09", "6m": "2027-03", "12m": "2027-09"}, "published_scopes": ["6m", "12m"],
        "prepared_snapshot": {"prepare_id": PREPARE_ID, "manifest": PREPARED,
                              "manifest_origin_month_label": prepare["prepare_checks"]["prepared_manifest_origin_label"],
                              "run_origin_month": ORIGIN, "feature_months": prepare["prepared_feature_months"],
                              "label_note": PREPARE_DEVIATION},
        "october_request": OCT_REQUEST, "downloads": prepare["downloads"],
        "october_retained_equals_bootstrap": prepare["october_retained_equals_bootstrap"],
        "source_choices": {"acled": "keep", "wfp": "keep"},
        "baseline_id": prepare["baseline_id"], "request_sha256": prepare["request_sha256"],
        "prepare_checks": prepare["prepare_checks"], "systems": systems, "package": package,
        "validation": manifest["validation"]["status"],
        "interpreter": sys.executable, "python": sys.version.split()[0],
        "requirements_lock_sha256": sha_file(CP / "requirements.lock.txt"),
        "steps_run": ["prepare (pipeline.initialize local store, pipeline.run-shape request, validate_delivery_request, "
                      "verify_reference_identities, prepare_inputs checks except origin label)",
                      "delivery_job system ipcch", "delivery_job system fewsnet", *package["steps"]],
        "g5": g5}
    # Sidecar outside the sealed delivery root (inventory/archive are already written).
    (run / "september_run.json").write_text(json.dumps(september_run, indent=1, sort_keys=True, default=str) + "\n")
    (HERE.parent / "september_run_g5.json").write_text(json.dumps(september_run, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps(g5, indent=1, default=str))
    if not g5["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "prepare":
        cmd_prepare()
    elif command == "system":
        cmd_system(sys.argv[2])
    elif command == "package":
        cmd_package()
    elif command == "report":
        cmd_report()
    else:
        raise SystemExit(f"unknown command {command}")
