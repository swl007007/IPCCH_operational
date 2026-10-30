"""Task 10-29 R60 (Supervisor on 43c6d12): real FEWS NET numerical parity of the v2 adapter - local only, no cloud,
no retraining.

A small subset of the REAL October bootstrap inputs (12 FEWS NET areas in KE and UG: history panel rows, geometry,
roster, family histories; the census; the accepted 0/6/12 local packages) is scored twice on identical inputs:

* reference = the existing ``deliver(system="fewsnet")`` called directly with the legacy inputs (prepared families /
  features of the snapshot, the raw panel, the packages, census, geometry and - for refresh - the existing
  ``wfp_aggregates`` / ``conflict_aggregates`` outputs of the raw exports, exactly as ``run_system._source_frames``);
* v2 = the full v2 route through ``run_v2.run_request``: admission (pinned prepare_request + nested refs), FEWS
  NET-scoped generation (the existing ``prepare.run_prepare`` with a deterministic local raster acquirer), the
  generation source binding, inference through ``publish_scored_member`` with the REAL in-process ``run_system`` ->
  ``deliver``, and v2 publication.

Modes: keep (the canonical SHARED FEWS+IPCCH retained stream of the subset panels) and refresh (format-valid raw
ACLED event and WFP price exports for the subset countries through the existing converters). Every deliver-produced
FEWS NET file of the reference must be byte-identical in the published v2 delivery. Results -> parity-results.json.

Run: ~/.venvs/fewsnet-test-lock-20261022/bin/python fews_parity.py [scratch dir]
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

OP = Path(__file__).resolve().parents[6] / "cloud_pipeline"
sys.path.insert(0, str(OP))

import rasterio  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

from cloud.batch import remote_sources as rs  # noqa: E402
from cloud.common.object_store import LocalObjectStore  # noqa: E402
from cloud.ipcch import fews_adapter as fa  # noqa: E402
from cloud.ipcch import publication as pub  # noqa: E402
from cloud.ipcch import run_v2  # noqa: E402
from cloud.orchestrator import delivery_job as dj  # noqa: E402
from cloud.orchestrator import delivery_manifest as dm  # noqa: E402
from cloud.orchestrator import delivery_request_v2 as v2  # noqa: E402
from cloud.orchestrator import prepare  # noqa: E402
from cloud.orchestrator.deliver import deliver, load_prepared_features, request_diagnostics  # noqa: E402
from tools.refresh_h5_inputs import conflict_aggregates, wfp_aggregates  # noqa: E402

B = OP / "bootstrap"
ORIGIN = "2026-07"
CUTOFF = "2026-08-05T12:00:00Z"
NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)
IMAGE = "us-central1-docker.pkg.dev/p/r/delivery@sha256:" + "c" * 64
COUNTRIES = {"KE": ("KEN", "Kenya"), "UG": ("UGA", "Uganda")}
PER_COUNTRY = 6
NEW_MONTHS = ("2026-05", "2026-06", "2026-07")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def put(store, uri, data: bytes):
    meta = store.write_bytes(uri, data)
    return {"uri": uri, "generation": str(meta.generation), "sha256": sha(data)}


class Reader:
    def __init__(self, store):
        self.store = store

    def read_bytes(self, uri, generation):
        meta = self.store.get_metadata(uri)
        return self.store.read_bytes(uri) if meta and str(meta.generation) == str(generation) else None


class Client:
    def __init__(self, reader):
        self.reader = reader

    def bucket(self, name):
        reader = self.reader

        class Bucket:
            def blob(self, blob, generation=None):
                class Blob:
                    def download_to_filename(self, path):
                        data = reader.read_bytes(f"gs://{name}/{blob}", str(generation))
                        if data is None:
                            raise type("NotFound", (Exception,), {})(blob)
                        Path(path).write_bytes(data)
                return Blob()
        return Bucket()


# --- 1. the real subset -------------------------------------------------------------------------------------------


def subset(scratch: Path) -> dict:
    out = scratch / "subset"
    if (out / "done.json").exists():
        return json.loads((out / "done.json").read_text())
    out.mkdir(parents=True, exist_ok=True)
    ids = pd.concat(pd.read_csv(B / "assets/fewsnet/history_panel.csv", usecols=["FEWSNET_admin_code", "ISO"],
                                dtype=str, chunksize=500000)).drop_duplicates()
    chosen = []
    for iso2 in COUNTRIES:
        chosen += sorted(ids.loc[ids.ISO == iso2, "FEWSNET_admin_code"], key=int)[:PER_COUNTRY]
    keep = set(chosen)
    header = True
    with open(out / "fews_panel.csv", "w", newline="") as handle:          # every column, original row order
        for chunk in pd.read_csv(B / "assets/fewsnet/history_panel.csv", dtype=str, keep_default_na=False,
                                 chunksize=200000):
            rows = chunk[chunk.FEWSNET_admin_code.isin(keep)]
            if len(rows):
                rows.to_csv(handle, index=False, header=header, lineterminator="\n")
                header = False
    geo = json.loads((B / "assets/fewsnet/geometry.geojson").read_text())
    geo["features"] = [f for f in geo["features"] if str(f["properties"]["admin_code"]) in keep]
    (out / "fews_geometry.geojson").write_text(json.dumps(geo))
    pd.DataFrame({"admin_code": chosen}).to_csv(out / "fews_roster.csv", index=False)
    # the census of the subset's countries (a delivery's country tables cover exactly its census countries)
    census = pd.read_csv(B / "assets/fewsnet/population.csv", dtype=str, keep_default_na=False)
    census[census.ISO3.isin([iso3 for iso3, _ in COUNTRIES.values()])].to_csv(out / "fews_census.csv", index=False,
                                                                              lineterminator="\n")
    (out / "history").mkdir(exist_ok=True)
    for family in rs.SYSTEM_FAMILIES["fewsnet"]:
        h = pd.read_csv(B / f"assets/fewsnet/history/{family}.csv", dtype=str, keep_default_na=False)
        h[h.admin_code.isin(keep)].to_csv(out / f"history/fews_{family}.csv", index=False, lineterminator="\n")
    # a tiny IPCCH side: only to make the prepare request's declared IPCCH refs and the SHARED retained stream real
    ip_ids = pd.read_csv(B / "assets/ipcch/roster.csv", dtype=str)["admin_code"].head(3).tolist()
    ip_keep = set(ip_ids)
    header = True
    with open(out / "ipcch_panel.csv", "w", newline="") as handle:
        for chunk in pd.read_csv(B / "assets/ipcch/history_panel.csv", dtype=str, keep_default_na=False,
                                 chunksize=200000):
            rows = chunk[chunk.admin_code.isin(ip_keep)]
            if len(rows):
                rows.to_csv(handle, index=False, header=header, lineterminator="\n")
                header = False
    igeo = json.loads((B / "assets/ipcch/geometry.geojson").read_text())
    igeo["features"] = [f for f in igeo["features"] if str(f["properties"]["admin_code"]) in ip_keep]
    (out / "ipcch_geometry.geojson").write_text(json.dumps(igeo))
    pd.DataFrame({"admin_code": ip_ids}).to_csv(out / "ipcch_roster.csv", index=False)
    for family in rs.SYSTEM_FAMILIES["ipcch"]:
        h = pd.read_csv(B / f"assets/ipcch/history/{family}.csv", dtype=str, keep_default_na=False)
        h[h.admin_code.isin(ip_keep)].to_csv(out / f"history/ipcch_{family}.csv", index=False, lineterminator="\n")
    done = {"fewsnet_areas": chosen, "ipcch_areas": ip_ids}
    (out / "done.json").write_text(json.dumps(done, indent=2))
    return done


def raw_exports(scratch: Path, areas: list[str]) -> dict[str, Path]:
    """Format-valid raw ACLED event / WFP price exports for the subset countries (deterministic)."""
    panel = pd.read_csv(scratch / "subset/fews_panel.csv", dtype=str, usecols=["FEWSNET_admin_code", "ISO", "lat", "lon",
                                                                               "ADMIN1", "ADMIN2"]).drop_duplicates(
        "FEWSNET_admin_code")
    rows = []
    rng = np.random.default_rng(7)
    types = ["Battles", "Explosions/Remote violence", "Violence against civilians"]
    for _, area in panel.iterrows():
        iso3, country = COUNTRIES[area.ISO]
        for month in ("2026-03", "2026-04") + NEW_MONTHS:
            for k in range(2):
                rows.append({"event_date": f"{month}-{10 + k:02d}", "event_type": types[(k + int(area.FEWSNET_admin_code)) % 3],
                             "country": country, "admin1": area.ADMIN1, "admin2": area.ADMIN2,
                             "admin3": f"{area.ADMIN2} A3", "location": f"loc-{area.FEWSNET_admin_code}-{k}",
                             "latitude": round(float(area.lat) + 0.01 * k, 4),
                             "longitude": round(float(area.lon) - 0.01 * k, 4),
                             "fatalities": int(rng.integers(0, 5)), "year": int(month[:4])})
    acled = scratch / "raw/acled_export.csv"
    acled.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(acled, index=False)
    wrows = []
    for iso2, (iso3, country) in COUNTRIES.items():
        for market in ("Central", "North"):
            price = 100.0
            for i, month in enumerate(("2026-01", "2026-02", "2026-03", "2026-04") + NEW_MONTHS):
                price *= 1.0 + 0.01 * (i % 3) + (0.005 if iso2 == "UG" else 0.0)
                y, m = month.split("-")
                wrows.append({"Country": country, "Admin 1": "A1", "Admin 2": "A2", "Market Name": market,
                              "Commodity": "Maize", "Price Type": "Retail", "Price Date": f"15/{m}/{y}",
                              "Price": round(price, 4), "Unit": "KG", "Currency": iso3, "Trend": round(i * 0.5, 3),
                              "Data Type": "Aggregated"})
    wfp = scratch / "raw/wfp_export.csv"
    pd.DataFrame(wrows).to_csv(wfp, index=False)
    return {"acled": acled, "wfp": wfp}


# --- 2. a deterministic local raster acquirer covering the subset --------------------------------------------------


class GridAcquirer:
    """latest/published months through ORIGIN; one GeoTIFF per (family, month) over the subset bounding box."""

    def __init__(self, bounds, workdir_note=""):
        self.bounds, self.acquired = bounds, []

    def latest_published(self, family, *, floor_month, end_month):
        months = [m for m in ("2026-04",) + NEW_MONTHS if floor_month <= m <= end_month]
        return (months[-1], f"{family}:{months[-1]}") if months else None

    def published_months(self, family, *, start_month, end_month):
        return {m: f"{family}:{m}" for m in ("2026-04",) + NEW_MONTHS if start_month <= m <= end_month}

    def acquire(self, family, month, *, provider_id, prepare_id, workdir):
        self.acquired.append((family, month))
        west, south, east, north = self.bounds
        res = 0.05
        width, height = int(np.ceil((east - west) / res)) + 2, int(np.ceil((north - south) / res)) + 2
        bands = rs.SOURCE_CONTRACTS[family].bands
        yy, xx = np.mgrid[0:height, 0:width]
        offset = int(month[-2:])
        data = np.stack([(np.sin(xx / 7.0 + b) + np.cos(yy / 5.0) + offset * 0.1 + b).astype("float32")
                         for b in range(len(bands))])
        path = Path(workdir) / f"{family}_{month}.tif"
        Path(workdir).mkdir(parents=True, exist_ok=True)
        with rasterio.open(path, "w", driver="GTiff", width=width, height=height, count=len(bands), dtype="float32",
                           crs="EPSG:4326", transform=from_origin(west - res, north + res, res, res),
                           nodata=-9999.0) as ds:
            ds.write(data)
            if len(bands) > 1:
                for i, band in enumerate(bands, start=1):
                    ds.set_band_description(i, band)
        raw = path.read_bytes()
        return prepare.AcquiredRaster(str(path), {"uri": f"gs://local-grid/{family}/{month}.tif", "generation": "1",
                                                  "sha256": sha(raw)})


# --- 3. the world (pinned objects) ---------------------------------------------------------------------------------


def world(scratch: Path, mode: str, areas: dict) -> dict:
    root = scratch / f"world-{mode}"
    if root.exists():
        shutil.rmtree(root)
    store = LocalObjectStore(root / "gcs")
    sub = scratch / "subset"
    systems = {}
    for system, prefix in (("fewsnet", "fews"), ("ipcch", "ipcch")):
        systems[system] = {
            "geometry": put(store, f"gs://parity-assets/{system}/geometry.geojson",
                            (sub / f"{prefix}_geometry.geojson").read_bytes()),
            "roster": put(store, f"gs://parity-assets/{system}/roster.csv", (sub / f"{prefix}_roster.csv").read_bytes()),
            "history": {f: put(store, f"gs://parity-assets/{system}/history/{f}.csv",
                               (sub / f"history/{prefix}_{f}.csv").read_bytes()) for f in rs.SYSTEM_FAMILIES[system]}}
    body = {"schema_version": prepare.PREPARE_SCHEMA_VERSION, "prepare_id": f"parity-{mode}", "origin_month": ORIGIN,
            "cutoff_utc": CUTOFF, "extraction_contract_version": rs.EXTRACTION_CONTRACT_VERSION, "systems": systems,
            "operator": "ops@example.org"}
    prep_ref = put(store, f"gs://parity-root/prepare_requests/parity-{mode}/prepare_request.json",
                   json.dumps(body).encode())
    panel = (sub / "fews_panel.csv").read_bytes()
    history_panel = put(store, "gs://parity-assets/fewsnet/history_panel.csv", panel)
    census = (sub / "fews_census.csv").read_bytes()
    contract = {"version": dm.RAW_CONVERTER_CONTRACT_VERSION, "sha256": json.load(open(B / "baseline.json"))["sources"]["acled"]["sha256"]}
    choices, raw = {}, raw_exports(scratch, areas["fewsnet_areas"])
    for name in ("acled", "wfp"):
        if mode == "keep":                         # the canonical SHARED retained stream of the subset panels
            text = "".join(dj.retained_family_rows({"fewsnet": str(sub / "fews_panel.csv"),
                                                    "ipcch": str(sub / "ipcch_panel.csv")}, name)).encode()
            choices[name] = {"action": "keep", "retained_snapshot": put(store, f"gs://parity-assets/retained_{name}.csv", text),
                             "converter_contract": contract}
        else:
            choices[name] = {"action": "refresh", "raw_upload": put(store, f"gs://parity-assets/raw_{name}.csv",
                                                                    raw[name].read_bytes()),
                             "converter_contract": contract}
    env = put(store, "gs://parity-assets/env.json", json.dumps({"image_uri": IMAGE,
                                                               "requirements_lock_sha256": dj.lock_sha256()}).encode())
    models = []
    for h in dm.HORIZONS_MONTHS:
        d = B / f"models/fewsnet/{h}m"
        files = [{"path": p.name, **put(store, f"gs://parity-assets/models/fewsnet/{h}m/{p.name}", p.read_bytes())}
                 for p in sorted(d.iterdir()) if p.is_file()]
        pid = json.loads((d / "local_model_manifest.json").read_text()).get("package_id", f"bootstrap-fewsnet-{h}m")
        manifest = put(store, f"gs://parity-assets/models/fewsnet/{h}m/package_manifest.json", json.dumps({
            "schema_version": dj.PACKAGE_MANIFEST_SCHEMA, "system": "fewsnet", "horizon_months": h, "package_id": pid,
            "files": files}).encode())
        schema = json.loads((d / "training_report.json").read_text())["feature_schema_sha256"]
        model = {"system": "fewsnet", "horizon_months": h, "package_id": pid, "package_manifest": manifest,
                 "feature_schema_sha256": schema}
        model["acceptance_report"] = put(store, f"gs://parity-assets/models/fewsnet/{h}m/acceptance.json", json.dumps({
            "schema_version": dj.ACCEPTANCE_REPORT_SCHEMA, "system": "fewsnet", "horizon_months": h, "package_id": pid,
            "status": "accepted", "package_manifest_sha256": manifest["sha256"], "feature_schema_sha256": schema,
            "runtime": {"image_uri": IMAGE, "environment_manifest_sha256": env["sha256"]}}).encode())
        models.append(model)
    assets = {"fewsnet": {"geometry": systems["fewsnet"]["geometry"], "roster": systems["fewsnet"]["roster"],
                          "population": put(store, "gs://parity-assets/fewsnet/population.csv", census),
                          "country_reference": put(store, "gs://parity-assets/fewsnet/country_reference.csv", census),
                          "history_panel": history_panel}}
    diagnostics = [{"system": "fewsnet", "horizon_months": h, "family": f, "status": "unavailable", "evidence": None,
                    "reason": "missing_evidence"} for h in dm.HORIZONS_MONTHS for f in dm.DIAGNOSTIC_FAMILIES["fewsnet"]]
    contracts = json.load(open(B / "baseline.json"))["delivery"]["contracts"]
    request = {"schema_version": v2.SCHEMA_VERSION, "run_id": f"parity-{mode}", "mode": "real", "execution_month": ORIGIN,
               "operations": {"ipcch_generation": False, "ipcch_inference": False, "fewsnet_generation": True,
                              "fewsnet_inference": True},
               "ipcch": None, "fewsnet": {"acled": choices["acled"], "wfp": choices["wfp"], "prepare_request": prep_ref,
                                          "delivery": {"models": models, "assets": assets, "diagnostics": diagnostics,
                                                       "contracts": contracts}},
               "publication": "current", "runtime": {"image_uri": IMAGE, "environment_manifest": env},
               "release": {"namespace": "prod", "expected_pointer_generation": "0"},
               "operator": "ops@example.org", "prepared_at": "2026-08-20T05:00:00Z"}
    geo = json.loads((sub / "fews_geometry.geojson").read_text())
    coords = np.array([pt for f in geo["features"] for pt in _points(f["geometry"])])
    bounds = (coords[:, 0].min(), coords[:, 1].min(), coords[:, 0].max(), coords[:, 1].max())
    return {"root": root, "store": store, "request": request, "raw": raw, "diagnostics": diagnostics,
            "bounds": bounds, "mode": mode}


def _points(geometry):
    def walk(c):
        if isinstance(c[0], (int, float)):
            yield c[:2]
        else:
            for x in c:
                yield from walk(x)
    return list(walk(geometry["coordinates"]))


# --- 4. the two runs -----------------------------------------------------------------------------------------------


def run_v2_route(w) -> dict:
    store, reader = w["store"], Reader(w["store"])
    data = w["request"]
    admit = dict(request_uri=f"gs://parity-ops/requests/{data['run_id']}/run_manifest.json", request_generation="1",
                 now_utc=NOW, production_namespace="prod", smoke_namespace="smoke", current_ipcch_execution_month=None,
                 resolve=lambda u, g: (lambda b: None if b is None else sha(b))(reader.read_bytes(u, g)),
                 read=reader.read_bytes, trusted_prefixes={"real": ["gs://parity-assets/", "gs://parity-root/"],
                                                           "smoke": ["gs://parity-smoke/"]},
                 batch_roots={"real": "gs://parity-root/ipcch-v2/real", "smoke": "gs://parity-smoke/ipcch-v2/smoke"})
    acquirer = GridAcquirer(w["bounds"])
    runner = fa.runner(store=store, reader=reader, output_root="gs://parity-root", work_root=w["root"] / "work",
                       image_uri=IMAGE, downloader_factory=lambda root: dj.PinnedDownloader(Client(reader), root),
                       score=lambda spec, system, out: dj.run_system(Path(spec), system, Path(out)),
                       acquirer_factory=lambda: acquirer)
    outcome = run_v2.run_request(data, admit_kwargs=admit, fewsnet_runner=runner, deployment=run_v2.Deployment(
        store=store, roots={"real": "gs://parity-root", "smoke": "gs://parity-smoke/v2"}))
    return {"outcome": outcome, "acquired": acquirer.acquired}


def run_reference(w, snapshot) -> Path:
    """The existing deliver(system="fewsnet") with the legacy inputs (run_system's own composition)."""
    store, reader = w["store"], Reader(w["store"])
    manifest = json.loads(store.read_text(snapshot["manifest"]["uri"]))
    out = w["root"] / "reference"
    sub = w["root"].parent / "subset"
    wfp = acled = None
    if w["mode"] == "refresh":
        wfp, _ = wfp_aggregates(w["raw"]["wfp"], cutoff=ORIGIN)
        acled, _ = conflict_aggregates(w["raw"]["acled"], cutoff=ORIGIN)
    deliver(origin=ORIGIN, out=out, prepared_families=manifest["families"],
            prepared_features=load_prepared_features(manifest, reader), ipcch_panel=None, ipcch_template=None,
            ipcch_package_root=None, fewsnet_raw=sub / "fews_panel.csv",
            fewsnet_packages={h: B / f"models/fewsnet/{h}m" for h in dm.HORIZONS_MONTHS},
            census={"fewsnet": sub / "fews_census.csv"}, geometry={"fewsnet": sub / "fews_geometry.geojson"},
            wfp=wfp, acled=acled, system="fewsnet",
            diagnostics=request_diagnostics({"validation_level": "structural", "diagnostics": w["diagnostics"]},
                                            "fewsnet", reader))
    return out


def _v2_out_roots(text: str, publication_id: str) -> set[str]:
    """The (deleted) temporary directory the v2 member was written in, as deliver embedded it in the file."""
    import re
    return set(re.findall(rf"(/(?!/)[^\s\"',#]*?/v2-delivery-{re.escape(publication_id)}-[^/\s\"',#]+/delivery)", text))


def compare(w, reference: Path, publication_id: str) -> dict:
    store = w["store"]
    base = f"gs://parity-root/deliveries/{publication_id}"
    manifest = json.loads(store.read_text(f"{base}/manifest.json"))
    published = {e["path"]: e["sha256"] for e in manifest["files"]}
    files = sorted(p.relative_to(reference).as_posix() for p in reference.rglob("*") if p.is_file())
    same, differ, missing = [], [], []
    for rel in files:
        digest = sha((reference / rel).read_bytes())
        if rel not in published:
            missing.append(rel)
        elif published[rel] == digest:
            same.append(rel)
        else:
            differ.append(rel)
    # deliver embeds its own output directory in file:// provenance refs: compare those files with each run's root
    # replaced by one placeholder (and nothing else changed)
    # a file identical modulo the output root is cited elsewhere by its sha256: such a citation is mapped to the
    # reference digest (only for files proven identical modulo the root, in dependency order)
    normalized, cited = {}, {}
    for rel in sorted(differ, key=lambda r: (not r.endswith(".json"), r)):
        ref_text = (reference / rel).read_text().replace(str(reference), "<OUT>")
        v2_text = store.read_bytes(f"{base}/{rel}").decode()
        for root in _v2_out_roots(v2_text, publication_id):
            v2_text = v2_text.replace(root, "<OUT>")
        for v2_sha, ref_sha in cited.items():
            v2_text = v2_text.replace(v2_sha, ref_sha)
        normalized[rel] = ref_text == v2_text
        if normalized[rel]:
            cited[published[rel]] = sha((reference / rel).read_bytes())
    return {"reference_files": len(files), "identical": len(same), "differ": differ, "missing_in_v2": missing,
            "differ_identical_after_output_root_normalization": normalized,
            "all_identical_modulo_output_root": not missing and all(normalized.values()),
            "scope_tables_identical": all(r in same for r in files if r.startswith("scopes/")),
            "prediction_sha256": {r: published.get(r) for r in files if r.endswith("polygon_predictions.csv")}}


def main(scratch: Path) -> dict:
    scratch.mkdir(parents=True, exist_ok=True)
    areas = subset(scratch)
    results = {"origin": ORIGIN, "areas": areas, "packages": {h: sha((B / f"models/fewsnet/{h}m/model.joblib").read_bytes())
                                                               for h in dm.HORIZONS_MONTHS}, "modes": {}}
    for mode in ("keep", "refresh"):
        w = world(scratch, mode, areas)
        v2out = run_v2_route(w)
        fews = v2out["outcome"]["systems"]["fewsnet"]
        entry = {"v2_status": v2out["outcome"]["status"], "v2_reason": fews.get("reason"),
                 "acquired": sorted({f for f, _ in v2out["acquired"]})}
        if fews["status"] == "succeeded":
            snapshot = fews["result"]["generation"]["prepared_snapshot"]
            reference = run_reference(w, snapshot)
            entry.update(compare(w, reference, fews["result"]["publication"]["publication_id"]))
            entry["pointer"] = pub.read_current(w["store"], "gs://parity-root", "prod")["record"]["systems"]["fewsnet"][
                "published_by_run"]
        results["modes"][mode] = entry
        print(mode, json.dumps({k: v for k, v in entry.items() if k != "prediction_sha256"}, default=str)[:1500])
    return results


if __name__ == "__main__":
    scratch = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "scratch/ipcch-fews-parity")
    res = main(scratch)
    target = Path(__file__).with_name("parity-results.json")
    target.write_text(json.dumps(res, indent=2, sort_keys=True, default=str) + "\n")
    print("wrote", target)
