"""Versioned combination envelope: the immutable binding of one model combination package to one handoff-input bundle
(task 10-29; design.md "Model combination package", R32, R45, R48, R51, R55).

The research-side candidate package (``package_manifest.json``) and handoff bundle (``handoff_manifest.json``) stay
byte-unchanged. An envelope is a separate, explicitly versioned JSON file (``ipcch-combination-envelope-v1``) that binds

* the package: ``package_manifest.json`` sha256, combination id, contract version, the per-scope horizon/lead/cutoff and
  feature-contract sha256, and the sha256 of the shared 527-name feature order;
* the handoff bundle: ``handoff_manifest.json`` sha256, its schema, roster size and roster sha256, and — only once the
  envelope is accepted — the sha256 of the FINALIZED ``acceptance_entries.json`` (every entry with acceptor and date).
  A candidate envelope records the draft entries digest as information only; acceptance changes those bytes, so an
  accepted envelope must bind the finalized file, never a stale draft digest;
* ``status`` candidate|accepted with acceptor and date (acceptance is a research-side act; nothing here writes it).

Verification is split by mode (R48):

* ``verify_combination`` reads only the envelope and the package (model + diagnostic evidence). Smoke may use a candidate
  envelope; real requires ``accepted`` with acceptor, date and a bound finalized-entries digest.
* ``verify_handoff`` (real only) resolves the real handoff bundle and requires its manifest, roster and finalized
  acceptance entries to match the envelope exactly; any other bundle is refused even when its 527-column schema matches.
* ``verify_fixture_bundle`` (smoke only) admits a bundle only inside the smoke binding's declared fixture root, decided
  lexically before any filesystem access (components lstat-checked inside the root, symlinks refused), reads the
  fixture marker before any payload, then the declared roster subset; smoke never resolves or reads the real handoff
  assets, even when one is passed by mistake.

A store initialised for a combination records the pairing (``combination_binding`` table); later reads require the
same pairing, so a store initialised from another bundle or for another package is refused.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

import pandas as pd

from cloud.common.object_store import ObjectStore
from cloud.ipcch.stores import StoreError, StoreRoot, VersionedTable

ENVELOPE_SCHEMA = "ipcch-combination-envelope-v1"
HANDOFF_SCHEMA = "ipcch-handoff-inputs-v1"
STATUSES = ("candidate", "accepted")
PACKAGE_MANIFEST = "package_manifest.json"
HANDOFF_MANIFEST = "handoff_manifest.json"
ACCEPTANCE_ENTRIES = "acceptance_entries.json"
ROSTER_FILE = "fixed/roster.csv"
BINDING_TABLE = "combination_binding"
SCOPES = {"0": (2, 0), "6": (8, 6), "12": (14, 12)}          # scope -> (model horizon, public lead)
PAIRING_COLUMNS = ("mode", "combination_id", "package_manifest_sha256", "feature_order_sha256",
                   "bundle_manifest_sha256", "roster_sha256", "roster_size")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class BindingError(RuntimeError):
    """The combination envelope, package or bundle do not match; nothing was used."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def feature_order_sha256(columns) -> str:
    """sha256 of the feature names as a compact JSON list (order-sensitive)."""
    return sha256_bytes(json.dumps([str(c) for c in columns], separators=(",", ":")).encode("utf-8"))


def _json(path: str) -> tuple[Any, str]:
    with open(path, "rb") as f:
        data = f.read()
    try:
        return json.loads(data), sha256_bytes(data)
    except ValueError as exc:
        raise BindingError(f"{path}: invalid JSON ({exc})") from exc


# --------------------------------------------------------------------------- package (model + evidence)


