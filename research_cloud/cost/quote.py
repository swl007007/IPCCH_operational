"""Itemized deployment quote for food-crisis-modeling-enso (us-central1 platform, global Gemini), from saved catalog SKUs.

Every line names its SKU (catalog file, array index, skuId - all verified against the saved record, with the
effective time), a quantity with its basis and a pool (``platform`` or ``training``, separate USD 100/month envelopes).
Quantities are in each SKU's base usage unit (the catalog ``unitPrice`` is per base unit, e.g. per operation, not per
display quantity). Prices are gross list prices: free tiers are NOT subtracted (they can aggregate at billing-account
level) and promotional credits are not assumed. Training lines are reservations computed with ``ledger.vertex_reservation`` (per
trial timeout + declared overhead, rounded up to 30 s). A quote is not a spending cap.

  python -m research_cloud.cost.quote --skus SKU_DIR --out QUOTE.json [--markdown QUOTE.md]
"""
import argparse
import json
import math
import os
import sys

from research_cloud.cost.ledger import vertex_reservation

GIB = 2 ** 30

# measured volumes (bytes) - sources named in VOLUMES_BASIS
VOLUMES = {"fews_roots": 76_949_755_782, "declared_inputs": 14_870_642_554, "mlflow_artifacts": 1_321_950_132,
           "packages": 12_582_279_472, "training_snapshots": 367_920_759}
VOLUMES_BASIS = {"fews_roots": "transfer-volume-supervisor.md: 27 roots, 136,776 files (metadata walk)",
                 "declared_inputs": "input-inventory.json: 121 files", "mlflow_artifacts": "snapshot r1 artifact tree, 3,573 files",
                 "packages": "packages/ at 223 packages, 15,885 files (du -sb, this checkpoint)",
                 "training_snapshots": "FEWS H4 2019-02 + IPCCH H3 feature snapshots (du -sb)"}


def sku(skus, file, index, sku_id, tier=None):
    """(unit price USD, description, effective time) of a saved catalog record, verified by skuId. ``tier``: the
    tier start amount to use (default: the first tier with a non-zero price, i.e. gross after any free tier)."""
    rec = json.load(open(os.path.join(skus, file)))[index]
    if rec["skuId"] != sku_id:
        raise ValueError(f"{file}[{index}] is {rec['skuId']}, not {sku_id}")
    info = rec["pricingInfo"][0]
    tiers = info["pricingExpression"]["tieredRates"]
    pick = next(t for t in tiers if (tier is None and (int(t["unitPrice"]["units"]) or t["unitPrice"]["nanos"]))
                or (tier is not None and t["startUsageAmount"] == tier))
    price = int(pick["unitPrice"]["units"]) + pick["unitPrice"]["nanos"] / 1e9
    return price, rec["description"], info["effectiveTime"], info["pricingExpression"]["usageUnit"]


# measured live GCS bytes after transfer and publication (ledger/actuals; supervisor reconciliation): 156,113 transfer
# objects + 15,477 publication copies (server-side copies of the packages into MLflow artifact paths)
LIVE = {"transfer_objects": 106_113_317_859, "publication_copies": 12_578_866_404}


