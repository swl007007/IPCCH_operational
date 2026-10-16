"""Import the declared tabular inputs into PostgreSQL as typed, queryable tables (rehearsal and capacity measurement).

For every inventory entry whose proposed storage is a Cloud SQL table (``input-inventory.json``):

1. The file is classified local (Dropbox placeholder check) and stream-hashed; it must equal the inventory's
   verified sha256 before anything is loaded.
2. Pass 1 infers one type per column over the whole file: ``bigint`` when every non-empty value is an integer
   literal within int64 (no sign or leading zeros: such columns, e.g. zero-padded IDs, stay text), ``double precision`` when every non-empty value parses as a float (correctly rounded on
   both sides, so values round-trip exactly), otherwise ``text``. Dates and sentinels such as ``0000-00`` stay text;
   nothing is coerced, deduplicated, dropped or filled.
3. Pass 2 COPYs the rows with ``_source_row`` (1-based data row number). A row with fewer fields than the header
   (e.g. a stray trailing export artifact) is not typed or dropped: it is kept verbatim, with its source row number,
   in ``<table>__irregular_rows`` and reported. A row with more fields fails the import. Empty fields: ``''`` in text columns,
   NULL in numeric columns (recorded per column). Header names are kept verbatim as quoted identifiers when they fit
   PostgreSQL's 63-byte limit; longer ones get ``<50-byte prefix>__<sha8>`` and every table's verbatim headers,
   positions, SQL names and types are recorded in ``public._column_catalog``. A repeated or empty header name
   fails the import rather than being renamed.
4. Checks: row count equals the data rows read; for declared key columns (``keys.jsonl`` profile) the duplicate and
   null/empty key counts are recomputed in SQL and compared with the profile; a sample of rows is read back and
   compared value-by-value with the source parse.

The report records table, column types, rows, bytes (``pg_total_relation_size``) and the checks.

  python -m research_cloud.sqlimport.load_inputs --inventory input-inventory.json --keys keys.jsonl
      --dsn "host=... dbname=research" --report REPORT.json [--only ID ...]
"""
import argparse
import contextlib
import csv
import hashlib
import io
import json
import math
import re
import sys
import time

import numpy as np
import pandas as pd

from research_cloud.packages.common import ensure_local

csv.field_size_limit(sys.maxsize)
INT_RE = re.compile(r"[+-]?\d+\Z")
CHUNK = 50_000
SAMPLE = 200


class ImportError_(Exception):
    pass


def table_name(entry):
    base = re.sub(r"[^a-z0-9_]+", "_", entry["id"].split(".", 1)[-1].lower()).strip("_")
    return base[:55] or "t"


def ident(name):
    return '"' + name.replace('"', '""') + '"'


def sql_names(header):
    """PostgreSQL truncates identifiers at 63 bytes; longer headers get a deterministic short name (prefix + sha8).
    The verbatim header is kept in the column catalog."""
    out = []
    for name in header:
        if len(name.encode()) <= 63:
            out.append(name)
        else:
            digest = hashlib.sha256(name.encode()).hexdigest()[:8]
            prefix = name.encode()[:50].decode("utf-8", "ignore")
            out.append(f"{prefix}__{digest}")
    if len(set(out)) != len(out):
        raise ImportError_("column names collide after the 63-byte mapping")
    return out


