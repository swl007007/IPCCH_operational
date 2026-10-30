"""Initialise the IPCCH retained stores from the accepted handoff bundle and read assembly inputs back (task 10-29; R32,
R45, R54, R55, R59, R62, R64).

The bundle (research_cloud/packages/ipcch_handoff_inputs.py) lists every file with its sha256 in
``handoff_manifest.json``. ``initialise`` first verifies the combination binding (``binding.py``: real -> exactly the
accepted envelope's handoff bundle and finalized acceptance entries; smoke -> its own fixture bundle, never the real
one), then each runtime file's bytes against that manifest AND an acceptance record (R45: a file without a record, or
with a different checksum, is refused before anything is written), then commits
it once into the mode's store as a versioned table named after its path. Re-initialising with the same content is a
no-op; different content for an initialised table is refused (accepted history is never silently replaced; refreshes go
through their own handlers). ``audit/`` files are review evidence and are not loaded.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import numpy as np
import pandas as pd

from cloud.common.object_store import ObjectStore
from cloud.ipcch import binding as bd
from cloud.ipcch.assembly import INTERIM_FAMILIES, AssemblyInputs
from cloud.ipcch.stores import AcceptanceManifest, StoreError, StoreRoot, VersionedTable
from cloud.ipcch.vendor import ipcch_compact as cp

SCHEMA = "ipcch-handoff-inputs-v1"
ROSTER_SIZE = 6226          # the accepted real roster (bound through the combination envelope)


def table_name(rel: str) -> str:
    """bundle path -> store table name (history/climate_month_sm_z.csv -> history__climate_month_sm_z)."""
    if not rel.endswith(".csv") or rel.startswith("audit/"):
        raise StoreError(f"{rel} is not a runtime bundle table")
    return rel[:-4].replace("/", "__")


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _schema(rel: str) -> tuple[tuple[str, ...] | None, tuple[str, ...], tuple[str, ...]]:
    """(exact columns or None = leading admin_code only, key columns, numeric columns) of a bundle table."""
    from cloud.ipcch import climate as cl
    from cloud.ipcch import retained
    name = rel.rsplit("/", 1)[-1][:-4]
    if rel == "fixed/roster.csv":
        return ("admin_code",), ("admin_code",), ()
    if rel.startswith("history/climate_month_"):
        return cl.MONTH_COLUMNS, ("admin_code", "month"), ("value", "n_sources", "ens_sd")
    if rel.startswith("history/climate_gs_"):
        return cl.GS_COLUMNS, cl.GS_KEY, ("value", "n_sources", "ens_sd")
    if rel.startswith("history/") and name in INTERIM_FAMILIES:
        return retained.SERIES_COLUMNS, ("admin_code", "month"), ("value",)
    if rel == "history/idp_local.csv":
        return ("admin_code", "month", "value"), ("admin_code", "month"), ("value",)
    if rel == "history/idp_national.csv":
        return ("iso3", "report_month", "stock"), ("iso3", "report_month"), ("stock",)
    if rel == "history/history_snapshot.csv":
        return retained.SNAPSHOT_COLUMNS, ("area_id", "report_month"), ()
    if rel == "fixed/area_identity.csv":
        return ("admin_code", "iso3", "iso2", "lat", "lon", "iso3_reference"), ("admin_code",), ("lat", "lon")
    if rel == "fixed/season_windows.csv":
        return ("admin_code", "season_year", "season", "gs_start_date", "gs_end_date_exclusive"), ("admin_code", "season_year", "season"), ()
    if rel == "fixed/population_reference.csv":
        return ("admin_code", "reference_period", "population_estimate"), ("admin_code", "reference_period"), ("population_estimate",)
    if rel in ("fixed/static29.csv", "fixed/ae_descriptors.csv", "fixed/season_calendar.csv"):
        return None, ("admin_code",), ("*",)
    if rel.startswith("fixed/acled/"):
        return None, (), ()
    raise StoreError(f"{rel}: no known schema; refusing to load an unknown bundle table")


FIELD_KINDS = {"admin_code": "integral", "area_id": "integral", "season_year": "integral", "n_sources": "integral",
               "month": "month", "report_month": "month", "availability_month": "month", "preparation_cutoff": "month",
               "reference_period": "month", "gs_start_date": "date", "gs_end_date_exclusive": "date", "season": "season",
               "iso2": "iso2", "iso3_reference": "iso3", "phase": "integral"}


def _check_fields(frame: pd.DataFrame, rel: str) -> None:
    """Shared strict validators for every identifier/month/date/key field of a runtime table (no write before this)."""
    from cloud.ipcch import climate as cl
    iso3_blank_ok = rel == "fixed/area_identity.csv"         # training-lineage iso3 is blank for 31 CI areas
    for col in frame.columns:
        kind = FIELD_KINDS.get(col) or ("iso3_or_blank" if col == "iso3" and iso3_blank_ok else "iso3" if col == "iso3" else None)
        if kind is None:
            continue
        v = frame[col].astype(str)
        if kind == "integral":
            ok = v.str.fullmatch(r"-?\d+")
        elif kind == "month":
            ok = v.str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])")
        elif kind == "date":
            ok = v.map(cl._real_day).astype(bool)
        elif kind == "season":
            ok = v.isin(["s1", "s2"])
        elif kind == "iso2":
            ok = v.str.fullmatch(r"[A-Z]{2}")
        elif kind == "iso3":
            ok = v.str.fullmatch(r"[A-Z]{3}")
        else:
            ok = v.str.fullmatch(r"[A-Z]{3}") | (v == "")
        if not ok.all():
            raise StoreError(f"{rel}: invalid {col} values {sorted(set(v[~ok]))[:3]}")


def _parse(bundle_dir: str, rel: str) -> pd.DataFrame:
    """Parse and validate one bundle table completely (no write): columns, unique keys, strict numerics."""
    from cloud.ipcch import retained
    frame = pd.read_csv(os.path.join(bundle_dir, rel), dtype=str, keep_default_na=False)
    exact, keys, numeric = _schema(rel)
    if exact is not None and tuple(frame.columns) != tuple(exact):
        raise StoreError(f"{rel}: columns {list(frame.columns)} != {list(exact)}")
    if exact is None and keys and frame.columns[0] != keys[0]:
        raise StoreError(f"{rel}: first column must be {keys[0]}")
    if keys and frame.duplicated(list(keys)).any():
        raise StoreError(f"{rel}: duplicate keys {frame.loc[frame.duplicated(list(keys)), list(keys)].head(3).to_dict('records')}")
    cols = [c for c in frame.columns if c != "admin_code"] if numeric == ("*",) else list(numeric)
    for c in cols:
        text = frame[c]
        try:
            text.replace("", np.nan).astype("float64")
        except ValueError as exc:
            raise StoreError(f"{rel}: column {c} has non-numeric values") from exc
    if not rel.startswith("fixed/acled/"):                 # byte-preserved ACLED tables are validated by acled.AcledTables
        _check_fields(frame, rel)
    if rel == "fixed/season_windows.csv":
        from cloud.ipcch import climate as cl
        try:
            cl.completed_windows(frame, "9998-12")          # shared window validator (no origin cut): real dates, end > start, unique
        except Exception as exc:
            raise StoreError(f"{rel}: {exc}") from exc
    if rel == "history/history_snapshot.csv":
        retained.validate_snapshot(frame, rel)
    if rel == "history/idp_national.csv":
        from cloud.ipcch.assembly import validate_idp_national
        try:
            validate_idp_national(frame)
        except Exception as exc:
            raise StoreError(f"{rel}: {exc}") from exc
    return frame


def initialise(store: ObjectStore, root: StoreRoot, bundle_dir: str, *, binding: bd.Binding) -> dict[str, Any]:
    """Two phases: (1) for the WHOLE bundle - the combination binding (real: exactly the envelope's handoff bundle with
    its finalized acceptance entries; smoke: the fixture bundle only, R48), bytes vs manifest, acceptance record, full
    parse/schema validation and conflicts with existing HEADs and with the store's combination pairing; (2) only then
    the commits, the pairing last. A malformed, unbound or conflicting file therefore leaves the store untouched (a
    crash mid-commit leaves already-committed tables without a pairing, so nothing reads them until a rerun completes)."""
    from cloud.ipcch import retained
    if binding.mode != root.mode:
        raise StoreError(f"{binding.mode} binding cannot initialise the {root.mode} store (R48)")
    try:
        ident = bd.verify_handoff(binding, bundle_dir) if root.mode == "real" else bd.verify_fixture_bundle(binding, bundle_dir)
    except bd.BindingError as exc:
        raise StoreError(str(exc)) from exc
    manifest, entries = ident["_manifest"], ident.get("_entries")
    if manifest.get("schema") != SCHEMA:          # roster size/sha: bound by the envelope (real) or declared (smoke)
        raise StoreError(f"bundle schema {manifest.get('schema')} != {SCHEMA}")
    wanted = bd.pairing(binding, ident)
    bound, pairing_generation = bd.check_store_pairing(store, root, wanted)
    acceptance = AcceptanceManifest(store, root)
    runtime = sorted(rel for rel in manifest["files"] if not rel.startswith("audit/"))
    plan, report = [], {"initialised": [], "unchanged": [], "verified_files": [], "root": root.uri,
                        "binding": binding.reference(), "pairing": wanted}
    for rel in runtime:
        sha = _sha(os.path.join(bundle_dir, rel))
        if sha != manifest["files"][rel]["sha256"]:
            raise StoreError(f"{rel}: bytes differ from handoff_manifest.json")
        record = acceptance.require(rel, sha)
        if entries is not None and any(record[k] != entries[rel][k] for k in ("acceptor", "accepted_at")):
            raise StoreError(f"{rel}: store acceptance record differs from the envelope-bound finalized entry (R45)")
        if not rel.endswith(".csv"):         # e.g. the geometry: verified and accepted, read from the bundle location
            report["verified_files"].append(rel)
            continue
        frame = _parse(bundle_dir, rel)
        if rel == "fixed/roster.csv" and len(frame) != ident["roster_size"]:
            raise StoreError(f"{rel}: {len(frame)} rows != declared roster {ident['roster_size']}")
        table = VersionedTable(store, root, table_name(rel))
        head, generation = table.head()
        if head is not None and head["record"].get("source_sha256") != sha:
            raise StoreError(f"{table.table} already holds different accepted content; refusing to replace it")
        plan.append((rel, sha, record, frame, table, head, generation))
    for rel, sha, record, frame, table, head, generation in plan:
        if head is not None:
            report["unchanged"].append(rel)
            continue
        meta = {"source": rel, "source_sha256": sha, "acceptance": {k: record[k] for k in ("acceptor", "accepted_at", "kind")},
                "combination": binding.reference()}
        if rel == "history/history_snapshot.csv":
            snap, cutoff = retained.validate_snapshot(frame, table.table)
            rec = {**retained.snapshot_record("initialise", snap, cutoff, {"bundle": rel, "sha256": sha}), **meta}
        else:
            rec = {"action": "initialise", **meta}
        table.commit(frame, rec, expected_generation=generation)
        report["initialised"].append(rel)
    if not bound:
        bd.commit_store_pairing(store, root, wanted, pairing_generation, binding)
    return report


def install_acceptance(store: ObjectStore, root: StoreRoot, bundle_dir: str, *, binding: bd.Binding) -> dict[str, Any]:
    """REAL: append the envelope-bound FINALIZED acceptance entries to the store's acceptance manifest (R45); entries
    already present with the same name, sha256, acceptor and date are kept. Smoke stores carry their own fixture
    records and never read the real entries (R48)."""
    if root.mode != "real" or binding.mode != "real":
        raise StoreError("only a real store installs the bound real acceptance entries (R48)")
    try:
        ident = bd.verify_handoff(binding, bundle_dir)
    except bd.BindingError as exc:
        raise StoreError(str(exc)) from exc
    have = AcceptanceManifest(store, root).records()
    present = set(map(tuple, have[["name", "sha256", "acceptor", "accepted_at"]].itertuples(index=False)))
    new = [{k: e[k] for k in ("name", "sha256", "source", "acceptor", "accepted_at", "kind")}
           for _, e in sorted(ident["_entries"].items()) if (e["name"], e["sha256"], e["acceptor"], e["accepted_at"]) not in present]
    if new:
        AcceptanceManifest(store, root).append(new)
    return {"appended": len(new), "acceptance_entries_sha256": ident["acceptance_entries_sha256"]}


def _read(store, root, rel, **numeric):
    frame, head, _ = VersionedTable(store, root, table_name(rel)).read({c: str for c in ("admin_code", "month", "season", "iso3",
                                                                                         "report_month", "gs_start_date",
                                                                                         "gs_end_date_exclusive", "method_id")})
    if frame is None:
        raise StoreError(f"{table_name(rel)} is not initialised (R45)")
    return frame


def read_assembly_inputs(store: ObjectStore, root: StoreRoot, binding: bd.Binding) -> AssemblyInputs:
    """Assembly inputs from the initialised (and later appended/refreshed) stores of THIS binding's combination (a store
    paired with another package or bundle is refused); the feature order is the bound package's. ACLED is supplied by
    the caller from the weekly store (``acled.monthly_series``)."""
    bd.require_store_pairing(store, root, binding)
    order = binding.feature_order
    def num(frame, cols):
        # exact text -> float64 (correctly rounded), empty -> NaN; the stored text is the bundle's round-trip repr
        return frame.assign(**{c: frame[c].replace("", np.nan).astype("float64") for c in cols})

    def series(rel):
        f = _read(store, root, rel)
        return num(f.assign(admin_code=f["admin_code"].astype(np.int64)), ["value"])[["admin_code", "month", "value"]]

    roster = tuple(int(a) for a in _read(store, root, "fixed/roster.csv")["admin_code"])
    seasonal = {}
    for b in cp.CLIMATE_BASES:
        f = _read(store, root, f"history/climate_gs_{b}.csv")
        seasonal[b] = num(f.assign(admin_code=f["admin_code"].astype(np.int64), season_year=f["season_year"].astype(np.int64)),
                          ["value"])[["admin_code", "season_year", "season", "value"]]
    windows = _read(store, root, "fixed/season_windows.csv")
    windows = windows.assign(admin_code=windows["admin_code"].astype(np.int64), season_year=windows["season_year"].astype(np.int64))
    static = _read(store, root, "fixed/static29.csv")
    ae = _read(store, root, "fixed/ae_descriptors.csv")
    ident = _read(store, root, "fixed/area_identity.csv")
    snap = _read(store, root, "history/history_snapshot.csv")
    nat = _read(store, root, "history/idp_national.csv")
    return AssemblyInputs(
        climate_monthly={b: series(f"history/climate_month_{b}.csv") for b in cp.CLIMATE_BASES}, climate_seasonal=seasonal,
        season_windows=windows, interim={f: series(f"history/{f}.csv") for f in INTERIM_FAMILIES}, acled=None,
        idp_national=num(nat, ["stock"]), idp_local=series("history/idp_local.csv"),
        snapshot=snap.assign(area_id=snap["area_id"].astype(np.int64), phase=snap["phase"].astype(np.int64)),
        static29=num(static, [c for c in static.columns if c != "admin_code"]),
        descriptors=num(ae, [c for c in ae.columns if c != "admin_code"]),
        identity=num(ident.assign(iso3=ident["iso3"].replace("", None)), ["lat", "lon"]),
        roster=roster, order=tuple(order))


def read_population(store: ObjectStore, root: StoreRoot, binding: bd.Binding, origin: str):
    """Output population fields at feature month O for every roster area of THIS binding's store, from the initialised
    population reference through the existing no-future ``PopulationSnapshotBuilder`` (``geography.population_snapshot``)."""
    from cloud.ipcch import geography
    bd.require_store_pairing(store, root, binding)
    roster = _read(store, root, "fixed/roster.csv")["admin_code"]
    ref = _read(store, root, "fixed/population_reference.csv")
    return geography.population_snapshot(ref.assign(population_estimate=ref["population_estimate"].replace("", np.nan).astype("float64")),
                                         origin=origin, roster=roster)
