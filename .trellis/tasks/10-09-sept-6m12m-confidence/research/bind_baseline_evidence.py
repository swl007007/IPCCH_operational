"""Bind the built diagnostic evidence into ``cloud_pipeline/bootstrap/baseline.json`` (design section 4).

* Verifies every evidence CSV against its builder report and re-validates its bytes with the
  production evidence validator (``delivery_outputs.area_evidence`` / ``residual_evidence``)
  against the real roster, package identity and acceptance rules.
* Writes ``bootstrap/evidence/provenance.json`` (sources, builders, environment, counts,
  regression gates, previous baseline sha256).
* Rewrites ``baseline.json`` with the same serialization; before writing it proves that only
  ``files`` (additions under ``evidence/``) and the 13 ``delivery.diagnostics`` entries change.
  FEWSNET 0m keeps both families ``unavailable/missing_evidence``.

The old baseline bytes are kept at ``research/baseline.before.json`` for rollback.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve()
RESEARCH = HERE.parent
REPO = HERE.parents[4]
CP = REPO / "cloud_pipeline"
BOOT = CP / "bootstrap"
sys.path.insert(0, str(CP))
from cloud.orchestrator import delivery_outputs as out  # noqa: E402

BACKUP = RESEARCH / "baseline.before.json"
REPORT = RESEARCH / "bind_baseline_evidence.json"
ORIGIN_FOR_CHECK = "2026-09"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def serialize(baseline: dict, crlf: bool) -> bytes:
    text = json.dumps(baseline, indent=2, sort_keys=True) + "\n"
    return (text.replace("\n", "\r\n") if crlf else text).encode()


def evidence_plan(fews: dict, ipcch: dict) -> dict:
    """(system, horizon, family) -> evidence file name."""
    plan = {}
    for name, item in fews["evidence"].items():
        for family in ("polygon_confidence", "country_confidence"):
            plan[("fewsnet", item["horizon_months"], family)] = name
    for name, item in ipcch["evidence"].items():
        families = ("maximum_phase",) if name.endswith("_residual.csv") else ("polygon_training_errors", "country_confidence")
        for family in families:
            plan[("ipcch", item["horizon_months"], family)] = name
    return plan


def validate_bytes(name: str, item: dict, data: bytes, packages: dict) -> dict:
    """Run the production validator exactly as ``scope_diagnostics`` would for this evidence."""
    system, horizon = item["system"], item["horizon_months"]
    roster = pd.read_csv(BOOT / f"assets/{system}/roster.csv", dtype=str)["admin_code"].str.strip().tolist()
    package_id = packages[(system, horizon)]
    if system == "fewsnet":
        model_dir = BOOT / f"models/fewsnet/{horizon}m"
        acceptance = {"system": system, "origin": ORIGIN_FOR_CHECK, "period": out.fewsnet_validation_period(model_dir),
                      "latest_end": None}
    else:
        acceptance = {"system": system, "origin": ORIGIN_FOR_CHECK, "period": None,
                      "latest_end": out.ipcch_training_cutoff_month(BOOT / "models/ipcch")}
    declared = {"status": "available", "evidence_model_package_id": package_id, "evidence_horizon_months": horizon}
    frame = pd.read_csv(io.BytesIO(data), dtype={"polygon_id": str, "target_month": str})
    parse = out.residual_evidence if name.endswith("_residual.csv") else out.area_evidence
    table, identity = parse(frame, roster=roster, model_package_id=package_id, horizon=horizon, declared=declared,
                            acceptance=acceptance)
    return {"rows": len(table), "polygons": int(table["polygon_id"].nunique()), "identity": identity,
            "acceptance": acceptance}


def main() -> int:
    path = BOOT / "baseline.json"
    old_bytes = path.read_bytes()
    crlf = b"\r\n" in old_bytes
    old = json.loads(old_bytes)
    if serialize(old, crlf) != old_bytes:
        raise SystemExit("baseline.json serialization is not reproducible; refusing to rewrite")
    if BACKUP.exists():
        backup = BACKUP.read_bytes()
        if backup != old_bytes:
            # Already bound: the backup is the pre-binding baseline. Re-running is idempotent only.
            old_bytes, old = backup, json.loads(backup)
    else:
        BACKUP.write_bytes(old_bytes)
    old_sha = sha(old_bytes)
    if any(e["status"] != "unavailable" for e in old["delivery"]["diagnostics"]):
        raise SystemExit("pre-binding baseline already has available diagnostics")

    fews = json.loads((RESEARCH / "fewsnet_proxy_evidence.json").read_text())
    ipcch = json.loads((RESEARCH / "ipcch_resubstitution_evidence.json").read_text())
    regression = json.loads((RESEARCH / "ipcch_resubstitution_regression_h5.json").read_text())
    if not (fews["regression"]["passed"] and regression["passed"]):
        raise SystemExit("regression gates G1/G2 have not passed")
    packages = {(m["system"], m["horizon_months"]): m["package_id"] for m in old["models"]}
    items = {**fews["evidence"], **ipcch["evidence"]}
    checks, files = {}, {}
    for name, item in sorted(items.items()):
        data = (BOOT / "evidence" / name).read_bytes()
        if sha(data) != item["sha256"] or len(data) != item["size"]:
            raise SystemExit(f"{name}: bytes differ from the builder report")
        if item["model_package_id"] != packages[(item["system"], item["horizon_months"])]:
            raise SystemExit(f"{name}: package id is not the baseline package")
        checks[name] = validate_bytes(name, item, data, packages)
        files[f"evidence/{name}"] = {"sha256": item["sha256"], "size_bytes": len(data)}
        print(f"{name}: validator accepted {checks[name]['rows']} rows", flush=True)

    provenance = {
        "schema_version": "diagnostic-evidence-provenance-v1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "task": ".trellis/tasks/10-09-sept-6m12m-confidence",
        "decisions": "prd.md D4 (sources), D7 (coverage), D9/D14 (FEWSNET proxy allowlist and labels)",
        "previous_baseline_sha256": old_sha,
        "runtime_reads_external_paths": False,
        "evidence": {name: {k: v for k, v in item.items() if k != "write"} for name, item in sorted(items.items())},
        "validator_check": {"origin_used": ORIGIN_FOR_CHECK, "results": checks},
        "fewsnet": {"builder": fews["builder"], "builder_sha256": fews["builder_sha256"], "python": fews["python"],
                    "pandas": fews["pandas"], "error_rule": fews["error_rule"], "roster": fews["roster"],
                    "regression_g1": fews["regression"]},
        "ipcch": {"builder": ipcch["builder"], "builder_sha256": ipcch["builder_sha256"],
                  "environment": ipcch["environment"], "float_precision": ipcch["float_precision"],
                  "source": ipcch["source"], "trainer": ipcch["trainer"], "roster": ipcch["roster"],
                  "phase3_threshold": ipcch["phase3_threshold"], "scopes": ipcch["scopes"],
                  "regression_g2": {k: regression[k] for k in ("passed", "float_precision", "inputs",
                                                               "training_keys_equal_saved", "replay_checks",
                                                               "polygon_count_comparison", "residual_comparison")}},
        "binding": {"script": str(HERE.relative_to(REPO)), "script_sha256": sha(HERE.read_bytes())},
    }
    prov_path = BOOT / "evidence/provenance.json"
    prov_bytes = (json.dumps(provenance, indent=1, sort_keys=True) + "\n").encode()
    prov_path.write_bytes(prov_bytes)
    files["evidence/provenance.json"] = {"sha256": sha(prov_bytes), "size_bytes": len(prov_bytes)}

    new = copy.deepcopy(old)
    if set(files) & set(new["files"]):
        raise SystemExit("evidence paths already present in baseline files")
    new["files"].update(files)
    plan = evidence_plan(fews, ipcch)
    flipped = []
    for entry in new["delivery"]["diagnostics"]:
        key = (entry["system"], entry["horizon_months"], entry["family"])
        if key in plan:
            entry.clear()
            entry.update({"system": key[0], "horizon_months": key[1], "family": key[2], "status": "available",
                          "evidence": {"local_path": f"evidence/{plan[key]}"},
                          "evidence_model_package_id": packages[key[:2]], "evidence_horizon_months": key[1]})
            flipped.append(key)
    if len(flipped) != 13 or len(plan) != 13 or set(flipped) != set(plan):
        raise SystemExit(f"expected 13 bound declarations, got {len(flipped)} / plan {len(plan)}")
    remaining = [(e["system"], e["horizon_months"], e["family"], e.get("reason"))
                 for e in new["delivery"]["diagnostics"] if e["status"] != "available"]
    if remaining != [("fewsnet", 0, "polygon_confidence", "missing_evidence"),
                     ("fewsnet", 0, "country_confidence", "missing_evidence")]:
        raise SystemExit(f"unexpected unavailable declarations {remaining}")

    # Only files (additions) and delivery.diagnostics may differ.
    assert {k: v for k, v in old.items() if k not in ("files", "delivery")} == \
           {k: v for k, v in new.items() if k not in ("files", "delivery")}
    assert {k: v for k, v in old["delivery"].items() if k != "diagnostics"} == \
           {k: v for k, v in new["delivery"].items() if k != "diagnostics"}
    assert all(new["files"][k] == v for k, v in old["files"].items())
    assert set(new["files"]) - set(old["files"]) == set(files) and all(k.startswith("evidence/") for k in files)

    new_bytes = serialize(new, crlf)
    path.write_bytes(new_bytes)
    if path.read_bytes() != new_bytes:
        raise SystemExit("baseline.json write verification failed")
    report = {"previous_baseline_sha256": old_sha, "new_baseline_sha256": sha(new_bytes), "line_endings": "CRLF" if crlf else "LF",
              "added_files": files, "bound_declarations": [list(k) + [plan[k]] for k in flipped],
              "unavailable_declarations": [list(r) for r in remaining], "backup": str(BACKUP.relative_to(REPO))}
    REPORT.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("previous_baseline_sha256", "new_baseline_sha256",
                                             "unavailable_declarations")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
