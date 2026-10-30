"""v2 deliveries: new members, byte-for-byte inherited members, explicit shared-report merge, upload and the actual
publication verifier (task 10-29; R17, R18, R47, R63 and the Supervisor CP4 rulings).

A v2 delivery keeps the existing tree layout and file names (R47) and is stored create-only under
``{mode root}/deliveries/{run_id}/<path>`` with ``manifest.json`` (``fewsnet-ipcch-delivery-v2``): every file's sha256
and, per system, its member record (contract, own months/targets, mode, package identity, source run, member files).

* New IPCCH member: ``delivery_member.write_member`` output (system_provenance.json hash-covers every member file).
* Inherited member (the other system, exactly the member of the release bound to the expected pointer generation):
  every member file is copied byte-for-byte from the source delivery's stored tree and must equal the source
  inventory's sha256; a new-contract IPCCH member is then re-verified by ``verify_member`` against its own provenance
  (its own months - inherit-of-inherit keeps the original); a legacy member is checked against its OWN origin and its
  own targets (origin + 0/6/12), never the outer run's, and its model package is copied from the source (identity =
  the source's package files, not an unrelated installed package).
* Shared reports are rebuilt by explicit merge: ``reports/diagnostic_availability.csv`` and
  ``reports/feature_fill_audit.csv`` = each system's own sidecar rows plus that system's own ``execution_month`` and
  ``feature_month`` on every row (schemas may differ per system; the merged header is their explicit union).
* ``verify_delivery`` is the publication verifier: the stored files equal the manifest; the new IPCCH member verifies;
  inherited members equal their source files and identity; the release record's members equal the manifest's.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from cloud.common.object_store import ObjectStore
from cloud.ipcch import delivery_member as dm
from cloud.ipcch import publication as pub

DELIVERY_SCHEMA = "fewsnet-ipcch-delivery-v2"
LEGACY_MEMBER = {
    system: re.compile(rf"^(scopes/(0|6|12)m/{system}/[^/]+\.csv|{system}/(polygons\.geojson|"
                       rf"country_population_reference\.csv|model_package/.+)|inputs/{inputs}|"
                       rf"inputs/evidence/(frozen/)?{system}_[^/]+|reports/{system}_[^/]+)$")
    for system, inputs in (("ipcch", r"ipcch_origin_rows\.csv"),
                           ("fewsnet", r"fewsnet_(scope_(0|6|12)m_inference|identity_population)\.csv"))
}
SHARED = ("diagnostic_availability", "feature_fill_audit")


class DeliveryError(RuntimeError):
    """The delivery is incomplete or does not verify; it must not be published."""


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def delivery_base(root_uri: str, run_id: str) -> str:
    return f"{root_uri.rstrip('/')}/deliveries/{run_id}"


def member_paths(system: str, member: Mapping[str, Any], source_files: Mapping[str, str]) -> list[str]:
    """The source delivery files that make up one system's member."""
    if member.get("contract") == dm.CONTRACT:
        prov = member["provenance_files"]
        return sorted([*prov, "ipcch/system_provenance.json"])
    return sorted(p for p in source_files if LEGACY_MEMBER[system].match(p))


def _belongs(system: str, member: Mapping[str, Any], rel: str) -> bool:
    """Whether a delivery path is part of this system's member (the same rules ``member_paths`` selects with)."""
    if member.get("contract") == dm.CONTRACT:
        return dm.is_member_file(rel)
    return bool(LEGACY_MEMBER[system].match(rel))


def source_member(store: ObjectStore, system: str, member: Mapping[str, Any]) -> dict[str, str]:
    """{path: sha256} of the member's files in its PINNED source delivery inventory (exact member set)."""
    source_manifest = json.loads(_read_pinned(store, member["delivery"]["manifest"]))
    files = {e["path"]: e["sha256"] for e in source_manifest["files"]}
    paths = member_paths(system, member, files)
    missing = [p for p in paths if p not in files]
    if not paths or missing:
        raise DeliveryError(f"{system} member files {missing[:3] or '(none)'} are not in its source inventory")
    return {p: files[p] for p in paths}


