"""Import the declared tabular inputs into PostgreSQL as typed, queryable tables (rehearsal and capacity measurement).

For every inventory entry whose proposed storage is a Cloud SQL table (``input-inventory.json``):

0. Preflight over the whole inventory before any DDL: every table and side-table name (``<name>`` and
   ``<name>__irregular_rows``) is a readable prefix plus ``_<sha8 of the entry id>``, at most 63 bytes including the side
   suffix, and must be unique; the import refuses to start otherwise.
1. The file is classified local (Dropbox placeholder check) and stream-hashed; it must equal the inventory sha256.
2. Pass 1 infers one type per column over the whole file:
   * identifier columns (``area_id``/``admin_code``/``FEWSNET_admin_code``, ``*_id``, ``*_code``, ``fid`` and declared
     key columns other than dates) stay ``text``: area IDs remain strings;
   * ``bigint`` when every non-empty value is an integer literal of at most 18 digits without sign or leading zeros;
     longer integer literals never degrade through float - the column stays ``text``;
   * ``double precision`` when every non-empty value parses as a finite float and every integer-literal value is
     within 2**53; otherwise ``text``. Dates and sentinels such as ``0000-00`` stay text.
3. Pass 2 COPYs the rows with ``_source_row`` (1-based data row number). Empty fields: ``''`` in text columns, NULL in
   numeric columns (recorded). A row with fewer fields than the header (found by an exact csv-module pre-scan) is kept
   verbatim in the side table; a row with more fields fails. Headers longer than 63 bytes get ``<50-byte prefix>__<sha8>``; ``public._column_catalog`` keeps
   every verbatim header, position, SQL name and type.
4. Verification in the same transaction, before COMMIT: row counts; a streaming comparison of every cell (the source
   re-parsed with the same typing against the table read back with ``COPY ... TO STDOUT`` ordered by ``_source_row``;
   floats exactly, NULL positions exactly, text exactly); declared key duplicate/null counts against the ``keys.jsonl``
   profile. Any failure rolls the table back, so nothing unverified is committed.

The report is keyed by inventory id. ``--only`` re-imports a subset and merges into the existing report; every run
reconciles the full expected table set (verified and present / failed / not imported).

  python -m research_cloud.sqlimport.load_inputs --inventory input-inventory.json --keys keys.jsonl
      --dsn "host=... dbname=research" --report REPORT.json [--only ID ...]
"""
import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
import re
import sys
import time

import numpy as np
import pandas as pd

from research_cloud.packages.common import ensure_local

csv.field_size_limit(sys.maxsize)
CHUNK = 50_000
SIDE = "__irregular_rows"
MAX_IDENT = 63
ID_COLUMN = re.compile(r"(^|_)(id|code)$|^fid$|admin_code", re.IGNORECASE)
DATE_COLUMN = re.compile(r"date|month|year|period", re.IGNORECASE)
EXACT_FLOAT_INT = 2 ** 53


class ImportFailure(Exception):
    pass


def ident(name):
    return '"' + name.replace('"', '""') + '"'


def table_name(entry_id):
    """Readable prefix + sha8 of the entry id, leaving room for the side-table suffix within 63 bytes."""
    digest = hashlib.sha256(entry_id.encode()).hexdigest()[:8]
    base = re.sub(r"[^a-z0-9_]+", "_", entry_id.split(".", 1)[-1].lower()).strip("_") or "t"
    room = MAX_IDENT - len(SIDE) - 1 - len(digest)
    return f"{base[:room].rstrip('_')}_{digest}"


def plan_names(entries):
    """{entry id: (schema, table)}; refuses duplicate or over-long names before any DDL."""
    names = {e["id"]: (ns, table_name(e["id"])) for ns, e in entries}
    full = [f"{s}.{t}" for s, t in names.values()] + [f"{s}.{t}{SIDE}" for s, t in names.values()]
    too_long = [t for _, t in names.values() if len((t + SIDE).encode()) > MAX_IDENT]
    if len(set(full)) != len(full) or too_long or len(names) != len(entries):
        raise ImportFailure(f"table names are not unique within {MAX_IDENT} bytes: {too_long[:3]}")
    return names


