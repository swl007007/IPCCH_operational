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


def lines(skus):
    gib_total = sum(VOLUMES.values()) / GIB
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
        "daily managed backups, short retention; conservatively the disk size")
    add("platform", "Cloud SQL public IPv4 reservation, 744 h", ("sql.json", 3944, "3151-8F6A-75C1"), 744,
        "included conservatively; applicability to an attached instance IP unverified")
    # Cloud Run MLflow service (max 1 instance, min 0, 1 vCPU / 2 GiB, request-based)
    add("platform", "Cloud Run CPU, 60 active h x 1 vCPU", ("run.json", 229, "4856-B847-F1EB"), 60 * 3600, "research use estimate")
    add("platform", "Cloud Run memory, 60 active h x 2 GiB", ("run.json", 8, "02A2-9231-36A6"), 60 * 3600 * 2, "research use estimate")
    add("platform", "Cloud Run requests, 0.1 M", ("run.json", 149, "2DA5-55D3-E679"), 100_000, "gross (first 2 M are free tier)")
    add("platform", "Cloud Run internet egress 20 GiB", ("run.json", 646, "DDFD-AE42-E219"), 20,
        "MLflow UI/API and proxied artifact downloads to the research workstation")
    # GCS (regional standard, us-central1)
    add("platform", f"GCS standard storage {storage_gib} GiB-month", ("gcs.json", 1124, "E5F0-6A5D-7BAD"), storage_gib,
        f"measured {gib_total:.1f} GiB (FEWS roots, inputs, MLflow artifacts, packages, snapshots) + 10% soft-delete/growth")
    add("platform", "GCS Class A, initial upload 170k objects", ("gcs.json", 392, "4DBF-185F-A415"), 170_000, "operations; month 1 only",
        one_time=True)
    add("platform", "GCS Class A, monthly 10k", ("gcs.json", 392, "4DBF-185F-A415"), 10_000, "operations")
    add("platform", "GCS Class B, monthly 100k", ("gcs.json", 596, "7870-010B-2763"), 100_000, "operations")
    add("platform", "GCS direct download 20 GiB", ("gcs.json", 180, "22EB-AAE8-FBCD"), 20,
        "large package/snapshot downloads (worldwide excl. Asia/Australia); in-region training reads are free")
    # images, builds, secrets, logging
    add("platform", "Artifact Registry storage 9 GiB-month", ("ar.json", 14, "8502-299A-ABAF"), 9,
        "service + 2 training images (~3.5 GB unpacked envs), up to 3 retained digests each; in-region pulls")
    add("platform", "Cloud Build e2-standard-2, 60 min", ("build.json", 249, "A464-9020-6404"), 60, "3 images x a few builds")
    add("platform", "Secret Manager, 10 replica-months", ("secret.json", 0, "7756-ADEF-84F4"), 10,
        "Flask secret, KEK, DB and identity credentials; user-managed us-central1 replication")
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
    jobs = [("FEWS feature snapshot (fews_features), 1 job", "n1-standard-4", 1, 1800),
            ("IPCCH feature snapshot (ipcch_features), 1 job", "n1-highmem-4", 1, 1800),
            ("FEWS single trial (fews_fourclass), 1 job", "n1-standard-4", 1, 900),
            ("IPCCH single trial (ipcch_quartet), 1 job", "n1-highmem-4", 1, 900),
            ("HPT smoke: 2 serial trials (ipcch_quartet), parallel 1", "n1-highmem-4", 2, 900)]
    for name, machine, trials, timeout in jobs:
        r = vertex_reservation(machines[machine], trials, timeout, 600, 100, disk_hour)
        out.append({"pool": "training", "item": name, "sku": {"machine": machine, "usd_per_hour": machines[machine],
                    "core": "2A57-4214-1832", "ram": "DE93-D712-2AE4", "disk_usd_per_gib_hour": disk_hour},
                    "quantity": {"trials": trials, "timeout_s": timeout, "overhead_s": 600, "boot_disk_gib": 100,
                                 "billed_seconds_per_trial": r["billed_seconds_per_trial"]},
                    "usd": round(r["total_usd"], 6), "one_time": True,
                    "basis": "reservation held until provider terminal status; disableRetries; 600 s declared startup/"
                             "termination overhead (not a provider bound); no separate management line (on-demand price)"})
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
             "volumes_bytes": VOLUMES, "volumes_basis": VOLUMES_BASIS, "items": items, "totals": totals(items)}
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