def inherit(out: Path, store: ObjectStore, root_uri: str, system: str, member: Mapping[str, Any]) -> dict[str, Any]:
    """Copy one system's member byte-for-byte from its source delivery (sha256 against the source inventory) and
    check it under its own provenance; returns the member record for this delivery."""
    src = member["delivery"]
    source_manifest = json.loads(_read_pinned(store, src["manifest"]))
    files = {e["path"]: e["sha256"] for e in source_manifest["files"]}
    base = src["manifest"]["uri"].rsplit("/", 1)[0]
    paths = member_paths(system, member, files)
    if not paths:
        raise DeliveryError(f"inherited {system} member has no files in its source delivery")
    for rel in paths:
        if rel not in files:
            raise DeliveryError(f"inherited {system} file {rel} is not in the source inventory")
        data = store.read_bytes(f"{base}/{rel}")
        if _sha_bytes(data) != files[rel]:
            raise DeliveryError(f"inherited {system} file {rel} differs from the source inventory")
        dst = Path(out) / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "xb") as f:
            f.write(data)
    if member.get("contract") == dm.CONTRACT:
        dm.verify_member(out, expected={k: member.get(k) for k in ("execution_month", "feature_origin", "mode",
                                                                    "provenance_sha256")})
    else:
        _check_legacy_member(out, system, member)
    return {**{k: v for k, v in member.items() if k != "inherited_from_pointer_generation"}, "files": paths}


def _check_legacy_member(out: Path, system: str, member: Mapping[str, Any]) -> None:
    """A legacy member keeps its OWN origin and targets (origin + 0/6/12), whatever the outer run's months."""
    origin = member.get("origin_month")
    if not origin:
        raise DeliveryError(f"inherited legacy {system} member records no origin month")
    y, m = (int(x) for x in origin.split("-"))
    for lead in (0, 6, 12):
        o = y * 12 + m - 1 + lead
        target = f"{o // 12:04d}-{o % 12 + 1:02d}"
        p = Path(out) / f"scopes/{lead}m/{system}/polygon_predictions.csv"
        if not p.is_file():
            raise DeliveryError(f"inherited legacy {system} lacks {p.name} for lead {lead}")
        f = pd.read_csv(p, dtype=str, keep_default_na=False)
        cols = ("feature_period", "target_period") if system == "ipcch" else ("feature_month", "target_month")
        if set(f[cols[0]]) != {origin} or set(f[cols[1]]) != {target}:
            raise DeliveryError(f"inherited legacy {system} lead {lead} is not its own {origin}->{target}")


def _months(member: Mapping[str, Any]) -> tuple[str, str]:
    if member.get("contract") == dm.CONTRACT:
        return member["execution_month"], member["feature_origin"]
    return member.get("execution_month") or member.get("origin_month"), member.get("feature_origin") or member.get("origin_month")


def merge_shared_reports(out: Path, members: Mapping[str, Mapping[str, Any]]) -> None:
    """Shared reports rebuilt by explicit merge with each system's own execution/feature months on every row."""
    for name in SHARED:
        parts = []
        for system in sorted(members):
            p = Path(out) / f"reports/{system}_{name}.csv"
            if not p.is_file():
                raise DeliveryError(f"{system} member lacks reports/{system}_{name}.csv")
            f = pd.read_csv(p, dtype=str, keep_default_na=False)
            execution, feature = _months(members[system])
            parts.append(f.assign(member_system=system, member_execution_month=execution, member_feature_month=feature))
        cols = ["member_system", "member_execution_month", "member_feature_month"]
        for f in parts:
            cols += [c for c in f.columns if c not in cols]
        merged = pd.concat([f.reindex(columns=cols) for f in parts], ignore_index=True).fillna("")
        with open(Path(out) / f"reports/{name}.csv", "xb") as handle:
            handle.write(merged.to_csv(index=False, lineterminator="\n").encode())


