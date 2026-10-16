"""Copy an MLflow SQLite store (tracking or basic-auth) into PostgreSQL, row for row.

The target schema must already exist at the same alembic revision (created by
MLflow's own initializer). Tables are loaded in foreign-key order, one
transaction per table, so an interruption leaves only whole tables behind. A
journal table in the target records each finished table with its row count and
digest; a rerun skips journal-complete tables whose live digest still matches
and truncates/reloads everything after the first incomplete table.

Each table is verified with an order-independent digest of typed, length-
delimited row encodings computed independently from source and target, so
value-level corruption (including same-size changes) fails verification and
NULL, text and separator characters cannot collide.

The journal is bound to the source snapshot (file sha256 + schema revision):
a rerun against a different snapshot is refused before any target write, and
journal-complete tables are re-compared against the current source as well as
the live target. --verify-only runs in a READ ONLY transaction and writes nothing.

Primary keys, timestamps, IDs, JSON text and nulls are copied unchanged;
serial sequences are advanced to max(id) afterwards. Nothing is printed from
row contents.

Usage:
  python -m research_cloud.mlflow_migrate.copy_store --source SQLITE --target URL
      --version-table alembic_version [--verify-only] [--stop-after-tables N] --report OUT.json
"""
import argparse
import hashlib
import json
import math
import sqlite3
import sys
import time

import psycopg2
import psycopg2.extras

JOURNAL = "_rc_migration_journal"
META = "_rc_migration_source"


class MigrationError(RuntimeError):
    pass


def pg_columns(cur, table, generated=False):
    """Insertable (stored) columns, or with generated=True every column including generated ones.

    Generated columns are recomputed by PostgreSQL on insert, but their values are still part
    of the comparison set, so a differing engine expression fails verification."""
    cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' "
        "AND table_name=%s" + ("" if generated else " AND is_generated='NEVER'") + " ORDER BY ordinal_position",
        (table,))
    return cur.fetchall()


def generated_columns(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' "
                "AND table_name=%s AND is_generated<>'NEVER'", (table,))
    return [r[0] for r in cur.fetchall()]


def fk_order(cur, version_table):
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
                "AND table_type='BASE TABLE'")
    tables = {r[0] for r in cur.fetchall()} - {version_table, JOURNAL, META}
    cur.execute("""
        SELECT tc.table_name, ccu.table_name FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema='public'""")
    deps = {t: set() for t in tables}
    for child, parent in cur.fetchall():
        if child in deps and parent in tables and parent != child:
            deps[child].add(parent)
    order = []
    while deps:
        ready = sorted(t for t, d in deps.items() if not d - set(order))
        if not ready:
            raise MigrationError(f"foreign-key cycle among {sorted(deps)}")
        for t in ready:
            order.append(t)
            del deps[t]
    return order


def canonical(value, pg_type):
    """JSON-safe typed value shared by source and target values of one column type."""
    if value is None:
        return None
    if pg_type == "boolean":
        return ["b", bool(int(value))]
    if pg_type in ("double precision", "real"):
        f = float(value)
        return ["f", "nan" if math.isnan(f) else repr(f)]
    if pg_type in ("integer", "bigint", "smallint"):
        return ["i", int(value)]
    if pg_type == "bytea":
        return ["x", bytes(value).hex()]
    return ["s", str(value)]


def row_encoding(row, types):
    return json.dumps([canonical(v, t) for v, t in zip(row, types)], ensure_ascii=True,
                      separators=(",", ":")).encode("ascii")


def digest(rows, types):
    h = hashlib.sha256()
    for enc in sorted(row_encoding(row, types) for row in rows):
        h.update(len(enc).to_bytes(8, "big"))
        h.update(enc)
    return h.hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def source_rows(src, table, cols):
    names = ",".join(f'"{c}"' for c, _ in cols)
    return src.execute(f'SELECT {names} FROM "{table}"').fetchall()


def target_rows(cur, table, cols):
    exprs = ",".join(f'"{c}"::text' if t in ("json", "jsonb", "date") else f'"{c}"' for c, t in cols)
    cur.execute(f'SELECT {exprs} FROM "{table}"')
    return cur.fetchall()