def package_identity(package_root: str) -> dict[str, Any]:
    """Identity of a package after re-hashing every listed file (no missing, altered, escaping or unlisted file)."""
    root = os.path.realpath(package_root)
    manifest, manifest_sha = _json(os.path.join(root, PACKAGE_MANIFEST))
    if manifest.get("kind") != "ipcch_model_combination" or not isinstance(manifest.get("files"), dict):
        raise BindingError(f"{PACKAGE_MANIFEST}: not an ipcch_model_combination manifest with a files map")
    listed = {rel: (e if isinstance(e, str) else e.get("sha256") if isinstance(e, dict) else None)
              for rel, e in manifest["files"].items()}            # rel -> sha256 (plain string or {"sha256": ...})
    for rel, sha in listed.items():
        path = os.path.realpath(os.path.join(root, rel))
        if not path.startswith(root + os.sep) or not os.path.isfile(path):
            raise BindingError(f"package file {rel} is missing or outside the package root")
        if sha is None or sha256_file(path) != sha:
            raise BindingError(f"package file {rel} differs from {PACKAGE_MANIFEST}")
    present = {os.path.relpath(os.path.join(d, n), root).replace(os.sep, "/")
               for d, _, names in os.walk(root) for n in names}
    unlisted = sorted(present - set(listed) - {PACKAGE_MANIFEST})
    if unlisted:
        raise BindingError(f"package holds unlisted files {unlisted[:5]}")
    scopes, orders = {}, {}
    if sorted(manifest.get("scopes", {})) != sorted(SCOPES):
        raise BindingError(f"package scopes {sorted(manifest.get('scopes', {}))} != {sorted(SCOPES)}")
    for scope, (horizon, lead) in SCOPES.items():
        spec = manifest["scopes"][scope]
        if (spec.get("model_horizon_months"), spec.get("public_lead_months")) != (horizon, lead):
            raise BindingError(f"scope {scope}: horizon/lead {spec.get('model_horizon_months')}/{spec.get('public_lead_months')}")
        contract_rel = f"scope_{scope}m/feature_contract.csv"
        if spec.get("feature_schema_sha256") != listed.get(contract_rel):
            raise BindingError(f"scope {scope}: feature_schema_sha256 is not the listed {contract_rel}")
        cols, _ = _json(os.path.join(root, f"scope_{scope}m/feature_columns.json"))
        cols = cols.get("feature_columns") if isinstance(cols, dict) else cols
        if not isinstance(cols, list) or len(cols) != len(set(cols)):
            raise BindingError(f"scope {scope}: feature_columns.json must list unique names")
        orders[scope] = tuple(str(c) for c in cols)
        scopes[scope] = {"model_horizon_months": horizon, "public_lead_months": lead,
                         "training_cutoff": spec.get("training_cutoff"),
                         "feature_schema_sha256": spec["feature_schema_sha256"]}
    if len(set(orders.values())) != 1:
        raise BindingError("the three scopes do not share one feature order")
    order = orders["0"]
    return {"package_manifest_sha256": manifest_sha, "combination_id": manifest.get("combination_id"),
            "contract_version": manifest.get("contract_version"), "package_status": manifest.get("status"),
            "scopes": scopes, "feature_order_sha256": feature_order_sha256(order), "feature_count": len(order),
            "_order": order}


# --------------------------------------------------------------------------- handoff bundle


def _roster(bundle_dir: str, manifest: Mapping[str, Any]) -> tuple[str, int]:
    entry = manifest.get("files", {}).get(ROSTER_FILE)
    if entry is None:
        raise BindingError(f"bundle lists no {ROSTER_FILE}")
    path = os.path.join(bundle_dir, ROSTER_FILE)
    sha = sha256_file(path)
    if sha != entry.get("sha256") or (manifest.get("roster_sha256") not in (None, sha)):
        raise BindingError(f"{ROSTER_FILE} bytes differ from the bundle manifest")
    codes = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(codes.columns) != ["admin_code"] or not codes["admin_code"].str.fullmatch(r"\d+").all() \
            or codes["admin_code"].duplicated().any():
        raise BindingError(f"{ROSTER_FILE} must be unique integral admin_code values")
    if len(codes) != manifest.get("roster_size"):
        raise BindingError(f"{ROSTER_FILE} has {len(codes)} rows, manifest roster_size {manifest.get('roster_size')}")
    return sha, len(codes)


