"""Request-driven October delivery (CP4): one immutable request -> scoring -> package -> release.

    python -m cloud.orchestrator.delivery_job run --request-uri gs://B/requests/<run_id>/run_manifest.json \
        --request-generation G --output-root gs://B --release-namespace NS --image-uri IMAGE@sha256:D

Invoked by Workflows from a Cloud Storage finalized event (deploy/october_delivery/workflow.yaml) as a
Cloud Run job with task retries 0. Order:

1. Read the request at its exact event generation; structural validation with the configured
   release namespace; the job's own image must equal ``runtime.image_uri``.
2. ``run_once``: identical duplicates return the original status; another request under the
   same run ID conflicts; failed/abandoned runs are never resumed (retry = new run ID).
3. Every referenced object is streamed to local disk at its pinned generation and its SHA-256
   is checked (``verify_reference_identities``; one copy, never buffered twice). Prepared
   feature refs inside the prepared manifest are fetched the same way.
4. The prepared snapshot must have succeeded for this prepare ID/origin and must have been prepared
   for exactly the delivery rosters (a bounded smoke snapshot is never a full-roster preparation);
   model acceptance reports must accept their exact package/system/horizon.
5. Each system is scored in its own process (bounded memory), then sidecars are finalized, the
   runtime/models installed, the delivery validated, inventoried, sealed and archived.
6. Outputs are uploaded create-only under ``deliveries/<run_id>/``; the release record and the
   pointer (generation CAS) are written last by ``delivery_run.publish``.

``deliver_job`` remains a CP3 debug entry only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
try:
    from google.api_core.exceptions import PreconditionFailed
    from google.cloud.storage.retry import DEFAULT_RETRY

    UPLOAD_RETRY = DEFAULT_RETRY.with_deadline(1800)
except ImportError:  # pragma: no cover - local environments without the GCS client
    class PreconditionFailed(Exception):  # never raised: nothing else is swallowed without the client
        pass

    UPLOAD_RETRY = None
PACKAGE_MANIFEST_SCHEMA = "delivery-package-manifest-v1"
ACCEPTANCE_REPORT_SCHEMA = "delivery-model-acceptance-v1"


class AcceptanceError(ValueError):
    """A request is structurally valid but fails an acceptance requirement; nothing is scored."""


def _stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class PinnedDownloader:
    """Streams exact object generations to disk once; ``resolve`` returns the actual SHA-256."""

    def __init__(self, client, root: Path):
        self.client, self.root, self.paths = client, Path(root), {}

    def resolve(self, uri: str, generation: str) -> str | None:
        key = f"{uri}#{generation}"
        if key not in self.paths:
            bucket, _, name = uri.removeprefix("gs://").partition("/")
            target = self.root / hashlib.sha256(key.encode()).hexdigest()[:16] / Path(name).name
            target.parent.mkdir(parents=True, exist_ok=True)
            blob = self.client.bucket(bucket).blob(name, generation=int(generation))
            try:
                blob.download_to_filename(target)  # streamed to disk at the pinned generation
            except Exception as exc:
                if exc.__class__.__name__ in {"NotFound", "FakeNotFound"}:
                    return None
                raise
            self.paths[key] = target
        return _stream_sha256(self.paths[key])

    def fetch(self, ref: Mapping[str, str]) -> Path:
        """Local path of a pinned object whose bytes match ``ref['sha256']``."""
        actual = self.resolve(ref["uri"], ref["generation"])
        if actual is None:
            raise AcceptanceError(f"{ref['uri']}#{ref['generation']} not found")
        if actual != ref["sha256"]:
            raise AcceptanceError(f"sha256 mismatch for {ref['uri']}#{ref['generation']}")
        return self.paths[f"{ref['uri']}#{ref['generation']}"]


class LocalPinnedReader:
    """``read_pinned`` reader over already verified local copies (no network)."""

    def __init__(self, index: Mapping[str, str]):
        self.index = dict(index)

    def read_bytes(self, uri: str, generation: str) -> bytes | None:
        path = self.index.get(f"{uri}#{generation}")
        return None if path is None else Path(path).read_bytes()


def materialize_package(manifest_path: Path, downloader: PinnedDownloader, target: Path, *, system: str,
                        horizon: int, package_id: str) -> Path:
    """Copy every pinned package file into ``target`` at its relative path (manifest is exact)."""
    import shutil

    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get("schema_version") != PACKAGE_MANIFEST_SCHEMA:
        raise AcceptanceError(f"package manifest schema must be {PACKAGE_MANIFEST_SCHEMA}")
    if (manifest.get("system"), manifest.get("horizon_months"), manifest.get("package_id")) != (system, horizon, package_id):
        raise AcceptanceError(f"package manifest is not {system}/{horizon}m/{package_id}")
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise AcceptanceError(f"package path escapes its root: {entry['path']}")
        destination = Path(target) / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = downloader.fetch(entry)
        if destination.exists():  # shared IPCCH root: a member may be reused only with identical bytes
            if _stream_sha256(destination) != entry["sha256"]:
                raise AcceptanceError(f"conflicting package member {entry['path']} for {system}/{horizon}m")
            continue
        shutil.copyfile(source, destination)
    return Path(target)


def package_schema_sha256(system: str, horizon: int, package_dir: Path) -> str:
    """Feature schema identity of a materialized package: FEWSNET's recorded training-report schema
    hash; IPCCH: the scope's feature contract bytes."""
    if system == "fewsnet":
        return json.loads((Path(package_dir) / "training_report.json").read_text())["feature_schema_sha256"]
    return _stream_sha256(Path(package_dir) / f"scope_{horizon}m/feature_contract.csv")