def sql_names(header):
    out = []
    for name in header:
        if len(name.encode()) <= MAX_IDENT:
            out.append(name)
        else:
            out.append(f"{name.encode()[:50].decode('utf-8', 'ignore')}__{hashlib.sha256(name.encode()).hexdigest()[:8]}")
    if len(set(out)) != len(out):
        raise ImportFailure("column names collide after the 63-byte mapping")
    return out


def sha256_stream(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def read_header(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f))


def short_rows(path, header):
    """1-based source row numbers with fewer fields than the header (csv module, exact); more fields fail."""
    out = set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)
        for i, row in enumerate(reader, 1):
            if len(row) < len(header):
                out.add(i)
            elif len(row) > len(header):
                raise ImportFailure(f"row {i} has {len(row)} fields, header has {len(header)}")
    return out


def chunks(path, header, short):
    """Pandas string chunks with the verbatim header, and a mask of the short rows (from short_rows)."""
    base = 0
    for chunk in pd.read_csv(path, dtype=str, keep_default_na=False, chunksize=CHUNK, encoding="utf-8-sig",
                             header=0, names=header):
        rows = np.arange(base + 1, base + len(chunk) + 1)
        base += len(chunk)
        yield chunk, np.isin(rows, list(short)) if short else np.zeros(len(chunk), dtype=bool)


def is_identifier(name, key_columns):
    return bool(ID_COLUMN.search(name)) or (name in key_columns and not DATE_COLUMN.search(name))


def infer_types(path, header, key_columns, short_set):
    kinds = {c: ("text" if is_identifier(c, key_columns) else "bigint") for c in header}
    rows = short_total = 0
    for chunk, short in chunks(path, header, short_set):
        rows += len(chunk)
        short_total += int(short.sum())
        chunk = chunk[~short]
        for c in header:
            if kinds[c] == "text":
                continue
            v = chunk[c]
            v = v[v != ""]
            if v.empty:
                continue
            if v.str.match(r"\+|-?0\d").any():          # sign or leading zeros: keep verbatim
                kinds[c] = "text"
                continue
            ints = v.str.fullmatch(r"-?\d+")
            if kinds[c] == "bigint":
                if ints.all():
                    if v.str.lstrip("-").str.len().max() > 18:
                        kinds[c] = "text"                 # never degrade a long integer through float
                    continue
                kinds[c] = "double precision"
            num = pd.to_numeric(v, errors="coerce")
            if num.isna().any() or not np.isfinite(num.to_numpy(dtype=np.float64)).all():
                kinds[c] = "text"
            elif ints.any() and (v[ints].str.lstrip("-").str.len().max() > 15 or (num[ints].abs() > EXACT_FLOAT_INT).any()):
                kinds[c] = "text"                         # integer literal not exactly representable as float
    return kinds, rows, short_total


def typed(frame, header, kinds):
    """Strings -> the values the table must hold (float64 / Int64 / str; '' -> NA in numeric columns)."""
    out = {}
    for c in header:
        s = frame[c]
        if kinds[c] == "text":
            out[c] = s.astype(str)
        else:
            num = pd.to_numeric(s.mask(s == ""), errors="raise")
            out[c] = num.astype("Int64") if kinds[c] == "bigint" else num.astype("float64")
    return out