def write_manifest(out: Path, *, run_id: str, members: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    files = sorted(str(p.relative_to(out)).replace(os.sep, "/") for p in Path(out).rglob("*") if p.is_file()
                   and p.name != "manifest.json")
    manifest = {"schema": DELIVERY_SCHEMA, "run_id": run_id, "members": dict(members),
                "files": [{"path": rel, "sha256": _sha_bytes((Path(out) / rel).read_bytes())} for rel in files]}
    with open(Path(out) / "manifest.json", "x") as f:
        f.write(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def upload(store: ObjectStore, root_uri: str, run_id: str, out: Path) -> dict[str, str]:
    """Create-only upload of every file, manifest last; returns the manifest ref."""
    base = delivery_base(root_uri, run_id)
    files = sorted(p for p in Path(out).rglob("*") if p.is_file() and p.name != "manifest.json")
    for p in [*files, Path(out) / "manifest.json"]:
        rel = str(p.relative_to(out)).replace(os.sep, "/")
        meta = store.write_bytes(f"{base}/{rel}", p.read_bytes(), if_generation_match=0)
    data = (Path(out) / "manifest.json").read_bytes()
    return {"uri": f"{base}/manifest.json", "generation": meta.generation, "sha256": _sha_bytes(data)}


def _read_pinned(store: ObjectStore, ref: Mapping[str, str]) -> bytes:
    meta = store.get_metadata(ref["uri"])
    if meta is None or str(meta.generation) != str(ref["generation"]):
        raise DeliveryError(f"{ref['uri']}#{ref['generation']} is not the stored object")
    data = store.read_bytes(ref["uri"])
    if _sha_bytes(data) != ref["sha256"]:
        raise DeliveryError(f"{ref['uri']} sha256 differs from its reference")
    return data


def verify_delivery(store: ObjectStore, *, delivery_ref: Mapping[str, str], snapshot: Mapping[str, Any],
                    record: Mapping[str, Any]) -> dict[str, Any]:
    """The publication verifier (``publication.publish(verify_delivery=...)``): see module docstring."""
    manifest = json.loads(_read_pinned(store, delivery_ref))
    if manifest.get("schema") != DELIVERY_SCHEMA or manifest.get("run_id") != record["run_id"]:
        raise DeliveryError("delivery manifest schema/run does not match the release")
    base = delivery_ref["uri"].rsplit("/", 1)[0]
    with tempfile.TemporaryDirectory(prefix="v2-verify-") as tmp:
        for entry in manifest["files"]:
            data = store.read_bytes(f"{base}/{entry['path']}")
            if _sha_bytes(data) != entry["sha256"]:
                raise DeliveryError(f"stored {entry['path']} differs from the delivery manifest")
            dst = Path(tmp) / entry["path"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
        current = pub.members(snapshot["record"])
        for system, member in record["systems"].items():
            listed = manifest["members"].get(system)
            if listed is None:
                raise DeliveryError(f"release member {system} is not in the delivery manifest")
            if member.get("published_by_run") == record["run_id"]:            # new in this release
                if member.get("contract") == dm.CONTRACT:
                    dm.verify_member(Path(tmp), expected=member)
                    if sorted(h["model_horizon_months"] for h in member.get("horizons", [])) != [2, 8, 14]:
                        raise DeliveryError("new IPCCH member does not carry H2/H8/H14 (R18)")
                else:                                                         # new legacy-format member (FEWS NET)
                    own = {p for p in (e["path"] for e in manifest["files"]) if _belongs(system, member, p)}
                    if not own:
                        raise DeliveryError(f"new {system} member has no files")
                    _check_legacy_member(Path(tmp), system, member)
            else:                                                             # inherited: bound snapshot's member
                src = current.get(system)
                strip = lambda m: {k: v for k, v in (m or {}).items() if k != "inherited_from_pointer_generation"}
                if src is None or strip(src) != strip(member):
                    raise DeliveryError(f"inherited {system} member is not the bound current release's member")
                if listed.get("delivery") != src.get("delivery") or listed.get("provenance_sha256") != src.get("provenance_sha256"):
                    raise DeliveryError(f"inherited {system} delivery identity differs from the current member")
                # independent of this delivery's own inventory: the member's exact file set and bytes must be those of
                # the pinned source inventory of the snapshot-bound member (edited, missing or extra files refuse)
                expected_files = source_member(store, system, src)
                new_files = {e["path"]: e["sha256"] for e in manifest["files"]}
                here = {p for p in new_files if _belongs(system, src, p)}
                if here != set(expected_files):
                    raise DeliveryError(f"inherited {system} member files differ from its source inventory: missing "
                                        f"{sorted(set(expected_files) - here)[:3]}, extra {sorted(here - set(expected_files))[:3]}")
                changed = sorted(p for p, sha in expected_files.items() if new_files[p] != sha)
                if changed:
                    raise DeliveryError(f"inherited {system} files differ from the source inventory: {changed[:3]}")
                if src.get("contract") == dm.CONTRACT:
                    dm.verify_member(Path(tmp), expected=src)
                else:
                    _check_legacy_member(Path(tmp), system, src)
    return manifest