def lock_sha256() -> str:
    lock = REPO / "requirements.lock.txt"
    return _stream_sha256(lock if lock.exists() else REPO / "deploy/october_delivery/requirements.lock.txt")


def check_acceptance(report_path: Path, model: Mapping[str, Any], runtime: Mapping[str, Any]) -> None:
    """The report must accept exactly this package (manifest bytes), feature schema and runtime identity."""
    report = json.loads(Path(report_path).read_text())
    expected = {"schema_version": ACCEPTANCE_REPORT_SCHEMA, "system": model["system"],
                "horizon_months": model["horizon_months"], "package_id": model["package_id"], "status": "accepted",
                "package_manifest_sha256": model["package_manifest"]["sha256"],
                "feature_schema_sha256": model["feature_schema_sha256"],
                "runtime": {"image_uri": runtime["image_uri"],
                            "environment_manifest_sha256": runtime["environment_manifest"]["sha256"]}}
    actual = {key: report.get(key) for key in expected}
    if actual != expected:
        raise AcceptanceError(f"acceptance report does not accept {model['system']}/{model['horizon_months']}m/"
                              f"{model['package_id']} with this schema/runtime: {actual}")


def check_environment(manifest_path: Path, runtime: Mapping[str, Any]) -> None:
    """The pinned environment manifest must describe this image and its exact dependency lock."""
    environment = json.loads(Path(manifest_path).read_text())
    expected = {"image_uri": runtime["image_uri"], "requirements_lock_sha256": lock_sha256()}
    actual = {key: environment.get(key) for key in expected}
    if actual != expected:
        raise AcceptanceError(f"environment manifest {actual} does not describe the running image {expected}")


def require_supported_extraction_contract(prepared: Mapping[str, Any]) -> str:
    """A prepared snapshot must use a readable extraction contract (legacy v1 or current)."""
    from cloud.batch.remote_sources import ACCEPTED_EXTRACTION_CONTRACT_VERSIONS

    version = prepared.get("extraction_contract_version")
    if version not in ACCEPTED_EXTRACTION_CONTRACT_VERSIONS:
        raise AcceptanceError(f"prepared extraction contract {version} is not one of "
                              f"{ACCEPTED_EXTRACTION_CONTRACT_VERSIONS}")
    return version