def finalized_entries(bundle_dir: str, manifest: Mapping[str, Any]) -> tuple[str, dict[str, dict[str, Any]]]:
    """(sha256, entries by name) of a FINALIZED acceptance_entries.json: one complete delivered entry (acceptor, date)
    for exactly every runtime file of the manifest, at that file's manifest sha256."""
    entries, sha = _json(os.path.join(bundle_dir, ACCEPTANCE_ENTRIES))
    if not isinstance(entries, list):
        raise BindingError(f"{ACCEPTANCE_ENTRIES} must be a list")
    by_name = {}
    for e in entries:
        name = e.get("name")
        if name in by_name:
            raise BindingError(f"{ACCEPTANCE_ENTRIES}: duplicate entry {name}")
        if not (isinstance(e.get("acceptor"), str) and e["acceptor"].strip()) or \
                not (isinstance(e.get("accepted_at"), str) and _DATE.fullmatch(e["accepted_at"])):
            raise BindingError(f"{ACCEPTANCE_ENTRIES}: {name} is not finalized (acceptor/accepted_at); drafts cannot be bound")
        if e.get("kind") != "delivered" or not (isinstance(e.get("source"), str) and e["source"].strip()):
            raise BindingError(f"{ACCEPTANCE_ENTRIES}: {name} needs kind=delivered and a source")
        by_name[name] = e
    runtime = {rel: v["sha256"] for rel, v in manifest["files"].items() if not rel.startswith("audit/")}
    if set(by_name) != set(runtime):
        raise BindingError(f"{ACCEPTANCE_ENTRIES} names differ from the runtime files: "
                           f"missing {sorted(set(runtime) - set(by_name))[:3]}, extra {sorted(set(by_name) - set(runtime))[:3]}")
    wrong = sorted(n for n, e in by_name.items() if e.get("sha256") != runtime[n])
    if wrong:
        raise BindingError(f"{ACCEPTANCE_ENTRIES}: sha256 differs from the manifest for {wrong[:3]}")
    return sha, by_name


def handoff_identity(bundle_dir: str, *, finalized: bool) -> dict[str, Any]:
    manifest, manifest_sha = _json(os.path.join(bundle_dir, HANDOFF_MANIFEST))
    if manifest.get("schema") != HANDOFF_SCHEMA:
        raise BindingError(f"{HANDOFF_MANIFEST}: schema {manifest.get('schema')!r} != {HANDOFF_SCHEMA}")
    roster_sha, size = _roster(bundle_dir, manifest)
    ident = {"manifest_sha256": manifest_sha, "schema": HANDOFF_SCHEMA, "fixture": bool(manifest.get("fixture")),
             "roster_size": size, "roster_sha256": roster_sha, "acceptance_entries_sha256": None,
             "draft_acceptance_entries_sha256": None}
    if finalized:
        if ident["fixture"]:
            raise BindingError("real mode refuses a fixture (smoke) bundle")
        ident["acceptance_entries_sha256"], ident["_entries"] = finalized_entries(bundle_dir, manifest)
    elif os.path.exists(os.path.join(bundle_dir, ACCEPTANCE_ENTRIES)):
        ident["draft_acceptance_entries_sha256"] = sha256_file(os.path.join(bundle_dir, ACCEPTANCE_ENTRIES))
    ident["_manifest"] = manifest
    return ident


# --------------------------------------------------------------------------- envelope


def build_envelope(package_root: str, bundle_dir: str, *, envelope_version: int, created_at: str,
                   acceptor: str | None = None, accepted_at: str | None = None) -> dict[str, Any]:
    """A candidate envelope (no acceptor) or an accepted one (acceptor + date, finalized entries required)."""
    accepted = acceptor is not None or accepted_at is not None
    if accepted and not (isinstance(acceptor, str) and acceptor.strip() and isinstance(accepted_at, str)
                         and _DATE.fullmatch(accepted_at)):
        raise BindingError("an accepted envelope needs a non-empty acceptor and accepted_at YYYY-MM-DD")
    if not isinstance(envelope_version, int) or envelope_version < 1:
        raise BindingError("envelope_version must be a positive integer")
    pkg = package_identity(package_root)
    ho = handoff_identity(bundle_dir, finalized=accepted)
    if ho["fixture"]:
        raise BindingError("a fixture (smoke) bundle cannot be bound into a combination envelope")
    return {
        "schema": ENVELOPE_SCHEMA, "envelope_version": envelope_version,
        "envelope_id": f"{pkg['combination_id']}/envelope-v{envelope_version}",
        "status": "accepted" if accepted else "candidate", "acceptor": acceptor, "accepted_at": accepted_at,
        "created_at": created_at,
        "package": {k: pkg[k] for k in ("package_manifest_sha256", "combination_id", "contract_version", "scopes",
                                        "feature_order_sha256", "feature_count")},
        "handoff": {k: ho[k] for k in ("manifest_sha256", "schema", "roster_size", "roster_sha256",
                                       "acceptance_entries_sha256", "draft_acceptance_entries_sha256")},
    }


