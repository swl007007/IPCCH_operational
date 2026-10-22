"""Release snapshot evidence and post-overlay survival check (no scoring).

1. Pins prepare_status.json / prepared_manifest.json of the retrain snapshot (generation, sha256).
2. Compares the snapshot's FEWS outputs with the independent local extractions (GOSIF v3 2025,
   EVI 2026-09) and the accepted full-window-20261008c 2026-08 values.
3. Runs the delivery's own fewsnet_base_panel (calendar rows, keep/keep, remote_overlay) over the
   frozen v2 history panel and checks that every panel cell <= each family's vintage survives:
   cleared cells must be re-supplied by the snapshot with the same value.
"""
import argparse, hashlib, io, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

PREFIX = "gs://food-crisis-test-ipcch-data/prepared/fewsnet-retrain-20261022a"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--staging", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.runtime_root))
    from google.cloud import storage
    from cloud.batch.remote_sources import MODEL_COLUMN_MAPPING
    from cloud.orchestrator import delivery_inputs as di
    from cloud.orchestrator.deliver import load_prepared_features
    from cloud.orchestrator.prepare import GcsPinnedReader

    client = storage.Client(project="feisty-flames-511718-d4")
    report = {"pins": {}}
    for name in ("prepare_status.json", "prepared_manifest.json", "prepare_plan.json"):
        bucket, blob_name = f"{PREFIX}/{name}"[5:].split("/", 1)
        blob = client.bucket(bucket).get_blob(blob_name)
        data = blob.download_as_bytes(if_generation_match=blob.generation)
        report["pins"][name] = {"uri": f"{PREFIX}/{name}", "generation": str(blob.generation),
                                "sha256": hashlib.sha256(data).hexdigest()}
        (args.out / name).parent.mkdir(parents=True, exist_ok=True)
        (args.out / name).write_bytes(data)
    manifest = json.loads((args.out / "prepared_manifest.json").read_text())
    status = json.loads((args.out / "prepare_status.json").read_text())
    report["status"] = status
    report["vintages"] = {f: v["provider_latest_completed_month"] for f, v in manifest["families"].items()}
    reader = GcsPinnedReader(client)
    fews = load_prepared_features(manifest, reader)["fewsnet"]
    S = args.staging
    comparisons = {}
    local_gosif = pd.read_csv(S / "sources/gosif_v3/fewsnet_gosif_v3_mean_2025.csv", dtype={"admin_code": str})
    local_evi = pd.read_csv(S / "sources/evi_202609/fewsnet_evi_2026-09.csv", dtype={"admin_code": str})
    pinned_old = S / "sources/remote/pinned-full-window-20261008c/features_fewsnet"
    for family, local, column, months in (("gosif_mean", local_gosif, "GPP_Mean__mean", None),
                                          ("evi", local_evi, "EVI__mean", ["2026-09"]),
                                          ("fldas", pd.read_csv(pinned_old / "fldas.csv", dtype={"admin_code": str}),
                                           "Tair_f_tavg__mean", ["2026-08"]),
                                          ("viirs", pd.read_csv(pinned_old / "viirs.csv", dtype={"admin_code": str}),
                                           "avg_rad__sum", ["2026-08"])):
        snap = fews[family]
        if months:
            local = local[local["month"].isin(months)]
        merged = snap.merge(local, on=["admin_code", "month"], suffixes=("_snapshot", "_local"))
        a, b = merged[f"{column}_snapshot"].to_numpy(float), merged[f"{column}_local"].to_numpy(float)
        both = ~np.isnan(a) & ~np.isnan(b)
        comparisons[family] = {"rows_compared": len(merged), "snapshot_rows": len(snap), "column": column,
                               "exact": int((a[both] == b[both]).sum()), "both_present": int(both.sum()),
                               "max_abs_diff": float(np.abs(a[both] - b[both]).max()) if both.any() else None,
                               "blank_mask_equal": bool((np.isnan(a) == np.isnan(b)).all())}
    report["snapshot_vs_independent"] = comparisons

    panel_path = S / "panel/v2/FEWSNET_versioned_panel_20261022.normalized-v1.csv"
    raw = pd.read_csv(panel_path, dtype={"FEWSNET_admin_code": str}, low_memory=False)
    base, overlay_report, extra = di.fewsnet_base_panel(raw, origin="2026-10", prepared_families=manifest["families"],
                                                        prepared_features=fews)
    report["overlay"] = overlay_report["remote_overlay"]
    raw["month_key"] = raw["date"].str[:7]
    keyed_raw = raw.set_index(["FEWSNET_admin_code", "month_key"])
    keyed_base = base.set_index([di.KEY, di.MONTH])
    survival = {}
    for family, columns in di.family_model_columns("fewsnet").items():
        vintage = manifest["families"][family]["provider_latest_completed_month"]
        for column in columns:
            months = sorted(m for m in raw["month_key"].unique() if "2025-01" <= m <= vintage)
            sub = raw[raw["month_key"].isin(months)]
            before = sub[column].to_numpy(float)
            after = keyed_base[column].reindex(pd.MultiIndex.from_arrays(
                [sub["FEWSNET_admin_code"].map(di.normalize_admin_code), sub["month_key"]])).to_numpy(float)
            present = ~np.isnan(before)
            lost = present & np.isnan(after)
            changed = present & ~np.isnan(after) & (np.abs(after - before) > 1e-9 * np.maximum(1, np.abs(before)))
            survival[column] = {"family": family, "months": [months[0], months[-1]] if months else None,
                                "panel_cells": int(present.sum()), "lost_after_overlay": int(lost.sum()),
                                "changed_after_overlay": int(changed.sum()),
                                "max_abs_change": float(np.abs(after[present & ~np.isnan(after)] -
                                                               before[present & ~np.isnan(after)]).max())
                                if (present & ~np.isnan(after)).any() else None,
                                "mapping": MODEL_COLUMN_MAPPING["fewsnet"][column]}
    report["post_overlay_survival_2025_01_through_vintage"] = survival
    (args.out / "snapshot_overlay_check.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({"vintages": report["vintages"], "comparisons": comparisons, "survival": survival}, default=str))


if __name__ == "__main__":
    main()