def coerce(row, cols):
    out = []
    for value, (name, pg_type) in zip(row, cols):
        if value is None:
            out.append(None)
        elif pg_type == "boolean":
            out.append(bool(int(value)))
        elif pg_type == "bytea":
            out.append(psycopg2.Binary(bytes(value)))
        elif pg_type in ("double precision", "real"):
            out.append(float(value))
        elif isinstance(value, str) and "\x00" in value:
            raise MigrationError(f"NUL character in {name}; PostgreSQL text cannot store it")
        else:
            out.append(value)
    return tuple(out)


def check_source_columns(src, table, cols, generated):
    # table_xinfo hidden values: 0 normal, 1 virtual-table hidden, 2/3 generated (virtual/stored)
    have = [r[1] for r in src.execute(f'PRAGMA table_xinfo("{table}")') if r[6] not in (2, 3)]
    src_generated = sorted(r[1] for r in src.execute(f'PRAGMA table_xinfo("{table}")') if r[6] in (2, 3))
    if src_generated != sorted(generated):
        raise MigrationError(f"generated columns differ in {table}: source {src_generated} target {sorted(generated)}")
    if sorted(have) != sorted(c for c, _ in cols):
        raise MigrationError(f"column mismatch in {table}: source {sorted(have)} target {sorted(c for c, _ in cols)}")


def bind_source(cur, source_sha, revision):
    """Create the journal on first use and refuse a target already bound to another snapshot."""
    cur.execute(f'CREATE TABLE IF NOT EXISTS "{META}" (source_sha256 text NOT NULL, revision text NOT NULL, '
                f'bound_at double precision NOT NULL)')
    cur.execute(f'CREATE TABLE IF NOT EXISTS "{JOURNAL}" (table_name text PRIMARY KEY, rows bigint NOT NULL, '
                f'digest text NOT NULL, completed_at double precision NOT NULL)')
    cur.execute(f'SELECT source_sha256, revision FROM "{META}"')
    bound = cur.fetchall()
    if not bound:
        cur.execute(f'INSERT INTO "{META}" VALUES (%s, %s, %s)', (source_sha, revision, time.time()))
    elif bound != [(source_sha, revision)]:
        raise MigrationError("target journal is bound to a different source snapshot; refusing to resume")


def reset_sequences(cur, tables):
    advanced = {}
    for table in tables:
        for col, _ in pg_columns(cur, table):
            cur.execute("SELECT pg_get_serial_sequence(%s, %s)", (f'"{table}"', col))
            seq = cur.fetchone()[0]
            if not seq:
                continue
            cur.execute(f'SELECT max("{col}") FROM "{table}"')
            top = cur.fetchone()[0]
            if top is None:
                cur.execute("SELECT setval(%s, 1, false)", (seq,))
            else:
                cur.execute("SELECT setval(%s, %s, true)", (seq, top))
            advanced[f"{table}.{col}"] = top
    return advanced