def envelope_bytes(envelope: Mapping[str, Any]) -> bytes:
    return (json.dumps(envelope, indent=1, sort_keys=True) + "\n").encode("utf-8")


def write_envelope(envelope: Mapping[str, Any], path: str) -> str:
    """Create-only write (an envelope version is never overwritten); returns its sha256."""
    data = envelope_bytes(envelope)
    with open(path, "xb") as f:
        f.write(data)
    return sha256_bytes(data)


@dataclass(frozen=True)
class Binding:
    mode: str
    envelope_sha256: str
    envelope_id: str
    status: str
    acceptor: str | None
    accepted_at: str | None
    combination_id: str
    package_manifest_sha256: str
    feature_order: tuple[str, ...]
    feature_order_sha256: str
    scopes: Mapping[str, Any]
    handoff: Mapping[str, Any] | None = field(default=None)   # real only (digests of the bound real bundle)
    fixture_root: str | None = None                           # smoke only: the declared trusted fixture namespace

    def reference(self) -> dict[str, Any]:
        """The combination reference recorded in batches, summaries and store records."""
        return {"envelope_id": self.envelope_id, "envelope_sha256": self.envelope_sha256, "status": self.status,
                "combination_id": self.combination_id, "package_manifest_sha256": self.package_manifest_sha256,
                "feature_order_sha256": self.feature_order_sha256,
                "handoff_manifest_sha256": None if self.handoff is None else self.handoff["manifest_sha256"]}


def verify_combination(envelope_path: str, package_root: str, *, mode: str,
                       expected_envelope_sha256: str | None = None, fixture_root: str | None = None) -> Binding:
    """Envelope + package only (no handoff asset is read in either mode). Real requires an accepted envelope; smoke
    requires the declared fixture root (its only admissible bundle namespace, R48)."""
    if mode not in ("smoke", "real"):
        raise BindingError(f"mode must be smoke or real, got {mode!r}")
    if (mode == "smoke") != (fixture_root is not None):
        raise BindingError("smoke requires a declared fixture_root; real takes none")
    env, env_sha = _json(envelope_path)
    if expected_envelope_sha256 is not None and env_sha != expected_envelope_sha256:
        raise BindingError(f"envelope sha256 {env_sha} != referenced {expected_envelope_sha256}")
    if env.get("schema") != ENVELOPE_SCHEMA or env.get("status") not in STATUSES:
        raise BindingError(f"envelope schema/status {env.get('schema')!r}/{env.get('status')!r} not recognised")
    if env["status"] == "accepted":
        if not (isinstance(env.get("acceptor"), str) and env["acceptor"].strip()
                and isinstance(env.get("accepted_at"), str) and _DATE.fullmatch(env["accepted_at"])):
            raise BindingError("accepted envelope lacks acceptor/accepted_at")
        if not env.get("handoff", {}).get("acceptance_entries_sha256"):
            raise BindingError("accepted envelope does not bind finalized acceptance entries")
    elif mode == "real":
        raise BindingError(f"real mode requires an accepted combination envelope; {env.get('envelope_id')} is "
                           f"{env['status']} (R51)")
    pkg = package_identity(package_root)
    for key in ("package_manifest_sha256", "combination_id", "contract_version", "scopes", "feature_order_sha256",
                "feature_count"):
        if env.get("package", {}).get(key) != pkg[key]:
            raise BindingError(f"package {key} {pkg[key]!r} differs from the envelope "
                               f"{env.get('package', {}).get(key)!r}; this package is not the bound combination")
    return Binding(mode=mode, envelope_sha256=env_sha, envelope_id=env["envelope_id"], status=env["status"],
                   acceptor=env.get("acceptor"), accepted_at=env.get("accepted_at"),
                   combination_id=pkg["combination_id"], package_manifest_sha256=pkg["package_manifest_sha256"],
                   feature_order=pkg["_order"], feature_order_sha256=pkg["feature_order_sha256"], scopes=pkg["scopes"],
                   handoff=dict(env["handoff"]) if mode == "real" else None,
                   fixture_root=None if fixture_root is None else _lexical(fixture_root))


