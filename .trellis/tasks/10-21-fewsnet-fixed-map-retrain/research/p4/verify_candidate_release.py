"""Release-specific checks of the downloaded FEWS retrain candidate (bound into the operator receipt).

No evaluation, no IPCCH inference, no confidence recomputation. Per horizon:
* FEWS: 5,718 unique admin codes in 22 countries, feature month 2026-10 and the exact target month,
  every row scored by the new all-history package (suite/model path), mapping/table keys consistent;
* frozen confidence: every frozen polygon/country column (blank masks included) equals the accepted
  October source by key, per the recorded copy contract; the current country outcome equals
  1[country probability_crisis >= 0.5] for every country, with the recorded threshold 0.5;
* inherited IPCCH: all 15 scope tables (and its inherited inputs/evidence/reports) byte-identical to the
  accepted October source inventory; IPCCH package digests unchanged;
* package and provenance identities: FEWS model inventory = the fit packages; delivery.json records
  FEWS scored now and IPCCH inherited.

usage: verify_candidate_release.py CANDIDATE_DIR OUT_JSON   (exit 1 unless every check passes)
       verify_candidate_release.py --self-check            (outcome rule on the accepted October tables)
"""

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

RESEARCH = Path(__file__).resolve().parents[1]  # .trellis/tasks/<task>/research
REPO = Path(__file__).resolve().parents[5] / "cloud_pipeline"
FALLBACK = REPO / "fallback/october_2026"
FIT = Path("/home/swl007007/projects/food-crisis-research/staging/fewsnet-fixed-map-retrain-20261022"
           "/fit/full-202610-ff389b11af93-02caeb861750/model_artifacts")
SUITE = "full-202610-ff389b11af93-02caeb861750"
TARGETS = {0: "2026-10", 6: "2027-04", 12: "2027-10"}
IPCCH_TABLES = ("polygon_predictions", "country_predictions", "polygon_model_mapping", "polygon_training_errors",
                "country_confidence")


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def same_by_key(candidate: pd.DataFrame, source: pd.DataFrame, key: str, columns) -> dict:
    left = candidate[list(columns)].set_index(key).sort_index()
    right = source[list(columns)].set_index(key).sort_index()
    equal = left.index.equals(right.index) and left.equals(right)
    differing = [] if equal else [c for c in left.columns if c in right.columns and not left[c].equals(right[c])]
    return {"equal": bool(equal), "rows": int(len(left)), "differing_columns": differing}


def outcome_agreement(predictions: pd.DataFrame, confidence: pd.DataFrame, threshold: float) -> dict:
    """Current country outcome = 1[country probability_crisis >= threshold] (blank when the probability is
    blank) for every country, with the recorded threshold equal to the contract threshold."""
    probability = predictions.set_index("ISO3")["probability_crisis"]
    expected = {iso: "" if value == "" else str(int(float(value) >= threshold)) for iso, value in probability.items()}
    actual = confidence.set_index("ISO3")["country_outcome_crisis"].to_dict()
    thresholds = set(confidence["country_outcome_crisis_threshold"])
    mismatches = sorted(iso for iso in expected if actual.get(iso) != expected[iso])
    equal = set(expected) == set(actual) and not mismatches and all(t != "" and float(t) == threshold
                                                                    for t in thresholds)
    return {"equal": bool(equal), "countries": len(expected), "mismatches": mismatches,
            "crisis_countries": sum(v == "1" for v in expected.values()), "thresholds": sorted(thresholds)}


def self_check() -> dict:
    """The outcome rule reproduces the accepted October delivery's FEWS country outcomes and rejects a flip."""
    threshold = float(json.loads((RESEARCH / "confidence-source-inventory.json").read_text())
                      ["copy_contract"]["country_outcome_threshold"])
    result = {}
    for horizon in (0, 6, 12):
        scope = FALLBACK / f"scopes/{horizon}m/fewsnet"
        predictions, confidence = text(scope / "country_predictions.csv"), text(scope / "country_confidence.csv")
        flipped = confidence.copy()
        flipped.loc[0, "country_outcome_crisis"] = "0" if flipped.loc[0, "country_outcome_crisis"] == "1" else "1"
        result[f"{horizon}m"] = {"accepted": outcome_agreement(predictions, confidence, threshold)["equal"],
                                 "flip_rejected": not outcome_agreement(predictions, flipped, threshold)["equal"]}
    return {"status": "passed" if all(all(v.values()) for v in result.values()) else "failed", "horizons": result}


