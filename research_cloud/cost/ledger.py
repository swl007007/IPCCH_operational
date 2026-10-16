"""Separate-pool spend ledger with atomic admission for in-scope cloud operations (operator host, SQLite).

Two pools with their own monthly caps - ``platform`` and ``training`` (USD 100 each by default) - never draw on each
other. Every paid operation is admitted by ``reserve`` before it is submitted:

* admission is one ``BEGIN IMMEDIATE`` transaction: the pool's month total (settled actuals + every reservation not
  yet settled or released) plus the new amount must stay within the cap, else nothing is written;
* ``attach`` records the provider resource name once submission returns it;
* ``observe`` records provider states; only provider terminal states (``TERMINAL``) end a job. ``CANCELLING``, a
  cancel request, a local timeout or a lost connection are not terminal, so the reservation keeps counting;
* ``settle`` needs a terminal state and records the charged amount with its basis (billing export, or a declared
  duration estimate until billing data exists); the actual counts even when it exceeds the reservation;
* ``release`` is only for an admission whose submission never created a resource, confirmed by a provider lookup
  (``no_resource_evidence``); anything ambiguous stays reserved.

Every transition reads the deciding state and writes it (with its event) inside one ``BEGIN IMMEDIATE`` transaction
with a conditional ``UPDATE``, so a concurrent attach and release cannot both succeed. Caps, amounts and reservation
inputs must be finite and in range.

The ledger is an operator control and receipt trail, not a provider-side spending cap.

  python -m research_cloud.cost.ledger --db LEDGER.sqlite summary --month 2026-10
"""
import argparse
import contextlib
import json
import math
import sqlite3
import sys
import time

POOLS = {"platform": 100.0, "training": 100.0}
TERMINAL = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED",
            "JOB_STATE_PARTIALLY_SUCCEEDED"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS pools (pool TEXT PRIMARY KEY, monthly_cap_usd REAL NOT NULL);