def run(args):
    src = sqlite3.connect(f"file:{args.source}?mode=ro", uri=True)
    src.execute("PRAGMA query_only=ON")
    pg = psycopg2.connect(args.target)
    pg.set_session(readonly=bool(args.verify_only), autocommit=False)
    cur = pg.cursor()

    src_ver = src.execute(f'SELECT version_num FROM "{args.version_table}"').fetchall()
    cur.execute(f'SELECT version_num FROM "{args.version_table}"')
    tgt_ver = cur.fetchall()
    if [tuple(r) for r in src_ver] != [tuple(r) for r in tgt_ver]:
        raise MigrationError(f"schema revision differs: source {src_ver} target {tgt_ver}")

    revision = json.dumps([list(r) for r in src_ver])
    source_sha = file_sha256(args.source)
    if not args.verify_only:
        bind_source(cur, source_sha, revision)
        pg.commit()
    order = fk_order(cur, args.version_table)
    src_tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")} - {args.version_table}
    if src_tables - set(order):
        raise MigrationError(f"source tables missing from target: {sorted(src_tables - set(order))}")

    report = {"source": args.source, "source_sha256": source_sha, "revision": [list(r) for r in src_ver],
              "order": order, "tables": {}}

    if args.verify_only:
        ok = True
        for table in order:
            cols = pg_columns(cur, table, generated=True)
            types = [t for _, t in cols]
            s_rows, t_rows = source_rows(src, table, cols), target_rows(cur, table, cols)
            s_d, t_d = digest(s_rows, types), digest(t_rows, types)
            report["tables"][table] = {"source_rows": len(s_rows), "target_rows": len(t_rows),
                                       "source_digest": s_d, "target_digest": t_d, "match": s_d == t_d}
            ok &= s_d == t_d and len(s_rows) == len(t_rows)
        pg.rollback()
        report["verified"] = ok
        return report

    cur.execute(f'SELECT table_name, rows, digest FROM "{JOURNAL}"')
    journal = {t: (n, d) for t, n, d in cur.fetchall()}

    # completed tables form a prefix of `order`; everything after the first gap is reloaded
    first_incomplete = next((i for i, t in enumerate(order) if t not in journal), len(order))
    for table in order[:first_incomplete]:
        cols = pg_columns(cur, table, generated=True)
        types = [t for _, t in cols]
        live = digest(target_rows(cur, table, cols), types)
        if live != journal[table][1]:
            raise MigrationError(f"journal-complete table {table} no longer matches its recorded digest")
        if digest(source_rows(src, table, cols), types) != journal[table][1]:
            raise MigrationError(f"source rows of journal-complete table {table} differ from the journal")
        report["tables"][table] = {"status": "skipped_complete", "rows": journal[table][0]}
    redo = order[first_incomplete:]
    for table in reversed(redo):
        cur.execute(f'DELETE FROM "{table}"')
    cur.execute(f'DELETE FROM "{JOURNAL}" WHERE table_name = ANY(%s)', (redo,))
    pg.commit()

    for n, table in enumerate(redo):
        if args.stop_after_tables is not None and n >= args.stop_after_tables:
            report["stopped_early"] = table
            break
        t0 = time.time()
        cols = pg_columns(cur, table)
        types = [t for _, t in cols]
        generated = generated_columns(cur, table)
        check_source_columns(src, table, cols, generated)
        rows = source_rows(src, table, cols)
        names = ",".join(f'"{c}"' for c, _ in cols)
        psycopg2.extras.execute_values(cur, f'INSERT INTO "{table}" ({names}) VALUES %s',
                                       [coerce(r, cols) for r in rows], page_size=2000)
        all_cols = pg_columns(cur, table, generated=True)
        all_types = [t for _, t in all_cols]
        s_d = digest(source_rows(src, table, all_cols), all_types)
        t_d = digest(target_rows(cur, table, all_cols), all_types)
        if s_d != t_d:
            pg.rollback()
            raise MigrationError(f"digest mismatch after loading {table}")
        cur.execute(f'INSERT INTO "{JOURNAL}" VALUES (%s, %s, %s, %s)', (table, len(rows), t_d, time.time()))
        pg.commit()
        report["tables"][table] = {"status": "loaded", "rows": len(rows), "digest": t_d,
                                   "seconds": round(time.time() - t0, 2)}
        if generated:
            report["tables"][table]["generated_columns_recomputed_and_compared"] = generated

    if "stopped_early" not in report:
        report["sequences"] = reset_sequences(cur, order)
        pg.commit()
        report["complete"] = True
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True, help="libpq connection string")
    ap.add_argument("--version-table", default="alembic_version")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--stop-after-tables", type=int, help="testing: simulate an interruption")
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    t0 = time.time()
    try:
        report = run(args)
    except MigrationError as exc:
        report = {"error": str(exc)}
    report["seconds"] = round(time.time() - t0, 2)
    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(args.report, "w") as handle:
        json.dump(report, handle, indent=1)
    ok = "error" not in report and (report.get("complete") or report.get("verified"))
    print(json.dumps({k: report.get(k) for k in ("error", "complete", "verified", "stopped_early", "seconds")}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