def main(root: Path) -> dict:
    contract = json.loads((RESEARCH / "confidence-source-inventory.json").read_text())["copy_contract"]
    source_inventory = {e["path"]: e["sha256"] for e in json.loads((FALLBACK / "manifest.json").read_text())["files"]}
    candidate_inventory = {e["path"]: e["sha256"] for e in json.loads((root / "manifest.json").read_text())["files"]}
    delivery = json.loads((root / "reports/delivery.json").read_text())
    checks, detail = {}, {}
    checks["execution_recorded"] = delivery.get("execution", {}).get("scored_systems") == ["fewsnet"] and \
        delivery["execution"].get("inherited_systems") == ["ipcch"] and delivery.get("origin_month") == "2026-10"
    models = json.loads((root / "model_inventory.json").read_text())
    for horizon in (0, 6, 12):
        fit = FIT / f"{horizon}m"
        checks[f"fewsnet_{horizon}m_package_is_fit"] = models[f"fewsnet/model_package/{horizon}m"] == {
            p.name: sha(p) for p in fit.iterdir() if p.is_file()}
        scope = root / f"scopes/{horizon}m/fewsnet"
        predictions = text(scope / "polygon_predictions.csv")
        checks[f"fewsnet_{horizon}m_areas"] = predictions["admin_code"].is_unique and len(predictions) == 5718 \
            and predictions["ISO3"].nunique() == 22
        checks[f"fewsnet_{horizon}m_months"] = set(predictions["feature_month"]) == {"2026-10"} and \
            set(predictions["target_month"]) == {TARGETS[horizon]} and set(predictions["horizon_months"]) == {str(horizon)}
        checks[f"fewsnet_{horizon}m_new_package_scored"] = set(predictions["suite_version"]) == {SUITE} and \
            set(predictions["model_artifact_path"]) == {f"fewsnet/model_package/{horizon}m"}
        mapping = text(scope / "polygon_model_mapping.csv")
        checks[f"fewsnet_{horizon}m_mapping_keys"] = set(mapping["polygon_id"]) == set(predictions["admin_code"])
        source = FALLBACK / f"scopes/{horizon}m/fewsnet"
        polygon = same_by_key(text(scope / "polygon_confidence.csv"), text(source / "polygon_confidence.csv"),
                              contract["polygon_key"], contract["polygon_frozen_columns"])
        country_candidate, country_source = text(scope / "country_confidence.csv"), text(source / "country_confidence.csv")
        country = same_by_key(country_candidate, country_source, contract["country_key"],
                              [contract["country_key"], *contract["country_frozen_columns"]])
        checks[f"fewsnet_{horizon}m_polygon_confidence_frozen"] = polygon["equal"] and polygon["rows"] == 5718
        checks[f"fewsnet_{horizon}m_country_confidence_frozen"] = country["equal"] and country["rows"] == 22
        outcome = outcome_agreement(text(scope / "country_predictions.csv"), country_candidate,
                                    float(contract["country_outcome_threshold"]))
        checks[f"fewsnet_{horizon}m_current_outcome_agrees"] = outcome["equal"]
        detail[f"{horizon}m"] = {"polygon_confidence": polygon, "country_confidence": country, "current_outcome": outcome,
                                 "predicted_crisis_areas": int((predictions["predicted_crisis"] == "1").sum())}
        for name in IPCCH_TABLES:
            relative = f"scopes/{horizon}m/ipcch/{name}.csv"
            checks[f"ipcch_{horizon}m_{name}_inherited"] = candidate_inventory.get(relative) == source_inventory[relative]
    inherited = json.loads((root / "reports/inherited_members.json").read_text())["ipcch"]
    checks["ipcch_inherited_members_match_source"] = bool(inherited["members"]) and all(
        source_inventory.get(path) == digest == candidate_inventory.get(path)
        for path, digest in inherited["members"].items())
    checks["ipcch_inherited_source_run"] = inherited["source_run_id"] == inherited["source_delivery_id"] \
        == "oct-confidence-20261009b"
    checks["ipcch_package_unchanged"] = all(
        source_inventory.get(f"ipcch/model_package/{path}") == digest for path, digest in inherited["model_package"].items())
    return {"status": "passed" if all(checks.values()) else "failed", "checks": checks, "detail": detail,
            "candidate_manifest_sha256": sha(root / "manifest.json"), "source_manifest_sha256": sha(FALLBACK / "manifest.json"),
            "inherited_members": len(inherited["members"])}


if __name__ == "__main__":
    if sys.argv[1] == "--self-check":
        report = self_check()
        print(json.dumps(report, sort_keys=True))
    else:
        report = main(Path(sys.argv[1]))
        Path(sys.argv[2]).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": report["status"], "failed": [k for k, v in report["checks"].items() if not v]}))
    sys.exit(0 if report["status"] == "passed" else 1)