def sha256_stream(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def read_header(path):
    """The header exactly as written (csv module; a UTF-8 byte-order mark is not part of the first name)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f))


def infer_types(path):
    """One type per column over every row (pandas C parser, strings only, header taken verbatim)."""
    header = read_header(path)
    if len(set(header)) != len(header) or "" in header:
        raise ImportError_(f"{path}: repeated or empty header names")
    kinds, rows, short = {c: "bigint" for c in header}, 0, 0
    for chunk in pd.read_csv(path, dtype=str, keep_default_na=False, chunksize=CHUNK, encoding="utf-8-sig",
                             header=0, names=header):
        rows += len(chunk)
        irregular = chunk[header[-1]].isna()   # fewer fields than the header: kept aside verbatim, not typed
        short += int(irregular.sum())
        chunk = chunk[~irregular]
        for c in header:
            if kinds[c] == "text":
                continue
            v = chunk[c]
            v = v[v != ""]
            if v.empty:
                continue
            if v.str.match(r"\+|-?0\d").any():   # sign or leading zeros: typing would lose the verbatim form (IDs stay text)
                kinds[c] = "text"
                continue
            if kinds[c] == "bigint":
                ok = v.str.fullmatch(r"-?\d+")
                if ok.all() and v.str.lstrip("-").str.len().max() <= 18:
                    continue
                kinds[c] = "double precision"
            num = pd.to_numeric(v, errors="coerce")
            if num.isna().any() or not np.isfinite(num.to_numpy(dtype=np.float64)).all():
                kinds[c] = "text"
    return header, kinds, rows, short


def copy_rows(cur, table, path, header, kinds):
    """Stream the file into COPY with a 1-based source row number; returns rows and per-column empty counts."""
    empties, irregular = {c: 0 for c in header}, []
    text_cols = [c for c in header if kinds[c] == "text"]
    sql = dict(zip(header, sql_names(header)))
    cols = ", ".join(["_source_row"] + [ident(sql[c]) for c in header])
    opts = "FORMAT csv, NULL ''" + (", FORCE_NOT_NULL (" + ", ".join(ident(sql[c]) for c in text_cols) + ")" if text_cols else "")
    total = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        if next(reader) != header:
            raise ImportError_("header differs between passes")
        while True:
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            n = 0
            for row in reader:
                total_row = total + n + 1
                if len(row) < len(header):   # kept verbatim in the sidecar table, never dropped
                    irregular.append((total_row, json.dumps(row)))
                    n += 1
                    if n == CHUNK:
                        break
                    continue
                if len(row) > len(header):
                    raise ImportError_(f"row {total_row} has {len(row)} fields, header has {len(header)}")
                for c, value in zip(header, row):
                    if value == "":
                        empties[c] += 1
                w.writerow([total_row] + row)
                n += 1
                if n == CHUNK:
                    break
            if n == 0:
                break
            buf.seek(0)
            cur.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH ({opts})", buf)
            total += n
    return total, empties, irregular


def sample_check(cur, table, path, header, kinds, rows, skip=()):
    """Compare SAMPLE rows read back from SQL with the source parse (rows kept in the sidecar are skipped)."""
    if rows == 0:
        return {"rows": 0, "mismatches": 0}
    picks = sorted(set(np.linspace(1, rows, num=min(SAMPLE, rows), dtype=np.int64).tolist()) - set(skip))
    want = set(picks)
    source = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)
        for i, row in enumerate(reader, 1):
            if i in want:
                source[i] = row
    cur.execute(f"SELECT * FROM {table} WHERE _source_row = ANY(%s) ORDER BY _source_row", (picks,))
    fetched = cur.fetchall()
    mismatches = [] if len(fetched) == len(picks) else [{"error": f"{len(picks) - len(fetched)} sampled rows absent"}]
    for rec in fetched:
        i, values = rec[0], rec[1:]
        for c, got, raw in zip(header, values, source[i]):
            if kinds[c] == "text":
                ok = got == raw
            elif raw == "":
                ok = got is None
            elif kinds[c] == "bigint":
                ok = got == int(raw)
            else:
                ok = got == float(raw) or (math.isnan(got) and math.isnan(float(raw)))
            if not ok:
                mismatches.append({"row": i, "column": c, "source": raw, "sql": str(got)})
    return {"rows": len(picks), "mismatches": len(mismatches), "examples": mismatches[:5]}


def key_check(cur, table, profile, header):
    cols = profile.get("key_columns") or []
    if not cols:
        return None
    sql = dict(zip(header, sql_names(header)))
    k = ", ".join(ident(sql[c]) for c in cols)
    cur.execute(f"SELECT count(*) - count(DISTINCT ({k})) FROM {table}")
    dup = cur.fetchone()[0]
    nulls = " OR ".join(f"{ident(sql[c])} IS NULL OR {ident(sql[c])}::text = ''" for c in cols)
    cur.execute(f"SELECT count(*) FROM {table} WHERE {nulls}")
    null = cur.fetchone()[0]
    return {"key_columns": cols, "sql_duplicate_rows": dup, "profile_duplicates": profile.get("key_duplicates_full"),
            "sql_null_or_empty": null, "profile_null_or_empty": profile.get("key_null_or_empty"),
            "agrees_with_profile": dup == profile.get("key_duplicates_full") and null == profile.get("key_null_or_empty")}


def load_one(conn, entry, schema, profile):
    path = entry["path"]
    t0 = time.time()
    ensure_local([path])
    if sha256_stream(path) != entry["actual_sha256"]:
        raise ImportError_(f"{path}: bytes differ from the inventory sha256")
    if entry.get("recorded_sha256") is not None and entry.get("sha_match") is not True:
        raise ImportError_(f"{path}: inventory sha differs from its recorded sha256")
    basis = "recorded sha256 matched" if entry.get("recorded_sha256") else "fresh inventory hash only (no recorded sha256)"
    header, kinds, rows, short = infer_types(path)
    table = f"{ident(schema)}.{ident(table_name(entry))}"
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {ident(schema)}")
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        names = sql_names(header)
        cur.execute(f"CREATE TABLE {table} (_source_row bigint PRIMARY KEY, "
                    + ", ".join(f"{ident(n)} {kinds[c]}" for c, n in zip(header, names)) + ")")
        cur.execute("CREATE TABLE IF NOT EXISTS public._column_catalog (table_name text, position int, source_header text, "
                    "sql_column text, sql_type text, PRIMARY KEY (table_name, position))")
        cur.execute("DELETE FROM public._column_catalog WHERE table_name = %s", (f"{schema}.{table_name(entry)}",))
        cur.executemany("INSERT INTO public._column_catalog VALUES (%s, %s, %s, %s, %s)",
                        [(f"{schema}.{table_name(entry)}", i, c, n, kinds[c]) for i, (c, n) in enumerate(zip(header, names))])
        side = f"{ident(schema)}.{ident(table_name(entry) + '__irregular_rows')}"
        cur.execute(f"DROP TABLE IF EXISTS {side}")
        loaded, empties, irregular = copy_rows(cur, table, path, header, kinds)
        if loaded != rows or len(irregular) != short:
            raise ImportError_(f"{path}: read {loaded} rows ({len(irregular)} short), pass 1 read {rows} ({short} short)")
        if irregular:
            cur.execute(f"CREATE TABLE {side} (_source_row bigint PRIMARY KEY, fields_json text NOT NULL)")
            cur.executemany(f"INSERT INTO {side} VALUES (%s, %s)", irregular)
        cur.execute(f"ANALYZE {table}")
        cur.execute("SELECT pg_total_relation_size(%s::regclass), pg_relation_size(%s::regclass)", (table, table))
        total_bytes, heap_bytes = cur.fetchone()
        sample = sample_check(cur, table, path, header, kinds, rows, skip=[r for r, _ in irregular])
        keys = key_check(cur, table, profile, header) if profile else None
    conn.commit()
    types = {k: sum(1 for v in kinds.values() if v == k) for k in ("bigint", "double precision", "text")}
    return {"id": entry["id"], "path": path, "sha256": entry["actual_sha256"], "identity_basis": basis,
            "source_bytes": entry["actual_bytes"],
            "table": f"{schema}.{table_name(entry)}", "columns": len(header), "column_types": types,
            "renamed_long_headers": sum(1 for c, n in zip(header, sql_names(header)) if c != n),
            "rows": rows, "typed_rows": rows - len(irregular),
            "irregular_rows": {"table": f"{schema}.{table_name(entry)}__irregular_rows", "rows": [r for r, _ in irregular][:20],
                               "count": len(irregular), "examples": [json.loads(f) for _, f in irregular][:3]} if irregular else None,
            "total_bytes": total_bytes, "heap_bytes": heap_bytes,
            "empty_to_null_numeric": {c: n for c, n in empties.items() if n and kinds[c] != "text"},
            "sample_readback": sample, "keys": keys, "seconds": round(time.time() - t0, 1),
            "passed": sample["mismatches"] == 0 and (keys is None or keys["agrees_with_profile"])}


def main():
    import psycopg2
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--keys", required=True)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args()
    inv = json.load(open(args.inventory))
    entries = {}
    for ns, block in inv["namespaces"].items():
        for f in block["files"]:
            if isinstance(f, dict) and str(f.get("proposed_storage", "")).startswith("Cloud SQL table") and f.get("file_type") == "csv":
                entries.setdefault(f["path"], (ns, f))
    profiles = {}
    for line in open(args.keys):
        p = json.loads(line)
        profiles[p["path"]] = p
    results = []
    with contextlib.closing(psycopg2.connect(args.dsn)) as conn:
        for path, (ns, entry) in sorted(entries.items(), key=lambda x: x[1][1]["actual_bytes"]):
            if args.only and entry["id"] not in args.only:
                continue
            try:
                r = load_one(conn, entry, ns, profiles.get(path))
            except Exception as e:   # recorded, never skipped silently
                conn.rollback()
                r = {"id": entry["id"], "path": path, "passed": False, "error": f"{type(e).__name__}: {e}"[:500]}
            results.append(r)
            print(json.dumps({k: r.get(k) for k in ("id", "rows", "columns", "total_bytes", "seconds", "passed", "error")}), flush=True)
            json.dump({"results": results}, open(args.report, "w"), indent=1, default=str)
        with conn.cursor() as cur:
            cur.execute("SELECT pg_database_size(current_database())")
            db_bytes = cur.fetchone()[0]
    report = {"results": results, "tables": len(results), "passed": sum(bool(r.get("passed")) for r in results),
              "database_bytes": db_bytes, "source_bytes": sum(r.get("source_bytes") or 0 for r in results)}
    json.dump(report, open(args.report, "w"), indent=1, default=str)
    print(json.dumps({k: report[k] for k in ("tables", "passed", "database_bytes", "source_bytes")}))


if __name__ == "__main__":
    main()