def copy_rows(cur, table, path, header, kinds, names):
    empties, irregular = {c: 0 for c in header}, []
    text_cols = [names[i] for i, c in enumerate(header) if kinds[c] == "text"]
    cols = ", ".join(["_source_row"] + [ident(n) for n in names])
    opts = "FORMAT csv, NULL ''" + (", FORCE_NOT_NULL (" + ", ".join(ident(n) for n in text_cols) + ")" if text_cols else "")
    total = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        if next(reader) != header:
            raise ImportFailure("header differs between passes")
        while True:
            buf, n = io.StringIO(), 0
            w = csv.writer(buf, lineterminator="\n")
            for row in reader:
                n += 1
                src = total + n
                if len(row) < len(header):
                    irregular.append((src, json.dumps(row)))
                elif len(row) > len(header):
                    raise ImportFailure(f"row {src} has {len(row)} fields, header has {len(header)}")
                else:
                    for c, value in zip(header, row):
                        if value == "":
                            empties[c] += 1
                    w.writerow([src] + row)
                if n == CHUNK:
                    break
            if n == 0:
                break
            buf.seek(0)
            cur.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH ({opts})", buf)
            total += n
    return total, empties, irregular


def compare_table(cur, table, path, header, kinds, names, short_set):
    """Every cell of the table against the source, in _source_row order (table read back via COPY TO STDOUT)."""
    tmp = io.StringIO()
    cur.copy_expert(f"COPY (SELECT _source_row, {', '.join(ident(n) for n in names)} FROM {table} ORDER BY _source_row) "
                    "TO STDOUT WITH (FORMAT csv, NULL '\\N')", tmp)
    tmp.seek(0)
    back_iter = pd.read_csv(tmp, dtype=str, keep_default_na=False, header=None, names=["_source_row"] + header,
                            chunksize=CHUNK)
    pending, cells, mismatches, base = None, 0, [], 0
    for chunk, short in chunks(path, header, short_set):
        src_rows = np.arange(base + 1, base + len(chunk) + 1)[~short]
        base += len(chunk)
        regular = chunk[~short].reset_index(drop=True)
        parts, need = [], len(regular)
        while need:
            if pending is None or pending.empty:
                pending = next(back_iter)
            parts.append(pending.iloc[:need])
            need -= len(parts[-1])
            pending = pending.iloc[len(parts[-1]):]
        if not parts:
            continue
        got = pd.concat(parts, ignore_index=True)
        if not np.array_equal(got["_source_row"].astype(np.int64).to_numpy(), src_rows):
            raise ImportFailure("table rows are not the source rows in order")
        want = typed(regular, header, kinds)
        for c in header:
            g = got[c]
            if kinds[c] == "text":
                bad = (g == "\\N").to_numpy() | (want[c].to_numpy() != g.to_numpy())
            else:
                null = (g == "\\N").to_numpy()
                back = pd.to_numeric(g.mask(null), errors="raise")
                w = want[c]
                if kinds[c] == "bigint":
                    bad = (w.isna().to_numpy() != null) | (~null & (w.fillna(0).to_numpy() != back.fillna(0).astype("int64").to_numpy()))
                else:
                    wv, bv = w.to_numpy(dtype=np.float64), back.to_numpy(dtype=np.float64)
                    bad = (np.isnan(wv) != null) | (~null & (wv != bv))
            cells += len(g)
            if bad.any():
                mismatches.append({"column": c, "count": int(bad.sum()), "first_source_row": int(src_rows[np.flatnonzero(bad)[0]])})
    leftover = (0 if pending is None else len(pending)) + sum(len(x) for x in back_iter)
    if leftover:
        raise ImportFailure(f"{leftover} table rows have no source row")
    return {"cells_compared": cells, "mismatched_columns": mismatches}


def key_check(cur, table, profile, header, names):
    cols = profile.get("key_columns") or []
    if not cols:
        return None
    sql = dict(zip(header, names))
    k = ", ".join(ident(sql[c]) for c in cols)
    cur.execute(f"SELECT count(*) - count(DISTINCT ({k})) FROM {table}")
    dup = cur.fetchone()[0]
    nulls = " OR ".join(f"{ident(sql[c])} IS NULL OR {ident(sql[c])}::text = ''" for c in cols)
    cur.execute(f"SELECT count(*) FROM {table} WHERE {nulls}")
    null = cur.fetchone()[0]
    return {"key_columns": cols, "sql_duplicate_rows": dup, "profile_duplicates": profile.get("key_duplicates_full"),
            "sql_null_or_empty": null, "profile_null_or_empty": profile.get("key_null_or_empty"),
            "agrees_with_profile": dup == profile.get("key_duplicates_full") and null == profile.get("key_null_or_empty")}