def prepare_inputs(request: Mapping[str, Any], downloader: PinnedDownloader, work: Path, *, image_uri: str) -> dict:
    """Verify every pinned reference, acceptance and runtime; return the local scoring spec."""
    from cloud.orchestrator.delivery_manifest import verify_reference_identities

    if request["runtime"]["image_uri"] != image_uri:
        raise AcceptanceError(f"job image {image_uri} is not the request runtime {request['runtime']['image_uri']}")
    if request["prepared_snapshot"] is None:
        raise AcceptanceError("unresolved remote-update intent: resolve it against its succeeded preparation first")
    verified = verify_reference_identities(request, downloader.resolve)
    index = {f"{ref['uri']}#{ref['generation']}": str(downloader.paths[f"{ref['uri']}#{ref['generation']}"])
             for ref in verified}
    prepared_path = downloader.fetch(request["prepared_snapshot"]["manifest"])
    prepared = json.loads(prepared_path.read_text())
    if (prepared.get("prepare_id"), prepared.get("origin_month"), prepared.get("status")) != (
            request["prepared_snapshot"]["prepare_id"], request["origin_month"], "succeeded"):
        raise AcceptanceError("prepared manifest is not a succeeded snapshot for the requested prepare_id/origin")
    from cloud.batch.remote_sources import SYSTEM_FAMILIES

    require_supported_extraction_contract(prepared)
    for system, kinds in request["assets"].items():  # a bounded smoke preparation never serves a full roster
        for kind in ("roster", "geometry"):
            prepared_ref = prepared.get("systems", {}).get(system, {}).get(kind, {}).get("sha256")
            if prepared_ref != kinds[kind]["sha256"]:
                raise AcceptanceError(f"{system}: prepared snapshot {kind} {prepared_ref} is not the delivery {kind} "
                                      f"{kinds[kind]['sha256']}")
        for family in SYSTEM_FAMILIES[system]:
            if system not in prepared["families"].get(family, {}).get("outputs", {}):
                raise AcceptanceError(f"prepared snapshot lacks {family} outputs for {system}")
    for family in prepared["families"].values():
        for ref in family.get("outputs", {}).values():
            index[f"{ref['uri']}#{ref['generation']}"] = str(downloader.fetch(ref))
    check_environment(downloader.fetch(request["runtime"]["environment_manifest"]), request["runtime"])
    packages = {"fewsnet": {}, "ipcch": None}
    for model in request["models"]:
        system, horizon = model["system"], model["horizon_months"]
        check_acceptance(downloader.fetch(model["acceptance_report"]), model, request["runtime"])
        target = work / ("packages/fewsnet" if system == "fewsnet" else "packages/ipcch") / (
            f"{horizon}m" if system == "fewsnet" else "")
        materialize_package(downloader.fetch(model["package_manifest"]), downloader, target, system=system,
                            horizon=horizon, package_id=model["package_id"])
        if system == "fewsnet":
            packages["fewsnet"][horizon] = str(target)
        else:
            packages["ipcch"] = str(work / "packages/ipcch")
    for model in request["models"]:  # after ALL packages are materialized: later scopes cannot void a binding
        directory = (packages["fewsnet"][model["horizon_months"]] if model["system"] == "fewsnet" else packages["ipcch"])
        actual = package_schema_sha256(model["system"], model["horizon_months"], Path(directory))
        if actual != model["feature_schema_sha256"]:
            raise AcceptanceError(f"{model['system']}/{model['horizon_months']}m feature schema {actual} is not the "
                                  f"accepted {model['feature_schema_sha256']}")
    assets = {system: {kind: str(downloader.fetch(ref)) for kind, ref in kinds.items()}
              for system, kinds in request["assets"].items()}
    history = {system: assets[system]["history_panel"] for system in assets}
    for name in ("acled", "wfp"):  # keep = the exact family values of the consumed history panels
        if request[name]["action"] == "keep":
            expected = retained_family_sha256(history, name)
            if expected != request[name]["retained_snapshot"]["sha256"]:
                raise AcceptanceError(f"{name}: retained snapshot does not equal the {name} family of the consumed "
                                      f"history panels ({expected})")
    sources = {name: {"action": request[name]["action"],
                      "path": str(downloader.fetch(request[name]["retained_snapshot" if request[name]["action"] == "keep"
                                                             else "raw_upload"]))}
               for name in ("acled", "wfp")}
    return {"origin": request["origin_month"], "prepared_manifest": str(prepared_path), "reader_index": index,
            "packages": packages, "assets": assets, "sources": sources, "verified_refs": verified}


