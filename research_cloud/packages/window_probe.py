"""Window-probe reused-comparator packages (8 registered versions: pooled and regional_ungated x H1/3/6/12).

The history-window probe (MLflow run e9cfa99f, ``source/run_probe.py``) compares its own expanding-window refits
with frozen P6 comparators; its own refits were not retained, the comparators are P6 units. They keep their own
registry identities (``zz_prov.arm_kind=reused_comparator``, original arms ``base_global`` / ``base_local``) and get
their own packages, because their served keys, routing and references are the probe's, not a P6 package's:

* served keys: every row of each selected cell (``plan.json`` ``selected``: H1/H3/H6 September 2023-2025, H12
  September 2024 and January 2025), mapped or not;
* ``base_global`` (registered ``pooled``): the cell's single P6 global unit (run_probe.py:131-141, identity and
  window checked by the probe against P6's own records);
* ``base_local`` (registered ``regional_ungated``): in a mapped region, the provider of P6's gate-pair
  ``local_routed`` raw (``local_routed_provider``: the local unit where ``local_fit_ok``, else the global unit),
  without gate adoption (run_probe.py:148-176); unmapped rows keep the global unit;
* decoding: P6 ``projection.project_and_decode`` (vendored from P6's ``source_code`` artifact, as for P6 packages);
* references: the probe's saved ``predictions_hHH_U.csv.gz`` (``base_global_*`` / ``base_local_*``), whose sha256
  values and the plan's are checked against the probe's ``artifact-hashes.json`` before use.

Unit bytes come from the P6 run root, enforced against P6's member manifest; inputs are P6's prepared rich561 rows.
"""
import io
import json
import os

import numpy as np
import pandas as pd

from research_cloud.packages import geoxgb
from research_cloud.packages.common import PackageBuilder, PackageError, ensure_local, select_reference, sha256_file

TARGETS = geoxgb.TARGETS
ARM_OF = {"pooled": "base_global", "regional_ungated": "base_local"}


def probe_files(probe_dir):
    hashes = json.load(open(os.path.join(probe_dir, "artifact-hashes.json")))

    def verified(name):
        path = os.path.join(probe_dir, name)
        if name not in hashes or sha256_file(path) != hashes[name]:
            raise PackageError(f"probe artifact {name} does not match artifact-hashes.json")
        return path
    return verified


def routing_for(cell, arm):
    """{region: (unit, route)} for one selected cell; '' is the unmapped region."""
    globals_ = {r["global_identity"] for r in cell["regions"]}
    if len(globals_) != 1:
        raise PackageError(f"cell H{cell['H']} {cell['U']} names {len(globals_)} global units")
    gid = next(iter(globals_))
    if arm == "base_global":
        return gid, {r["region"]: (gid, "pooled_global") for r in cell["regions"]} | {"": (gid, "pooled_global")}
    out = {"": (gid, "unmapped_global")}
    for r in cell["regions"]:
        provider = r["local_routed_provider"]
        ok = r["local_fit_ok"] == "True"
        if provider != (r["local_identity"] if ok else gid):
            raise PackageError(f"region {r['region']} H{cell['H']} {cell['U']}: local_routed_provider inconsistent with local_fit_ok")
        out[r["region"]] = (provider, "local_routed" if ok else "local_fit_not_ok_global")
    return gid, out