def verify_handoff(binding: Binding, bundle_dir: str) -> dict[str, Any]:
    """REAL only: the bundle must be exactly the envelope's handoff bundle with its finalized acceptance entries."""
    if binding.mode != "real" or binding.handoff is None:
        raise BindingError("smoke never resolves the real handoff bundle; use verify_fixture_bundle (R48)")
    ident = handoff_identity(bundle_dir, finalized=True)
    if ident["fixture"]:
        raise BindingError("real mode refuses a fixture (smoke) bundle")
    for key in ("manifest_sha256", "roster_size", "roster_sha256", "acceptance_entries_sha256"):
        if ident[key] != binding.handoff.get(key):
            raise BindingError(f"handoff {key} {ident[key]!r} != envelope {binding.handoff.get(key)!r}; "
                               f"this bundle is not bound to {binding.envelope_id}")
    return ident


def _lexical(path: str) -> str:
    """Absolute normalised path computed WITHOUT touching the filesystem."""
    return os.path.normpath(os.path.abspath(os.fspath(path)))


def _inside(root: str, path: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def admit_fixture_dir(binding: Binding, bundle_dir: str) -> str:
    """SMOKE admission, decided lexically before ANY filesystem access: the bundle must lie inside the binding's
    declared fixture root; anything else (e.g. a misrouted real handoff bundle) is refused unread (R48)."""
    if binding.mode != "smoke" or binding.fixture_root is None:
        raise BindingError("fixture bundles are admitted only for a smoke binding with a declared fixture_root")
    path = _lexical(bundle_dir)
    if not _inside(binding.fixture_root, path):
        raise BindingError(f"smoke bundle {path} is outside the declared fixture root {binding.fixture_root}; "
                           "refused before any read (R48)")
    return path


def fixture_file(binding: Binding, bundle_dir: str, rel: str) -> str:
    """Path of one fixture-bundle file after admission; the fixture root itself and then every component below it are
    lstat-checked (only the root and paths inside it are touched) and symlinks are refused, so no read can leave the
    fixture root."""
    import stat
    bundle = admit_fixture_dir(binding, bundle_dir)
    path = _lexical(os.path.join(bundle, rel))
    if not _inside(bundle, path) or path == bundle:
        raise BindingError(f"{rel} escapes the fixture bundle")
    current = binding.fixture_root
    try:                                                   # the root itself first: a symlinked root leaves the namespace
        root_mode = os.lstat(current).st_mode
    except FileNotFoundError as exc:
        raise BindingError(f"fixture root {current} is missing") from exc
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        raise BindingError(f"fixture root {current} is a symlink or not a directory; refused (R48)")
    for part in os.path.relpath(path, current).split(os.sep):
        current = os.path.join(current, part)
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError as exc:
            raise BindingError(f"fixture file {rel} is missing") from exc
        if stat.S_ISLNK(mode):
            raise BindingError(f"fixture path {current} is a symlink; refused (R48)")
    return path


def verify_fixture_bundle(binding: Binding, bundle_dir: str) -> dict[str, Any]:
    """SMOKE only: admission inside the fixture root (no filesystem access before it), then the manifest's fixture
    marker BEFORE any payload is read, then the declared roster subset. Nothing of the real bundle is touched."""
    bundle = admit_fixture_dir(binding, bundle_dir)
    manifest, manifest_sha = _json(fixture_file(binding, bundle, HANDOFF_MANIFEST))
    if not manifest.get("fixture"):
        raise BindingError("smoke initialisation requires a fixture bundle (manifest fixture: true), never the real "
                           "handoff bundle (R48)")
    if manifest.get("schema") != HANDOFF_SCHEMA:
        raise BindingError(f"{HANDOFF_MANIFEST}: schema {manifest.get('schema')!r} != {HANDOFF_SCHEMA}")
    fixture_file(binding, bundle, ROSTER_FILE)
    roster_sha, size = _roster(bundle, manifest)
    return {"manifest_sha256": manifest_sha, "schema": HANDOFF_SCHEMA, "fixture": True, "roster_size": size,
            "roster_sha256": roster_sha, "acceptance_entries_sha256": None, "draft_acceptance_entries_sha256": None,
            "_manifest": manifest}


# --------------------------------------------------------------------------- store pairing


def pairing(binding: Binding, bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {"mode": binding.mode, "combination_id": binding.combination_id,
            "package_manifest_sha256": binding.package_manifest_sha256,
            "feature_order_sha256": binding.feature_order_sha256, "bundle_manifest_sha256": bundle["manifest_sha256"],
            "roster_sha256": bundle["roster_sha256"], "roster_size": int(bundle["roster_size"])}


def store_pairing(store: ObjectStore, root: StoreRoot) -> tuple[dict[str, Any] | None, str]:
    frame, _, generation = VersionedTable(store, root, BINDING_TABLE).read({c: str for c in PAIRING_COLUMNS})
    if frame is None:
        return None, generation
    if list(frame.columns) != list(PAIRING_COLUMNS) or len(frame) != 1:
        raise StoreError(f"{BINDING_TABLE} must be one row of {PAIRING_COLUMNS}")
    row = frame.iloc[0].to_dict()
    row["roster_size"] = int(row["roster_size"])
    return row, generation


def check_store_pairing(store: ObjectStore, root: StoreRoot, wanted: Mapping[str, Any]) -> tuple[bool, str]:
    """(already bound, generation); a store bound to another pairing is refused."""
    have, generation = store_pairing(store, root)
    if have is None:
        return False, generation
    if have != dict(wanted):
        diff = {k: (have.get(k), wanted.get(k)) for k in PAIRING_COLUMNS if have.get(k) != wanted.get(k)}
        raise StoreError(f"store {root.uri} is bound to another combination/bundle {diff}; refusing to mix (R32/R55)")
    return True, generation


def commit_store_pairing(store: ObjectStore, root: StoreRoot, wanted: Mapping[str, Any], generation: str,
                         binding: Binding) -> None:
    VersionedTable(store, root, BINDING_TABLE).commit(
        pd.DataFrame([wanted], columns=list(PAIRING_COLUMNS)),
        {"action": "bind", "envelope": binding.reference()}, expected_generation=generation)


def require_store_pairing(store: ObjectStore, root: StoreRoot, binding: Binding) -> dict[str, Any]:
    """The store must have been initialised for this binding's combination (and, in real, its handoff bundle)."""
    if binding.mode != root.mode:
        raise StoreError(f"{binding.mode} binding cannot read the {root.mode} store (R48)")
    have, _ = store_pairing(store, root)
    if have is None:
        raise StoreError(f"store {root.uri} is not initialised for any combination (R45)")
    expect = {"mode": binding.mode, "combination_id": binding.combination_id,
              "package_manifest_sha256": binding.package_manifest_sha256,
              "feature_order_sha256": binding.feature_order_sha256}
    if binding.handoff is not None:
        expect.update(bundle_manifest_sha256=binding.handoff["manifest_sha256"],
                      roster_sha256=binding.handoff["roster_sha256"], roster_size=int(binding.handoff["roster_size"]))
    diff = {k: (have.get(k), v) for k, v in expect.items() if have.get(k) != v}
    if diff:
        raise StoreError(f"store {root.uri} is bound to another combination/bundle {diff}; refusing to mix (R32/R55)")
    return have