def load_one(conn, entry, schema, tname, profile):
    path = entry["path"]
    t0 = time.time()
    ensure_local([path])
    if sha256_stream(path) != entry["actual_sha256"]:
        raise ImportFailure("bytes differ from the inventory sha256")
    if entry.get("recorded_sha256") is not None and entry.get("sha_match") is not True:
        raise ImportFailure("inventory sha differs from its recorded sha256")
    header = read_header(path)
    if len(set(header)) != len(header) or "" in header:
        raise ImportFailure("repeated or empty header names")
    key_columns = set((profile or {}).get("key_columns") or [])
    short_set = short_rows(path, header)
    kinds, rows, short = infer_types(path, header, key_columns, short_set)
    names = sql_names(header)
    table, side, qualified = f"{ident(schema)}.{ident(tname)}", f"{ident(schema)}.{ident(tname + SIDE)}", f"{schema}.{tname}"
    with conn.cursor() as cur:   # one transaction: committed only after every check passes
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {ident(schema)}")
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(f"DROP TABLE IF EXISTS {side}")
        cur.execute(f"CREATE TABLE {table} (_source_row bigint PRIMARY KEY, "
                    + ", ".join(f"{ident(n)} {kinds[c]}" for c, n in zip(header, names)) + ")")
        cur.execute("CREATE TABLE IF NOT EXISTS public._column_catalog (table_name text, position int, source_header text, "
                    "sql_column text, sql_type text, PRIMARY KEY (table_name, position))")
        cur.execute("DELETE FROM public._column_catalog WHERE table_name = %s", (qualified,))
        cur.executemany("INSERT INTO public._column_catalog VALUES (%s, %s, %s, %s, %s)",
                        [(qualified, i, c, n, kinds[c]) for i, (c, n) in enumerate(zip(header, names))])
        loaded, empties, irregular = copy_rows(cur, table, path, header, kinds, names)
        if loaded != rows or len(irregular) != short or {r for r, _ in irregular} != short_set:
            raise ImportFailure(f"read {loaded} rows ({len(irregular)} short); pass 1 read {rows} ({short} short)")
        if irregular:
            cur.execute(f"CREATE TABLE {side} (_source_row bigint PRIMARY KEY, fields_json text NOT NULL)")
            cur.executemany(f"INSERT INTO {side} VALUES (%s, %s)", irregular)
        cur.execute(f"SELECT count(*) FROM {table}")
        if cur.fetchone()[0] != rows - len(irregular):
            raise ImportFailure("table row count differs from the regular source rows")
        comparison = compare_table(cur, table, path, header, kinds, names, short_set)
        if comparison["mismatched_columns"]:
            raise ImportFailure(f"cell comparison failed: {comparison['mismatched_columns'][:3]}")
        keys = key_check(cur, table, profile, header, names) if profile else None
        if keys is not None and not keys["agrees_with_profile"]:
            raise ImportFailure(f"key profile disagrees: {keys}")
        cur.execute(f"ANALYZE {table}")
        cur.execute("SELECT pg_total_relation_size(%s::regclass), pg_relation_size(%s::regclass)", (table, table))
        total_bytes, heap_bytes = cur.fetchone()
    conn.commit()
    types = {k: sum(1 for v in kinds.values() if v == k) for k in ("bigint", "double precision", "text")}
    return {"id": entry["id"], "path": path, "sha256": entry["actual_sha256"],
            "identity_basis": "recorded sha256 matched" if entry.get("recorded_sha256") else "fresh inventory hash only",
            "source_bytes": entry["actual_bytes"], "table": qualified, "columns": len(header), "column_types": types,
            "identifier_text_columns": sorted(c for c in header if is_identifier(c, key_columns)),
            "renamed_long_headers": sum(1 for c, n in zip(header, names) if c != n),
            "rows": rows, "typed_rows": rows - len(irregular),
            "irregular_rows": {"table": qualified + SIDE, "count": len(irregular), "rows": [r for r, _ in irregular][:20],
                               "examples": [json.loads(f) for _, f in irregular][:3]} if irregular else None,
            "total_bytes": total_bytes, "heap_bytes": heap_bytes,
            "empty_to_null_numeric": {c: n for c, n in empties.items() if n and kinds[c] != "text"},
            "cell_comparison": comparison, "keys": keys, "seconds": round(time.time() - t0, 1), "status": "verified"}