def retained_family_rows(history: Mapping[str, str], family: str, *, chunksize: int = 200_000):
    """CSV text blocks of the retained family projection of each history panel (deterministic, streamed):
    ``system, admin_code, month`` + the family columns as recorded, in source row order."""
    from tools.refresh_h5_inputs import CONFLICT_COLUMNS, WFP_COLUMNS

    columns = list(WFP_COLUMNS if family == "wfp" else CONFLICT_COLUMNS)
    header = True
    for system in ("fewsnet", "ipcch"):
        identity = ["FEWSNET_admin_code", "date"] if system == "fewsnet" else ["admin_code", "year", "month"]
        for chunk in pd_read_chunks(history[system], [*identity, *columns], chunksize):
            if system == "fewsnet":
                keys = {"admin_code": chunk["FEWSNET_admin_code"], "month": chunk["date"].str[:7]}
            else:
                keys = {"admin_code": chunk["admin_code"],
                        "month": chunk["year"].str.zfill(4) + "-" + chunk["month"].str.zfill(2)}
            block = chunk[columns].assign(**keys, system=system)[["system", "admin_code", "month", *columns]]
            yield block.to_csv(index=False, header=header, lineterminator="\n")
            header = False


def pd_read_chunks(path, usecols, chunksize):
    import pandas as pd

    return pd.read_csv(path, usecols=usecols, dtype=str, keep_default_na=False, chunksize=chunksize)


def retained_family_sha256(history: Mapping[str, str], family: str) -> str:
    digest = hashlib.sha256()
    for text in retained_family_rows(history, family):
        digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def _source_frames(spec: Mapping[str, Any]):
    """CP1 converters once, globally, for refreshed families; keep -> None (the pinned history)."""
    from tools.refresh_h5_inputs import conflict_aggregates, wfp_aggregates

    wfp = acled = None
    if spec["sources"]["wfp"]["action"] == "refresh":
        wfp, _ = wfp_aggregates(Path(spec["sources"]["wfp"]["path"]), cutoff=spec["origin"])
    if spec["sources"]["acled"]["action"] == "refresh":
        acled, _ = conflict_aggregates(Path(spec["sources"]["acled"]["path"]), cutoff=spec["origin"])
    return wfp, acled


def run_system(spec_path: Path, system: str, out: Path) -> None:
    """One system's ``deliver`` from verified local inputs only (run in its own process)."""
    from cloud.orchestrator.deliver import deliver, load_prepared_features, request_diagnostics

    spec = json.loads(Path(spec_path).read_text())
    request = json.loads(Path(spec["request_path"]).read_text())
    reader = LocalPinnedReader(spec["reader_index"])
    manifest = json.loads(Path(spec["prepared_manifest"]).read_text())
    wfp, acled = _source_frames(spec)
    assets = spec["assets"]
    deliver(origin=spec["origin"], out=out, prepared_families=manifest["families"],
            prepared_features=load_prepared_features(manifest, reader),
            ipcch_panel=Path(assets["ipcch"]["history_panel"]), ipcch_template=Path(assets["ipcch"]["fixed_features"]),
            ipcch_package_root=Path(spec["packages"]["ipcch"]), fewsnet_raw=Path(assets["fewsnet"]["history_panel"]),
            fewsnet_packages={int(h): Path(p) for h, p in spec["packages"]["fewsnet"].items()},
            census={s: Path(assets[s]["country_reference"]) for s in ("fewsnet", "ipcch")},
            geometry={s: Path(assets[s]["geometry"]) for s in ("fewsnet", "ipcch")}, wfp=wfp, acled=acled,
            system=system, diagnostics=request_diagnostics({**request, "validation_level": "structural"}, system, reader))


# Per-system members carried from an accepted same-origin delivery when that system is not scored
# now (its model package is installed from the request and checked for identity instead).
INHERITED_MEMBERS = {
    system: re.compile(rf"^(scopes/(0|6|12)m/{system}/[^/]+\.csv|{system}/(polygons\.geojson|"
                       rf"country_population_reference\.csv)|inputs/{inputs}|inputs/evidence/(frozen/)?{system}_[^/]+|"
                       rf"reports/{system}_[^/]+)$")
    for system, inputs in (("ipcch", r"ipcch_origin_rows\.csv"),
                           ("fewsnet", r"fewsnet_(scope_(0|6|12)m_inference|identity_population)\.csv"))
}
INHERITED_PACKAGE_PREFIX = {"ipcch": "ipcch/model_package/", "fewsnet": "fewsnet/model_package/"}


