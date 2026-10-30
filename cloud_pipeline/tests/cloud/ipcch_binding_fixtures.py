"""Task 10-29 test helpers: a tiny model-combination package (no weights are loaded) and combination envelopes."""

import hashlib
import json
import os

from cloud.ipcch import binding as bd


def make_package(root, order, combination_id="ipcch-test-combination", contract_body="model_feature,category\n"):
    root.mkdir(parents=True, exist_ok=True)
    files, scopes = {}, {}
    for scope, (h, lead) in bd.SCOPES.items():
        d = root / f"scope_{scope}m"
        d.mkdir(exist_ok=True)
        (d / "feature_columns.json").write_text(json.dumps(list(order)))
        (d / "feature_contract.csv").write_text(contract_body + f"# scope {scope}\n")
        (d / "phase2_worse_model.json").write_text(json.dumps({"scope": scope}))
        for rel in ("feature_columns.json", "feature_contract.csv", "phase2_worse_model.json"):
            files[f"scope_{scope}m/{rel}"] = {"sha256": hashlib.sha256((d / rel).read_bytes()).hexdigest()}
        scopes[scope] = {"model_horizon_months": h, "public_lead_months": lead, "training_cutoff": "2025-11",
                         "feature_schema_sha256": files[f"scope_{scope}m/feature_contract.csv"]["sha256"]}
    (root / "evidence").mkdir(exist_ok=True)
    (root / "evidence" / "e.csv").write_text("area,residual\n1,0.1\n")
    files["evidence/e.csv"] = {"sha256": hashlib.sha256((root / "evidence" / "e.csv").read_bytes()).hexdigest()}
    (root / bd.PACKAGE_MANIFEST).write_text(json.dumps({"kind": "ipcch_model_combination", "combination_id": combination_id,
                                                        "contract_version": "test-v1", "status": "candidate",
                                                        "acceptor": None, "accepted_at": None, "files": files,
                                                        "scopes": scopes}))
    return root


def smoke_envelope(path, package_root, version=1):
    """A candidate envelope whose handoff digests name some real bundle smoke never reads."""
    pkg = bd.package_identity(str(package_root))
    env = {"schema": bd.ENVELOPE_SCHEMA, "envelope_version": version, "envelope_id": f"{pkg['combination_id']}/envelope-v{version}",
           "status": "candidate", "acceptor": None, "accepted_at": None, "created_at": "2026-10-30T00:00:00Z",
           "package": {k: pkg[k] for k in ("package_manifest_sha256", "combination_id", "contract_version", "scopes",
                                           "feature_order_sha256", "feature_count")},
           "handoff": {"manifest_sha256": "a" * 64, "schema": bd.HANDOFF_SCHEMA, "roster_size": 6226, "roster_sha256": "b" * 64,
                       "acceptance_entries_sha256": None, "draft_acceptance_entries_sha256": "c" * 64}}
    return bd.write_envelope(env, str(path))


def finalize_entries(bundle_dir, acceptor="research lead", accepted_at="2026-10-31"):
    man = json.load(open(os.path.join(bundle_dir, bd.HANDOFF_MANIFEST)))
    entries = [{"name": rel, "sha256": v["sha256"], "source": "test bundle", "kind": "delivered", "acceptor": acceptor,
                "accepted_at": accepted_at} for rel, v in sorted(man["files"].items()) if not rel.startswith("audit/")]
    with open(os.path.join(bundle_dir, bd.ACCEPTANCE_ENTRIES), "w") as f:
        json.dump(entries, f)
    return entries


def make_scoring_package(root, order, combination_id="ipcch-test-scoring", seed=0, evidence_areas=("11", "12", "13")):
    """A loadable model-combination package (tiny XGBoost q2..q5 per scope on the 527-name order, the real contract and
    metadata formats) for runtime scoring tests."""
    import numpy as np
    import pandas as pd
    import xgboost

    root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(60, len(order))), columns=list(order))
    files, scopes = {}, {}
    cutoffs = {"0": "2025-11", "6": "2025-05", "12": "2024-11"}
    for scope, (h, lead) in bd.SCOPES.items():
        d = root / f"scope_{scope}m"
        d.mkdir(exist_ok=True)
        (d / "feature_columns.json").write_text(json.dumps(list(order)))
        rows = ["feature_name,scope_months,category,source_column,dtype,required_in_input,missing_tolerance,fill_method,"
                "fill_value_or_stat_key,lookup_asset,derive_function,as_of_policy,notes"]
        rows += [f"{c},{scope},required,{c},float,True,1.0,none,,,,feature_origin_O=M-2,test" for c in order]
        (d / "feature_contract.csv").write_text("\n".join(rows) + "\n")
        (d / "model_metadata.json").write_text(json.dumps({
            "model_horizon_months": h, "public_lead_months": lead, "scope_months": int(scope),
            "thresholds": {"default": 0.2}, "monotonicity_policy": "cummax", "training_cutoff": cutoffs[scope],
            "feature_policy": "nan_passthrough_no_imputation", "package_id": combination_id}))
        for k, target in enumerate(("phase2_worse", "phase3_worse", "phase4_worse", "phase5_worse")):
            y = (X.iloc[:, k] > (k - 1.5) * 0.5).astype(float) * (0.9 - 0.2 * k)
            model = xgboost.XGBRegressor(n_estimators=3, max_depth=2, random_state=seed)
            model.fit(X, y)
            model.save_model(str(d / f"{target}_model.json"))
        for p in d.iterdir():
            files[f"scope_{scope}m/{p.name}"] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        # model-matched evidence in the real package formats (training resubstitution, identity-bound per scope)
        ev = root / "evidence"
        ev.mkdir(exist_ok=True)
        pid, period = f"{combination_id}/scope_{scope}m", f"2014-01..{cutoffs[scope]}"
        ident = f"{pid},{scope},training_resubstitution,{period}"
        area = "polygon_id,sample_count,error_count,model_package_id,horizon_months,basis,period\n" + "".join(
            f"{a},{6 + k},{k % 3},{ident}\n" for k, a in enumerate(evidence_areas))
        months = [f"2020-{m:02d}" for m in range(1, 7)]
        residual = ("polygon_id,target_month,phase2_worse_residual,phase3_worse_residual,phase4_worse_residual,"
                    "phase5_worse_residual,model_package_id,horizon_months,basis,period\n") + "".join(
            f"{a},{m},{0.01 * (i - 2)},{0.02 * (j - 3)},0.0,-0.001,{ident}\n"
            for i, a in enumerate(evidence_areas) for j, m in enumerate(months))
        evidence = {}
        for part, text in (("area", area), ("residual", residual)):
            name = f"evidence/ipcch_{scope}m_resubstitution_{part}.csv"
            (root / name).write_text(text)
            files[name] = {"sha256": hashlib.sha256(text.encode()).hexdigest()}
            evidence[part] = {"file": name, "sha256": files[name]["sha256"]}
        scopes[scope] = {"model_horizon_months": h, "public_lead_months": lead, "training_cutoff": cutoffs[scope],
                         "feature_schema_sha256": files[f"scope_{scope}m/feature_contract.csv"]["sha256"],
                         "evidence": {**evidence, "basis": "training_resubstitution", "period": period,
                                      "model_package_id": pid, "horizon_months": int(scope)}}
    (root / bd.PACKAGE_MANIFEST).write_text(json.dumps({"kind": "ipcch_model_combination", "combination_id": combination_id,
                                                        "contract_version": "test-v1", "status": "candidate",
                                                        "files": files, "scopes": scopes}))
    return root