def lines(skus):
    gib_total = sum(LIVE.values()) / GIB
    storage_gib = math.ceil(gib_total * 1.10)          # + 10% soft-delete / growth allowance
    out = []

    def add(pool, name, ref, qty, basis, one_time=False, scale=1.0):
        price, desc, eff, unit = sku(skus, *ref)
        out.append({"pool": pool, "item": name, "sku": {"file": ref[0], "index": ref[1], "id": ref[2], "description": desc,
                                                         "effective": eff, "unit": unit, "unit_price_usd": price},
                    "quantity": qty, "scale": scale, "usd": round(price * qty * scale, 6), "basis": basis,
                    "one_time": one_time})
    # Cloud SQL (Enterprise, PostgreSQL 16, zonal, db-g1-small; research + mlflow + mlflow_auth)
    add("platform", "Cloud SQL db-g1-small instance, 744 h", ("sql.json", 3383, "2A6B-45EC-D503"), 744, "always on, full month")
    add("platform", "Cloud SQL SSD 30 GiB", ("sql.json", 15396, "C18F-7FE0-0717"), 30,
        "measured 10.98 GiB data + WAL/temp allowances 13.65 GiB; 30 GiB leaves ~16 GiB headroom")
    add("platform", "Cloud SQL backups 30 GiB-month", ("sql.json", 5732, "46C8-DA82-DF18"), 30,
        "automated daily backups, 7 retained, point-in-time recovery (WAL archiving) OFF; one full (~11 GiB measured "
        "data) + incrementals of a mostly static research DB, reserved at ~2.7x measured data; reconcile with billed usage")
    add("platform", "Cloud SQL public IPv4 reservation, 744 h", ("sql.json", 3944, "3151-8F6A-75C1"), 744,
        "included conservatively; applicability to an attached instance IP unverified")
    add("platform", "Cloud SQL internet egress, input-import verification readback 16 GiB", ("sql.json", 2798, "238B-D94B-7243"),
        16, "one-time: the research-input import's every-cell COPY TO readback through the Auth Proxy to the workstation "
        "(~12.8 GiB CSV-equivalent + geometry/catalog reads); added before the import ran", one_time=True)
    # Cloud Run MLflow service (max 1 instance, min 0, 1 vCPU / 2 GiB, request-based)
    add("platform", "Cloud Run CPU, 60 active h x 1 vCPU", ("run.json", 229, "4856-B847-F1EB"), 60 * 3600, "research use estimate")
    add("platform", "Cloud Run memory, 60 active h x 2 GiB", ("run.json", 8, "02A2-9231-36A6"), 60 * 3600 * 2, "research use estimate")
    add("platform", "Cloud Run requests, 0.1 M", ("run.json", 149, "2DA5-55D3-E679"), 100_000, "gross (first 2 M are free tier)")
    add("platform", "Cloud Run internet egress 20 GiB", ("run.json", 646, "DDFD-AE42-E219"), 20,
        "recurring workload allowance: MLflow UI/API and proxied artifact/package downloads to the workstation")
    # GCS (regional standard, us-central1)
    add("platform", f"GCS standard storage {storage_gib} GiB-month", ("gcs.json", 1124, "E5F0-6A5D-7BAD"), storage_gib,
        f"measured live {gib_total:.2f} GiB: 156,113 transferred objects (FEWS roots, inputs, MLflow artifacts, packages, "
        "snapshots, jobs) + 15,477 publication copies (12.58 GB, packages copied into MLflow artifact paths) + 10% "
        "soft-delete/growth")
    add("platform", "GCS Class A, initial upload + publication 172k", ("gcs.json", 392, "4DBF-185F-A415"), 172_000,
        "one-time: 171,590 logical object writes (156,113 transfer objects + 15,477 publication copies, counted once)",
        one_time=True)
    add("platform", "GCS Class A, monthly 10k", ("gcs.json", 392, "4DBF-185F-A415"), 10_000, "operations")
    add("platform", "GCS Class B, monthly 100k", ("gcs.json", 596, "7870-010B-2763"), 100_000, "operations")
    add("platform", "GCS Class B, acceptance reads 400k", ("gcs.json", 596, "7870-010B-2763"), 400_000,
        "one-time (indicative; with the monthly 100k: 500k): upload reload + verify 312,226, publication verify 30,954, "
        "archive downloads 55,964, package downloads 15,477", one_time=True)
    scen, packages = 45_341_699_278 / GIB, VOLUMES["packages"] / GIB
    add("platform", f"GCS direct download, scen archive acceptance {math.ceil(scen)} GiB", ("gcs.json", 180, "22EB-AAE8-FBCD"),
        math.ceil(scen), f"one-time: every extant scen-b43ef6a-v1 material ({scen:.2f} GiB; the exception's source archive), "
        "authorized direct GCS download; no other root is re-downloaded", one_time=True)
    add("platform", "GCS direct download, AC8 inputs + confirm-onset archive 3 GiB", ("gcs.json", 180, "22EB-AAE8-FBCD"), 3,
        "one-time: AC8 clean-run gs:// input reads 2.34 GiB (6 objects, sizes from object metadata) + confirm-onset-v1 "
        "every extant byte 0.06 GiB", one_time=True)
    add("platform", f"Cloud Run egress, package acceptance via MLflow SDK {math.ceil(packages)} GiB",
        ("run.json", 646, "DDFD-AE42-E219"), math.ceil(packages),
        f"one-time: all retained packages ({packages:.2f} GiB) downloaded with authenticated MLflow SDK calls through the "
        "service's artifact proxy (the intended user path, incl. the largest-package service check); the pilot, trial, "
        "HPT and AC8 package downloads (0.11 GiB) fit in the rounding", one_time=True)
    add("platform", "Cloud Run CPU, package acceptance streaming 2 h", ("run.json", 229, "4856-B847-F1EB"), 2 * 3600,
        "one-time: proxy time to stream the package acceptance volume (conservative)", one_time=True)
    add("platform", "Cloud Run memory, package acceptance streaming 2 h x 2 GiB", ("run.json", 8, "02A2-9231-36A6"),
        2 * 3600 * 2, "one-time, as above", one_time=True)
    add("platform", "Artifact Registry pulls to the workstation 11 GiB", ("ar.json", 1, "108E-9EAE-92D9"), 11,
        "one-time crane pulls of the 5 images (digest verification; historical replay acceptance on the workstation): "
        "measured unpacked envs 5.54 GB + base layers, x2 for one rebuild", one_time=True)
    # images, builds, secrets, logging
    add("platform", "Artifact Registry storage 11 GiB-month", ("ar.json", 14, "8502-299A-ABAF"), 11,
        "7 digests now: the original 5 (service + 2 training + 2 historical replay) + service 4cc5d93b + training-ipcch "
        "6ad7f46c (train-entry); measured repository size 4.11 GB (3.82 GiB), allowance kept for later digests; "
        "Cloud Run/Vertex pulls are in-region")
    add("platform", "Cloud Build e2-standard-2, 120 min", ("build.json", 249, "A464-9020-6404"), 120,
        "measured: 7 successful builds 18.64 min + 1 failed ~1.93 min (20.5 min); allowance kept for rebuilds; source "
        "contexts ~4.5 MB staged in the build source bucket (2.5 MB live)")
    add("platform", "Secret Manager, 18 active versions (replica-months)", ("secret.json", 0, "7756-ADEF-84F4"), 18,
        "measured: 16 secrets, 18 ENABLED versions (13 initial, 2 corrected MLflow URI versions with version 1 kept, "
        "1 temporary migration admin, 2 assistant/guard); all assumed retained the full month (the temporary admin's "
        "versions are destroyed after acceptance: 17 steady); user-managed us-central1 replication")
    add("platform", "Secret Manager accesses 20k", ("secret.json", 1, "EBA7-264F-2D2C"), 20_000, "accesses")
    add("platform", "Logging ingestion 10 GiB", ("logging.json", 0, "143F-A1B0-E0BE"), 10, "gross (first 50 GiB free tier)")
    add("platform", "Logging retention 10 GiB-month", ("logging.json", 2, "F4AE-5A52-ACE3"), 10, "beyond default retention")
    # Gemini (global endpoint): the guard's hard monthly allocation at standard list prices
    inp, desc_i, eff_i, _ = sku(skus, "vertex.json", 1570, "2A35-AC68-14D6")
    outp, desc_o, eff_o, _ = sku(skus, "vertex.json", 5375, "90FD-DC5F-DC55")
    out.append({"pool": "platform", "item": "Gemini 3.8 Flash (global) assistant, guard allocation",
                "sku": {"input": {"id": "2A35-AC68-14D6", "usd_per_mtok": inp * 1e6, "effective": eff_i, "description": desc_i},
                        "output": {"id": "90FD-DC5F-DC55", "usd_per_mtok": outp * 1e6, "effective": eff_o, "description": desc_o}},
                "quantity": None, "usd": 10.0, "one_time": False,
                "basis": "the guard admits requests only within its USD 10 monthly allocation, reserving input + 2x max output "
                         "at gross list prices (output includes reasoning); promotional credits not assumed"})
    out.append({"pool": "platform", "item": "Contingency", "sku": None, "quantity": None, "usd": 10.0, "one_time": False,
                "basis": "unmetered allowances (network between services, retries, measurement error)"})
    # training (reservations; separate envelope)
    core, *_ = sku(skus, "vertex.json", 1576, "2A57-4214-1832")
    ram, *_ = sku(skus, "vertex.json", 8176, "DE93-D712-2AE4")
    machines = {"n1-standard-4": 4 * core + 15 * ram, "n1-highmem-4": 4 * core + 26 * ram}
    disk_hour = 0.000063014   # official displayed standard-PD hourly price (vertex-training-cost-supervisor.md)
    # the training jobs actually submitted (each reserved before its POST; reservations are estimates, not billed
    # spend). The two feature-snapshot jobs of earlier quotes were not run on Vertex (built on the workstation).
    jobs = [("FEWS single trial attempt 1 (failed: trainer lacked serviceusage), 1 job", "n1-standard-4", 1, 900),
            ("FEWS single trial attempt 2 (succeeded), 1 job", "n1-standard-4", 1, 900),
            ("IPCCH single trial (succeeded), 1 job", "n1-highmem-4", 1, 900),
            ("HPT smoke attempt 1: 2 serial trials (failed: /var/hypertune permission)", "n1-highmem-4", 2, 900),
            ("HPT diagnostic: /var/hypertune mount probe (cancelled)", "n1-standard-4", 1, 300),
            ("HPT smoke attempt 2: 2 serial trials (cancelled at the aggregate deadline)", "n1-highmem-4", 2, 900),
            ("HPT smoke attempt 3: 2 serial trials", "n1-highmem-4", 2, 900)]
    for name, machine, trials, timeout in jobs:
        r = vertex_reservation(machines[machine], trials, timeout, 600, 100, disk_hour)
        out.append({"pool": "training", "item": name, "sku": {"machine": machine, "usd_per_hour": machines[machine],
                    "core": "2A57-4214-1832", "ram": "DE93-D712-2AE4", "disk_usd_per_gib_hour": disk_hour},
                    "quantity": {"trials": trials, "timeout_s": timeout, "overhead_s": 600, "boot_disk_gib": 100,
                                 "billed_seconds_per_trial": r["billed_seconds_per_trial"]},
                    "usd": round(r["total_usd"], 6), "one_time": True,
                    "basis": "submitted job's reservation (an estimate; billed actual not yet known), held until provider "
                             "terminal status; disableRetries; 600 s declared startup/termination overhead (not a provider "
                             "bound); no separate management line (on-demand price)"})
    return out