def expected_entries(inventory):
    out = {}
    for ns, block in inventory["namespaces"].items():
        for f in block["files"]:
            if isinstance(f, dict) and str(f.get("proposed_storage", "")).startswith("Cloud SQL table") and f.get("file_type") == "csv":
                out.setdefault(f["path"], (ns, f))
    return list(out.values())


def reconcile(conn, entries, names, results):
    with conn.cursor() as cur:
        present = {}
        for ns, entry in entries:
            schema, tname = names[entry["id"]]
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"{ident(schema)}.{ident(tname)}",))
            present[entry["id"]] = cur.fetchone()[0]
        cur.execute("SELECT pg_database_size(current_database())")
        db_bytes = cur.fetchone()[0]
    ids = [e["id"] for _, e in entries]
    rec = {"expected": len(ids),
           "verified": sorted(i for i in ids if results.get(i, {}).get("status") == "verified" and present[i]),
           "failed": sorted(i for i in ids if results.get(i, {}).get("status") == "failed"),
           "not_imported": sorted(i for i in ids if i not in results),
           "verified_but_table_absent": sorted(i for i in ids if results.get(i, {}).get("status") == "verified" and not present[i])}
    return rec, db_bytes


def main(argv=None):
    import psycopg2
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--keys", required=True)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args(argv)
    entries = expected_entries(json.load(open(args.inventory)))
    names = plan_names(entries)   # whole-inventory preflight before any DDL
    profiles = {}
    for line in open(args.keys):
        p = json.loads(line)
        profiles[p["path"]] = p
    previous = json.load(open(args.report)) if os.path.exists(args.report) else {}
    results = previous.get("results") if isinstance(previous.get("results"), dict) else {}
    with contextlib.closing(psycopg2.connect(args.dsn)) as conn:
        for ns, entry in sorted(entries, key=lambda x: x[1]["actual_bytes"]):
            if args.only and entry["id"] not in args.only:
                continue
            schema, tname = names[entry["id"]]
            try:
                r = load_one(conn, entry, schema, tname, profiles.get(entry["path"]))
            except Exception as e:
                conn.rollback()
                r = {"id": entry["id"], "path": entry["path"], "table": f"{schema}.{tname}", "status": "failed",
                     "error": f"{type(e).__name__}: {e}"[:600]}
            results[entry["id"]] = r
            print(json.dumps({k: r.get(k) for k in ("id", "status", "rows", "columns", "total_bytes", "seconds", "error")}), flush=True)
            json.dump({"results": results}, open(args.report, "w"), indent=1, default=str)
        rec, db_bytes = reconcile(conn, entries, names, results)
    verified = set(rec["verified"])
    report = {"results": results, "reconciliation": rec, "database_bytes": db_bytes,
              "verified_table_bytes": sum(r.get("total_bytes") or 0 for i, r in results.items() if i in verified),
              "verified_source_bytes": sum(r.get("source_bytes") or 0 for i, r in results.items() if i in verified)}
    json.dump(report, open(args.report, "w"), indent=1, default=str)
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in rec.items()}),
          json.dumps({k: report[k] for k in ("database_bytes", "verified_table_bytes", "verified_source_bytes")}))
    return 0 if len(rec["verified"]) == rec["expected"] else 1


if __name__ == "__main__":
    sys.exit(main())