def inherit_system(out: Path, system: str, source: Mapping[str, Any], downloader: PinnedDownloader, *,
                   origin: str, package_dirs: Mapping[str, Path]) -> dict:
    """Copy one unscored system's members byte-for-byte from a pinned accepted delivery.

    The source must have the same origin and every horizon's targets; each member must match the
    source inventory hash; its model package must equal the package installed for this release.
    Nothing is recomputed: the inherited computation provenance stays the source's.
    """
    import tarfile

    import pandas as pd

    from cloud.orchestrator.delivery_bundle import SCOPE_TABLES, _directory_inventory
    from model_pipeline.run_operational_launch_inference import add_calendar_months

    manifest = json.loads(downloader.fetch(source["manifest"]).read_text())
    inventory = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    pattern, prefix = INHERITED_MEMBERS[system], INHERITED_PACKAGE_PREFIX[system]
    members, package, source_delivery = {}, {}, None
    with tarfile.open(downloader.fetch(source["archive"]), "r:gz") as archive:
        for info in archive.getmembers():
            name = info.name.removeprefix("./")
            wanted = pattern.match(name) or name.startswith(prefix) or name == "reports/delivery.json"
            if not info.isfile() or not wanted:
                continue
            data = archive.extractfile(info).read()
            digest = hashlib.sha256(data).hexdigest()
            if inventory.get(name) != digest:
                raise AcceptanceError(f"inherited {name} does not match the source inventory")
            if name == "reports/delivery.json":  # source identity only; this release writes its own
                source_delivery = json.loads(data)
                continue
            if name.startswith(prefix):
                package[name.removeprefix(prefix)] = digest
                continue
            destination = Path(out) / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                handle.write(data)
            members[name] = digest
    if source_delivery is None or source_delivery.get("origin_month") != origin:
        raise AcceptanceError(f"inherited {system} source is not an origin {origin} delivery")
    expected = {f"scopes/{h}m/{system}/{name}.csv" for h in (0, 6, 12) for name in SCOPE_TABLES[system]}
    if not expected <= set(members):
        raise AcceptanceError(f"inherited {system} lacks scope tables {sorted(expected - set(members))[:3]}")
    for horizon in (0, 6, 12):
        target = add_calendar_months(origin, horizon)
        table = Path(out) / f"scopes/{horizon}m/{system}/polygon_predictions.csv"
        frame = pd.read_csv(table, dtype=str, keep_default_na=False)
        months = ({"feature_period": origin, "target_period": target} if system == "ipcch"
                  else {"feature_month": origin, "target_month": target})
        if any(set(frame[column]) != {value} for column, value in months.items()):
            raise AcceptanceError(f"inherited {system} {horizon}m targets differ from {origin}->{target}")
    installed = {}
    for key, directory in package_dirs.items():
        relative = "" if system == "ipcch" else f"{key}m/"
        installed.update({relative + path: digest for path, digest in _directory_inventory(directory).items()})
    if package != installed:
        raise AcceptanceError(f"inherited {system} model package differs from the package installed for this release")
    return {"source_delivery_id": source["source_delivery_id"], "manifest": dict(source["manifest"]),
            "archive": dict(source["archive"]), "origin_month": origin, "members": members,
            "model_package": package, "source_run_id": source_delivery.get("run_id"),
            "source_provenance": manifest.get("provenance", {})}