def totals(items):
    t = {}
    for pool in ("platform", "training"):
        monthly = sum(i["usd"] for i in items if i["pool"] == pool and not i["one_time"])
        once = sum(i["usd"] for i in items if i["pool"] == pool and i["one_time"])
        t[pool] = {"monthly_usd": round(monthly, 2), "one_time_usd": round(once, 2), "first_month_usd": round(monthly + once, 2),
                   "envelope_usd": 100.0, "within_envelope": monthly + once <= 100.0}
    return t


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--skus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--markdown")
    args = ap.parse_args(argv)
    items = lines(args.skus)
    quote = {"project": "food-crisis-modeling-enso", "region": "us-central1 (Gemini: global endpoint)",
             "prices": "gross list prices, catalog effective 2026-10-15T07:00:00Z; no free tiers or credits subtracted",
             "volumes_bytes": VOLUMES, "volumes_basis": VOLUMES_BASIS, "live_gcs_bytes": LIVE, "items": items, "totals": totals(items)}
    with open(args.out, "w") as f:
        json.dump(quote, f, indent=1)
    if args.markdown:
        rows = ["| Pool | Item | SKU | Qty | USD | One-time | Basis |", "|---|---|---|---|---|---|---|"]
        for i in items:
            sku_id = (i["sku"] or {}).get("id") or ((i["sku"] or {}).get("machine") if i["sku"] else "-") or "in/out"
            rows.append(f"| {i['pool']} | {i['item']} | {sku_id} | {i['quantity'] if not isinstance(i['quantity'], dict) else ''} | "
                        f"{i['usd']:.4f} | {'yes' if i['one_time'] else ''} | {i['basis']} |")
        open(args.markdown, "w").write("\n".join(rows) + "\n")
    print(json.dumps(quote["totals"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
