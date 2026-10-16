"""Read-only storage capacity record for the research/tracking/auth databases (rehearsal and cloud acceptance).

Per database: ``pg_database_size``. For each one, per schema and per relation kind: heap, TOAST (with its index) and
index bytes, plus which tables are import side tables (``__irregular_rows``), catalogs (``_column_catalog``,
``_geometry_bundles``) or PostGIS geometry tables (with their GiST index bytes). Cluster-level: the current ``pg_wal``
size and WAL settings, and cumulative ``temp_files``/``temp_bytes`` since the statistics reset (an observed lower
bound on server temp use, not a reconstructed peak). Disk-backed client readback (the verification ``COPY ... TO``
temp file on the importing host) is not server storage and is not counted here.

  python -m research_cloud.sqlimport.capacity --dsn "host=... user=..." --databases research mlflow mlflow_auth
      --out CAPACITY.json
"""
import argparse
import json
import sys
import time

RELATIONS = """
SELECT n.nspname, c.relname, c.relkind,
       pg_relation_size(c.oid) AS heap,
       COALESCE(pg_total_relation_size(c.reltoastrelid), 0) AS toast,
       pg_indexes_size(c.oid) AS indexes,
       pg_total_relation_size(c.oid) AS total,
       EXISTS (SELECT 1 FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid
               WHERE a.attrelid = c.oid AND t.typname = 'geometry' AND NOT a.attisdropped) AS has_geometry
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_toast%'
"""


def kind(schema, name, has_geometry):
    if name.endswith("__irregular_rows"):
        return "side_table"
    if name in ("_column_catalog", "_geometry_bundles", "spatial_ref_sys"):
        return "catalog"
    if has_geometry:
        return "geometry"
    return "table"


def measure(dsn, databases):
    import psycopg2
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "databases": {}}
    for db in databases:
        with psycopg2.connect(f"{dsn} dbname={db}") as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_database_size(current_database())")
            size = cur.fetchone()[0]
            cur.execute(RELATIONS)
            groups, largest = {}, []
            for schema, name, _, heap, toast, idx, total, geo in cur.fetchall():
                g = groups.setdefault(f"{schema}:{kind(schema, name, geo)}",
                                      {"relations": 0, "heap": 0, "toast": 0, "indexes": 0, "total": 0})
                g["relations"] += 1
                for k, v in (("heap", heap), ("toast", toast), ("indexes", idx), ("total", total)):
                    g[k] += v
                largest.append((total, f"{schema}.{name}"))
            relation_total = sum(g["total"] for g in groups.values())
            out["databases"][db] = {"database_bytes": size, "relation_bytes": relation_total,
                                    "other_bytes": size - relation_total, "groups": dict(sorted(groups.items())),
                                    "largest": [{"relation": n, "bytes": b} for b, n in sorted(largest, reverse=True)[:10]]}
    with psycopg2.connect(f"{dsn} dbname={databases[0]}") as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(sum(size), 0) FROM pg_ls_waldir()")
        wal = int(cur.fetchone()[0])
        settings = {}
        for name in ("max_wal_size", "min_wal_size", "wal_keep_size", "shared_buffers", "work_mem", "maintenance_work_mem"):
            cur.execute(f"SHOW {name}")
            settings[name] = cur.fetchone()[0]
        cur.execute("SELECT datname, temp_files, temp_bytes, stats_reset FROM pg_stat_database WHERE datname IS NOT NULL")
        temp = {d: {"temp_files": f, "temp_bytes": b, "stats_reset": str(r) if r else None} for d, f, b, r in cur.fetchall()
                if d in databases}
    out["cluster"] = {"pg_wal_bytes_now": wal, "settings": settings, "temp_since_stats_reset": temp}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True, help="libpq parameters without dbname")
    ap.add_argument("--databases", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    record = measure(args.dsn, args.databases)
    with open(args.out, "w") as f:
        json.dump(record, f, indent=1)
    print(json.dumps({db: {k: v for k, v in d.items() if k in ("database_bytes", "relation_bytes", "other_bytes")}
                      for db, d in record["databases"].items()} | {"cluster": {"pg_wal_bytes_now": record["cluster"]["pg_wal_bytes_now"]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