def package_delivery(out: Path, spec: Mapping[str, Any], request: Mapping[str, Any], *, image_uri: str,
                     inherited: Mapping[str, Any] | None = None) -> dict:
    from cloud.orchestrator import delivery_bundle
    from cloud.orchestrator.deliver import finalize
    from cloud.orchestrator.delivery_manifest import selected_systems

    finalize(out)
    (out / "reports/delivery.json").write_text(json.dumps(
        {"origin_month": spec["origin"], "run_id": request["run_id"], "request": request["request"],
         "prepare_id": request["prepared_snapshot"]["prepare_id"],
         "execution": {"scored_systems": list(selected_systems(request)),
                       "inherited_systems": sorted(inherited or {}),
                       "remote_update": bool((request.get("execution") or {}).get("remote_update", True)),
                       "publication": (request.get("execution") or {}).get("publication", "current")}},
        indent=2, sort_keys=True) + "\n")
    if inherited:
        (out / "reports/inherited_members.json").write_text(
            json.dumps(dict(inherited), indent=2, sort_keys=True) + "\n")
    lock = REPO / "requirements.lock.txt"
    delivery_bundle.install_runtime_and_models(
        out, repo=REPO, fewsnet_packages={int(h): Path(p) for h, p in spec["packages"]["fewsnet"].items()},
        ipcch_package_root=Path(spec["packages"]["ipcch"]),
        lock_file=lock if lock.exists() else REPO / "deploy/october_delivery/requirements.lock.txt")
    delivery_bundle.write_bundle_docs(out, origin=spec["origin"], prepare_id=request["prepared_snapshot"]["prepare_id"])
    inventory = delivery_bundle.write_inventory(out, provenance={
        "request": request["request"], "run_id": request["run_id"], "image_uri": image_uri,
        "verified_refs": spec["verified_refs"]})
    archive = delivery_bundle.build_archive(out)  # refuses a failed validation or a changed inventory
    return {"validation": inventory["validation"]["status"], "archive": archive}


def _crc32c(path: Path) -> str:
    import base64

    import google_crc32c

    checksum = google_crc32c.Checksum()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            checksum.update(block)
    return base64.b64encode(checksum.digest()).decode()


def upload_tree(client, out: Path, output_root: str, run_id: str) -> dict[str, dict[str, str]]:
    """Create-only streamed upload of the delivery root; returns {relative: ref}."""
    bucket_name = output_root.removeprefix("gs://").split("/", 1)[0]
    bucket = client.bucket(bucket_name)
    refs = {}
    for path in sorted(p for p in Path(out).rglob("*") if p.is_file()):
        relative = path.relative_to(out).as_posix()
        blob = bucket.blob(f"deliveries/{run_id}/{relative}")
        try:  # create-only; long transient-error budget (observed: GCS 503 beyond the default 120 s)
            blob.upload_from_filename(path, if_generation_match=0, timeout=600, retry=UPLOAD_RETRY)
        except PreconditionFailed:  # a retried create whose first attempt landed
            existing = bucket.get_blob(blob.name)
            # transport check (size + CRC32C), not cryptographic identity; the recorded ref sha256 is the local file's
            if existing is None or existing.size != path.stat().st_size or existing.crc32c != _crc32c(path):
                raise
            blob = existing
        refs[relative] = {"uri": f"gs://{bucket_name}/{blob.name}", "generation": str(blob.generation),
                          "sha256": _stream_sha256(path)}
    return refs


