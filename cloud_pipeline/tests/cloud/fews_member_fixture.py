"""A content-valid FEWS NET delivery member (origin 2026-04) cut from the existing valid-delivery fixture
(tests/cloud/test_delivery_bundle._valid_delivery): what ``deliver(system="fewsnet")`` writes, plus the exact local
packages it scored with. Used to drive the v2 FEWS member writer and the publication verifier."""

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

ORIGIN = "2026-04"


def build(tmp: Path) -> dict:
    """{"files": member dir with the deliver(fewsnet) outputs (no packages), "packages": {h: dir},
    "inventory": {"{h}m/<file>": sha256}}."""
    from cloud.ipcch.delivery_v2 import LEGACY_MEMBER
    from tests.cloud.test_delivery_bundle import _valid_delivery

    full = Path(tmp) / "valid-delivery"
    _valid_delivery(full)
    member = Path(tmp) / "fews-member-files"
    for path in sorted(full.rglob("*")):
        rel = path.relative_to(full).as_posix()
        if path.is_file() and LEGACY_MEMBER["fewsnet"].match(rel) and not rel.startswith("fewsnet/model_package/"):
            (member / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, member / rel)
    availability = pd.read_csv(full / "reports/diagnostic_availability.csv", dtype=str, keep_default_na=False)
    availability[availability["model_system"] == "fewsnet"].to_csv(
        member / "reports/fewsnet_diagnostic_availability.csv", index=False, lineterminator="\n")
    (member / "reports/fewsnet_feature_fill_audit.csv").write_text("system,polygon_id,fill_method\nfewsnet,0,observed\n")
    packages = {}
    for h in (0, 6, 12):                                  # the existing local package format (all seven files)
        packages[h] = Path(tmp) / f"fews-package-{h}m"
        packages[h].mkdir()
        for name, data in local_package_members(f"fews-{h}m").items():
            (packages[h] / name).write_bytes(data)
    inventory = {f"{h}m/{p.relative_to(d).as_posix()}": hashlib.sha256(p.read_bytes()).hexdigest()
                 for h, d in packages.items() for p in sorted(d.rglob("*")) if p.is_file()}
    return {"files": member, "packages": packages, "inventory": inventory}


def score_from(fixture: dict, calls: list | None = None):
    """A ``score(spec_path, system, out)`` that writes the fixture member's deliver(fewsnet) outputs."""
    def score(spec_path, system, out):
        assert system == "fewsnet"
        if calls is not None:
            calls.append(system)
        shutil.copytree(fixture["files"], out, dirs_exist_ok=True)
    return score


def package_members(fixture: dict) -> dict:
    """{h: {relative path: bytes}} of the fixture's exact local packages (to pin them as request package members)."""
    return {h: {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}
            for h, d in fixture["packages"].items()}


def manifest_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def local_package_members(seed: str, *, feature_schema_sha256: str = "a" * 64, checksums=None) -> dict:
    """{file: bytes} of a package in the EXISTING local package format (fewsnet_partitioned_rf_pipeline.local.package:
    LOCAL_PACKAGE_FILES, checksums.json over exactly the content files); ``checksums`` overrides that map."""
    from fewsnet_partitioned_rf_pipeline.local.package import LOCAL_PACKAGE_FILES
    members = {"model.joblib": f"model {seed}".encode() + bytes(range(256)),
               "feature_contract.json": json.dumps({"seed": seed}).encode(),
               "partition_map.csv": b"partition,admin_code\n1,0\n",
               "threshold_report.json": json.dumps({"seed": seed}).encode(),
               "training_report.json": json.dumps({"feature_schema_sha256": feature_schema_sha256}).encode(),
               "local_model_manifest.json": json.dumps({"files": list(LOCAL_PACKAGE_FILES), "seed": seed}).encode()}
    sums = {n: hashlib.sha256(d).hexdigest() for n, d in sorted(members.items())} if checksums is None else checksums
    members["checksums.json"] = json.dumps(sums).encode()
    return members