def build(out_dir, *, probe_dir, p6_root, p6_source_code, p6_members_manifest, version, lead, registered_arm,
          code_identity, original_runtime, linux_runtime, per_unit=32):
    arm = ARM_OF[registered_arm]
    h = f"h{int(lead):02d}"
    verified = probe_files(probe_dir)
    plan = json.load(open(verified("plan.json")))
    cells = [c for c in plan["selected"] if int(c["H"]) == int(lead)]
    if not cells:
        raise PackageError(f"no selected cells for H{lead}")
    rel = {"keys": f"prepared/keys_{h}.csv.gz", "X": f"prepared/X_rich561_{h}.npy",
           "feature_order": "prepared/feature_order.csv", "frozen_map": f"stage1/frozen_map_{h}.csv"}
    ensure_local([os.path.join(p6_root, r) for r in rel.values()])
    keys = pd.read_csv(os.path.join(p6_root, rel["keys"]))
    X = np.load(os.path.join(p6_root, rel["X"]), mmap_mode="r")
    if len(keys) != len(X) or keys.duplicated(["admin_code", "target_ord"]).any():
        raise PackageError("P6 keys/X misaligned or non-unique")
    frozen = pd.read_csv(os.path.join(p6_root, rel["frozen_map"]), dtype={"node_id": str})
    region_of = dict(zip(frozen["admin_code"].astype(int), frozen["node_id"]))

    rows, routing = [], []
    for cell in cells:
        pred = pd.read_csv(verified(f"predictions_{h}_{cell['U']}.csv.gz"), float_precision="round_trip",
                           keep_default_na=False, dtype={"region": str})
        if (pred["target_ord"] != int(cell["target_ord"])).any() or pred.duplicated(["admin_code", "target_ord"]).any():
            raise PackageError(f"cell {cell['U']}: saved predictions are not one row per key of the selected month")
        mapped = pred["admin_code"].astype(int).map(lambda a: region_of.get(a, ""))
        if not (mapped == pred["region"]).all():
            raise PackageError(f"cell {cell['U']}: P6 frozen map disagrees with the probe's regions")
        gid, table = routing_for(cell, arm)
        missing = set(pred["region"]) - set(table)
        if missing:
            raise PackageError(f"cell {cell['U']}: regions without a plan entry {sorted(missing)[:3]}")
        pred["unit"] = [table[r][0] for r in pred["region"]]
        pred["route"] = [table[r][1] for r in pred["region"]]
        if arm == "base_local" and not (pred["base_local_ok"].astype(str).eq("True") == pred["route"].eq("local_routed")).all():
            raise PackageError(f"cell {cell['U']}: saved base_local_ok disagrees with the plan's local_fit_ok routing")
        rows.append(pred)
        routing += [{"target_ord": int(cell["target_ord"]), "region": r, "unit": u, "route": rt} for r, (u, rt) in table.items()]
    served = pd.concat(rows, ignore_index=True)
    routing = pd.DataFrame(routing).drop_duplicates().sort_values(["target_ord", "region"])

    members = geoxgb._members(p6_members_manifest)
    units = sorted(served["unit"].unique())
    gaps = [f"unit {d}: required member {n} absent from the P6 member manifest"
            for d in units for n in geoxgb.REQUIRED_UNIT_FILES if f"models/{d[:2]}/{d}/{n}" not in members]
    unit_files = sorted(m for m in members if any(m.startswith(f"models/{d[:2]}/{d}/") for d in units))
    ensure_local([os.path.join(p6_root, m) for m in unit_files])
    b = PackageBuilder(out_dir)
    for m in unit_files:
        b.add_file(os.path.join(p6_root, m), "weights/" + "/".join(m.split("/")[2:]), members[m]["sha256"], members[m]["bytes"])
    for d in units:
        record = json.load(open(os.path.join(out_dir, "weights", d, "record.json")))
        for q in TARGETS:
            if record.get("booster_sha256", {}).get(q) != b.files[f"weights/{d}/{q}.ubj"]["sha256"]:
                gaps.append(f"unit {d}: {q}.ubj bytes differ from record.json booster_sha256")
    b.add_file(os.path.join(p6_root, rel["feature_order"]), "deps/" + rel["feature_order"])
    b.add_file(os.path.join(p6_root, rel["frozen_map"]), "deps/" + rel["frozen_map"])
    b.add_file(verified("plan.json"), "deps/probe/plan.json")
    for cell in cells:
        b.add_file(verified(f"predictions_{h}_{cell['U']}.csv.gz"), f"deps/probe/predictions_{h}_{cell['U']}.csv.gz")
    b.add_bytes("deps/routing.csv", routing.to_csv(index=False).encode())

    star = served[[f"{arm}_{q}_star" for q in TARGETS]].to_numpy(dtype=np.float64)
    ref = select_reference(served, "unit", pd.Series(np.abs(star - 0.20).min(axis=1), index=served.index),
                           ["admin_code", "target_ord"], per_unit=per_unit, cover_cols=("route",))
    row_of = pd.Series(np.arange(len(keys)), index=pd.MultiIndex.from_frame(keys[["admin_code", "target_ord"]]))
    inputs = np.ascontiguousarray(X[row_of.loc[list(zip(ref["admin_code"], ref["target_ord"]))].to_numpy()], dtype=np.float64)
    buf = io.BytesIO()
    np.save(buf, inputs, allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    expected = ref[["admin_code", "target_ord", "route", "unit"]].copy()
    for q in TARGETS:
        expected[f"{q}_raw"] = ref[f"{arm}_{q}_raw"].to_numpy()
        expected[f"{q}_star"] = ref[f"{arm}_{q}_star"].to_numpy()
    expected["phase"] = ref[f"{arm}_phase"].to_numpy()
    b.add_bytes("reference/expected.csv", expected.to_csv(index=False, float_format="%.17g").encode())
    src_pkg = os.path.join(p6_source_code, "ipcch_geoxgb")
    b.add_bytes("loader/ipcch_geoxgb/__init__.py", b"")
    for name in geoxgb.LOADER_FILES:
        b.add_file(os.path.join(src_pkg, name), f"loader/ipcch_geoxgb/{name}")
    b.add_bytes("loader/entry.py", geoxgb.ENTRY.encode())

    n_features = len(pd.read_csv(os.path.join(p6_root, rel["feature_order"])))
    return b.finalize({
        "family": "geoxgb_window_probe", "identity": version, "lead_months": int(lead), "arm": registered_arm,
        "original_arm": arm, "arm_kind": "reused_comparator",
        "status": "complete" if not gaps else "retained_weights_missing_dependencies", "gaps": gaps,
        "fitted_units": len(units),
        "comparator_scope": {"selected_cells": [{"U": c["U"], "target_ord": int(c["target_ord"]), "origin": int(c["origin"])} for c in cells],
                             "selection_rule": plan.get("selection_rule"),
                             "note": "exploratory selected-date comparison; not a whole-P6 deployment; P6 packages are not aliases"},
        "routing": {"table": "deps/routing.csv", "frozen_map": "deps/" + rel["frozen_map"], "feature_order": "deps/" + rel["feature_order"],
                    "served_keys": int(len(served)), "routes_in_version": sorted(served["route"].unique()),
                    "rule": "pooled: the cell's P6 global unit; regional_ungated: local_routed_provider per mapped region "
                            "(local unit where local_fit_ok, else global), unmapped rows global; no gate adoption"},
        "source": {"probe_run": "runs:/e9cfa99f94dd4a67b0e3b6ed511708ad/source", "probe_dir": probe_dir,
                   "artifact_hashes_sha256": sha256_file(os.path.join(probe_dir, "artifact-hashes.json")),
                   "p6_run_root": p6_root, "p6_members_manifest": p6_members_manifest,
                   "p6_members_manifest_sha256": sha256_file(p6_members_manifest)},
        "code": {"identity": code_identity, "package": "ipcch_geoxgb", "vendored_from": src_pkg,
                 "vendored_files": {n: sha256_file(os.path.join(src_pkg, n)) for n in geoxgb.LOADER_FILES},
                 "routing_source": "source/run_probe.py:131-141 (global), 148-176 (local_routed)"},
        "runtime": {"original": original_runtime, "linux": linux_runtime},
        "loader": {"entry": "loader/entry.py", "call": "load(package_dir).predict(keys[admin_code,target_ord], X)",
                   "inputs": f"float64 rows ({n_features} features) in feature_order.csv order; NaN = missing",
                   "unserved_keys": "KeyError (outside the probe's selected cells)"},
        "reference": {"rows": int(len(expected)), "per_unit_cap": per_unit,
                      "selection": "per unit (cap): >=1 row per route, half nearest a 0.20 boundary, rest by key hash",
                      "routes_covered": sorted(expected["route"].unique()),
                      "rows_with_missing_features": int(np.isnan(inputs).any(axis=1).sum())},
        "tolerance": {"declared_before_comparison": True,
                      "projected_shares": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref)",
                      "raw_shares": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref)",
                      "phase": "new phase must decode from new projected shares; drift only within that reference's tolerance",
                      "routing": "resolved unit and route must equal the frozen reference exactly"},
    })