CREATE TABLE IF NOT EXISTS operations (
  operation_id TEXT PRIMARY KEY, pool TEXT NOT NULL REFERENCES pools(pool), month TEXT NOT NULL,
  reserved_usd REAL NOT NULL, status TEXT NOT NULL CHECK (status IN ('reserved', 'settled', 'released')),
  provider_resource TEXT, provider_state TEXT, actual_usd REAL, actual_basis TEXT, detail TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (operation_id TEXT NOT NULL, at TEXT NOT NULL, event TEXT NOT NULL, data TEXT NOT NULL);
"""


class AdmissionRefused(Exception):
    pass


class LedgerError(Exception):
    pass


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def finite(value, name, minimum=0.0, strict=False):
    """A finite real >= minimum (> minimum when strict); bools and non-numbers are refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or value < minimum or (strict and value == minimum):
        raise LedgerError(f"{name} must be a finite number {'>' if strict else '>='} {minimum}, got {value!r}")
    return float(value)


def connect(path, pools=None, timeout=30):
    pools = pools or POOLS
    for pool, cap in pools.items():
        finite(cap, f"cap of {pool}", strict=True)
    conn = sqlite3.connect(path, isolation_level=None, timeout=timeout)
    conn.executescript(SCHEMA)
    for pool, cap in pools.items():
        conn.execute("INSERT OR IGNORE INTO pools VALUES (?, ?)", (pool, float(cap)))
        stored = conn.execute("SELECT monthly_cap_usd FROM pools WHERE pool = ?", (pool,)).fetchone()[0]
        if stored != float(cap):
            raise LedgerError(f"pool {pool} already has cap {stored}, not {cap}")
    return conn


@contextlib.contextmanager
def transaction(conn):
    """One exclusive write transaction: every read that decides a transition and its write happen inside it."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _event(conn, op, event, data):
    conn.execute("INSERT INTO events VALUES (?, ?, ?, ?)", (op, now(), event, json.dumps(data, sort_keys=True)))


def committed(conn, pool, month):
    """Settled actuals + open reservations for the pool and month."""
    row = conn.execute("SELECT COALESCE(SUM(CASE status WHEN 'settled' THEN actual_usd WHEN 'reserved' THEN reserved_usd "
                       "ELSE 0 END), 0) FROM operations WHERE pool = ? AND month = ?", (pool, month)).fetchone()
    return float(row[0])


def reserve(conn, pool, month, operation_id, amount_usd, detail):
    amount_usd = finite(amount_usd, "reservation", strict=True)
    with transaction(conn):
        cap = conn.execute("SELECT monthly_cap_usd FROM pools WHERE pool = ?", (pool,)).fetchone()
        if cap is None:
            raise LedgerError(f"unknown pool {pool}")
        if conn.execute("SELECT 1 FROM operations WHERE operation_id = ?", (operation_id,)).fetchone():
            raise LedgerError(f"operation {operation_id} already admitted")
        used = committed(conn, pool, month)
        if used + amount_usd > cap[0] + 1e-9:
            raise AdmissionRefused(f"{pool} {month}: committed {used:.6f} + {amount_usd:.6f} exceeds cap {cap[0]:.2f}")
        t = now()
        conn.execute("INSERT INTO operations VALUES (?, ?, ?, ?, 'reserved', NULL, NULL, NULL, NULL, ?, ?, ?)",
                     (operation_id, pool, month, amount_usd, json.dumps(detail, sort_keys=True), t, t))
        _event(conn, operation_id, "reserved", {"amount_usd": amount_usd, "committed_before": used, "cap": cap[0]})
    return used + amount_usd


def _get(conn, operation_id):
    row = conn.execute("SELECT status, provider_resource, provider_state FROM operations WHERE operation_id = ?",
                       (operation_id,)).fetchone()
    if row is None:
        raise LedgerError(f"unknown operation {operation_id}")
    return row


def attach(conn, operation_id, provider_resource):
    if not provider_resource:
        raise LedgerError("provider resource name required")
    with transaction(conn):
        status, existing, _ = _get(conn, operation_id)
        if status != "reserved" or (existing and existing != provider_resource):
            raise LedgerError(f"{operation_id}: cannot attach {provider_resource} (status {status}, resource {existing})")
        conn.execute("UPDATE operations SET provider_resource = ?, updated_at = ? "
                     "WHERE operation_id = ? AND status = 'reserved'", (provider_resource, now(), operation_id))
        _event(conn, operation_id, "attached", {"provider_resource": provider_resource})


def observe(conn, operation_id, provider_state, source):
    """Record a provider-reported state (source: the read command/receipt that returned it)."""
    with transaction(conn):
        status, resource, _ = _get(conn, operation_id)
        if status != "reserved" or not resource:
            raise LedgerError(f"{operation_id}: states are observed only for an attached open reservation")
        conn.execute("UPDATE operations SET provider_state = ?, updated_at = ? WHERE operation_id = ?",
                     (provider_state, now(), operation_id))
        _event(conn, operation_id, "observed", {"provider_state": provider_state, "source": source,
                                                "terminal": provider_state in TERMINAL})
    return provider_state in TERMINAL


def settle(conn, operation_id, actual_usd, basis):
    actual_usd = finite(actual_usd, "actual")
    if not basis:
        raise LedgerError("settlement basis required")
    with transaction(conn):
        status, _, state = _get(conn, operation_id)
        if status != "reserved":
            raise LedgerError(f"{operation_id}: already {status}")
        if state not in TERMINAL:
            raise LedgerError(f"{operation_id}: provider state {state} is not terminal; the reservation stays")
        conn.execute("UPDATE operations SET status = 'settled', actual_usd = ?, actual_basis = ?, updated_at = ? "
                     "WHERE operation_id = ? AND status = 'reserved'", (actual_usd, basis, now(), operation_id))
        _event(conn, operation_id, "settled", {"actual_usd": actual_usd, "basis": basis})


def release(conn, operation_id, no_resource_evidence):
    if not no_resource_evidence:
        raise LedgerError(f"{operation_id}: release needs a provider lookup showing no resource was created")
    with transaction(conn):
        status, resource, _ = _get(conn, operation_id)
        if status != "reserved" or resource:
            raise LedgerError(f"{operation_id}: only an admission without a provider resource can be released")
        conn.execute("UPDATE operations SET status = 'released', updated_at = ? "
                     "WHERE operation_id = ? AND status = 'reserved' AND provider_resource IS NULL", (now(), operation_id))
        _event(conn, operation_id, "released", {"no_resource_evidence": no_resource_evidence})


def summary(conn, month):
    out = {}
    for pool, cap in conn.execute("SELECT pool, monthly_cap_usd FROM pools ORDER BY pool"):
        rows = conn.execute("SELECT status, COUNT(*), COALESCE(SUM(reserved_usd), 0), COALESCE(SUM(actual_usd), 0) "
                            "FROM operations WHERE pool = ? AND month = ? GROUP BY status", (pool, month)).fetchall()
        by = {s: {"operations": n, "reserved_usd": r, "actual_usd": a} for s, n, r, a in rows}
        used = committed(conn, pool, month)
        out[pool] = {"cap_usd": cap, "committed_usd": used, "headroom_usd": cap - used, "by_status": by}
    return out


def vertex_reservation(rate_per_hour, trials, timeout_s, overhead_s, disk_gib, disk_rate_gib_hour):
    """Conservative CustomJob/HPT reservation: per trial (running timeout + declared startup/termination overhead),
    rounded up to 30-second billing increments, at the machine's on-demand rate, plus boot disk for the same time."""
    if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
        raise LedgerError(f"trials must be a positive integer, got {trials!r}")
    rate_per_hour = finite(rate_per_hour, "machine rate", strict=True)
    timeout_s = finite(timeout_s, "timeout", strict=True)
    overhead_s = finite(overhead_s, "overhead")
    disk_gib = finite(disk_gib, "disk GiB")
    disk_rate_gib_hour = finite(disk_rate_gib_hour, "disk rate")
    billed_s = math.ceil((timeout_s + overhead_s) / 30) * 30
    hours = trials * billed_s / 3600
    return {"trials": trials, "billed_seconds_per_trial": billed_s, "compute_usd": hours * rate_per_hour,
            "disk_usd": hours * disk_gib * disk_rate_gib_hour,
            "total_usd": hours * (rate_per_hour + disk_gib * disk_rate_gib_hour),
            "assumption": f"{overhead_s}s startup/termination overhead per trial is declared, not a provider bound"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summary")
    s.add_argument("--month", required=True)
    args = ap.parse_args(argv)
    conn = connect(args.db)
    print(json.dumps(summary(conn, args.month), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