def execute(*, request_ref: Mapping[str, str], request_bytes: bytes, output_root: str, release_namespace: str,
            image_uri: str, store, downloader: PinnedDownloader, work: Path,
            score: Callable[[Path, str, Path], None], package: Callable[..., dict],
            upload: Callable[[Path, str], dict]) -> dict:
    """The whole request lifecycle with injectable side effects (tests drive this directly)."""
    from cloud.orchestrator.delivery_manifest import validate_delivery_request
    from cloud.orchestrator.delivery_run import publish, run_once

    request = validate_delivery_request(json.loads(request_bytes), request_uri=request_ref["uri"],
                                        request_generation=request_ref["generation"],
                                        expected_release_namespace=release_namespace)

    from cloud.orchestrator.delivery_manifest import selected_systems

    execution = request.get("execution") or {}
    if execution and not execution["inference_systems"]:
        raise AcceptanceError("a prepare-only intent never runs delivery")

    def compute():
        spec = prepare_inputs(request, downloader, work, image_uri=image_uri)
        request_path = work / "request.json"
        request_path.write_bytes(request_bytes)
        spec_path = work / "spec.json"
        spec_path.write_text(json.dumps({**spec, "request_path": str(request_path)}, default=str))
        out = work / "delivery"
        selected = selected_systems(request)
        for system in ("ipcch", "fewsnet"):  # separate processes: bounded memory; only selected systems score
            if system in selected:
                score(spec_path, system, out)
        inherited = {}
        for system, source in (execution.get("inherit") or {}).items():
            packages = ({"": Path(spec["packages"]["ipcch"])} if system == "ipcch"
                        else {str(h): Path(p) for h, p in spec["packages"]["fewsnet"].items()})
            inherited[system] = inherit_system(out, system, source, downloader, origin=request["origin_month"],
                                               package_dirs=packages)
        packaged = (package(out, spec, request, image_uri=image_uri, inherited=inherited) if inherited
                    else package(out, spec, request, image_uri=image_uri))
        refs = upload(out, request["run_id"])
        record = {"run_id": request["run_id"], "request": dict(request_ref), "origin_month": request["origin_month"],
                  "manifest": refs["manifest.json"], "archive": refs["webapp_model_bundle.tar.gz"],
                  "validation": packaged["validation"],
                  **({"execution": {"scored_systems": list(selected), "inherited_systems": sorted(inherited)}}
                     if execution else {})}

        def validate():
            if packaged["validation"] != "passed":
                raise AcceptanceError("delivery validation did not pass; the release pointer is unchanged")

        outputs = f"{output_root.rstrip('/')}/deliveries/{request['run_id']}/"
        if execution.get("publication") == "candidate":
            # A checked candidate is promoted later (download/replay receipt + pointer CAS); never now.
            validate()
            candidate = store.write_text(f"{output_root.rstrip('/')}/candidates/{request['run_id']}/candidate.json",
                                         json.dumps(record, indent=2, sort_keys=True) + "\n", if_generation_match=0)
            return {"outputs": outputs, "release": None,
                    "candidate": {"uri": f"{output_root.rstrip('/')}/candidates/{request['run_id']}/candidate.json",
                                  "generation": str(candidate.generation)}}
        release = publish(store, output_root, run_id=request["run_id"], namespace=request["release"]["namespace"],
                          expected_pointer_generation=request["release"]["expected_pointer_generation"],
                          release_record=record, validate=validate)
        return {"outputs": outputs, "release": release}

    return run_once(store, output_root, run_id=request["run_id"], request_ref=request_ref, compute=compute)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Request-driven October delivery.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--request-uri", required=True)
    run.add_argument("--request-generation", required=True)
    run.add_argument("--output-root", required=True)
    run.add_argument("--release-namespace", required=True)
    run.add_argument("--image-uri", required=True)
    run.add_argument("--work-dir", default="/tmp/delivery-work")
    system = commands.add_parser("system")
    system.add_argument("--spec", required=True)
    system.add_argument("--system", choices=["fewsnet", "ipcch"], required=True)
    system.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.command == "system":
        run_system(Path(args.spec), args.system, Path(args.out))
        return 0

    from google.cloud import storage

    from cloud.common.object_store import GCSObjectStore
    from cloud.orchestrator.prepare import GcsPinnedReader

    client = storage.Client()
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=False)
    data = GcsPinnedReader(client).read_bytes(args.request_uri, args.request_generation)
    if data is None:
        raise AcceptanceError(f"request {args.request_uri}#{args.request_generation} not found")
    request_ref = {"uri": args.request_uri, "generation": args.request_generation,
                   "sha256": hashlib.sha256(data).hexdigest()}

    def score(spec_path, name, out):
        subprocess.run([sys.executable, "-m", "cloud.orchestrator.delivery_job", "system", "--spec", str(spec_path),
                        "--system", name, "--out", str(out)], check=True)

    status = execute(request_ref=request_ref, request_bytes=data, output_root=args.output_root,
                     release_namespace=args.release_namespace, image_uri=args.image_uri,
                     store=GCSObjectStore(client), downloader=PinnedDownloader(client, work / "inputs"), work=work,
                     score=score, package=package_delivery,
                     upload=lambda out, run_id: upload_tree(client, out, args.output_root, run_id))
    print(json.dumps(status, indent=2, sort_keys=True, default=str))
    return 0 if status["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
