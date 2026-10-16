"""Import the declared shapefile bundles into PostGIS and prove the round trip (rehearsal and capacity measurement).

A bundle is every inventory entry with the same ``bundle`` whose ``.shp`` member has proposed storage
``PostGIS table (from .shp bundle) + GCS original bundle``. Two steps, because the geo stack and the database driver
live in different environments:

``export`` (geo env: geopandas/pyogrio/shapely/pyproj)
  1. Every bundle member is stream-hashed and must equal the inventory sha256 (the ``.shp``/``.shx``/``.dbf``/``.prj``/
     ``.cpg`` read together, nothing else).
  2. The ``.shp`` is read with ``geopandas.read_file`` - what the research code uses - in file order. ``_fid`` is the
     0-based feature position. Attribute types come from the driver (``pyogrio.read_info``): integer -> ``bigint``,
     real -> ``double precision``, everything else -> ``text`` (verbatim string). Geometries are written as 2D/3D ISO
     WKB, little endian, hex.
  3. SRID: the exact EPSG code (confidence 100) of the CRS ``read_file`` reports - the CRS the research code sees; e.g.
     an ESRI ``GCS_WGS_1984`` + ``VERTCS`` ``.prj`` is reported as EPSG:4326 - else 0. The ``.prj`` text is kept
     verbatim either way, with the identification basis.
  Output: ``rows.tsv`` (PostgreSQL COPY text) and ``export.json`` (members, columns, srid, prj, counts, rows sha256).

``load`` (database env: psycopg2)
  One transaction per bundle: CREATE TABLE ``<namespace>.<name>`` (``_fid`` primary key, attributes, ``geom``), COPY,
  GiST index, ANALYZE, then verification before COMMIT - row count, every attribute (bigint exact, double exact, NULL
  positions exact, text exact) and ``ST_AsBinary(geom, 'NDR')`` byte-equal to the exported WKB, every SRID equal.
  ``public._geometry_bundles`` keeps the bundle identity (member hashes, prj, srid, export sha256). Any failure rolls
  the bundle back. Geometry validity is recorded (``ST_IsValid`` counts), never repaired.

  python -m research_cloud.sqlimport.load_geometry export --inventory INV.json --bundle ID --out DIR
  python -m research_cloud.sqlimport.load_geometry load --export DIR --dsn DSN --report REPORT.json
"""
import argparse
import hashlib
import json
import os
import sys
import time

from research_cloud.sqlimport.load_inputs import table_name

POSTGIS_STORAGE = "PostGIS table (from .shp bundle) + GCS original bundle"
SHAPEFILE_MEMBERS = {"shp", "shx", "dbf", "prj", "cpg"}
SQL_TYPES = {"int": "bigint", "float": "double precision", "text": "text"}


class GeometryImportFailure(Exception):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def bundle_entries(inventory, bundle):
    out = []
    for ns, block in inventory["namespaces"].items():
        out += [(ns, e) for e in block["files"] if e.get("bundle") == bundle]
    shp = [(ns, e) for ns, e in out if e.get("file_type") == "shp"]
    if len(shp) != 1 or shp[0][1].get("proposed_storage") != POSTGIS_STORAGE:
        raise GeometryImportFailure(f"{bundle}: expected exactly one .shp member destined for PostGIS")
    return shp[0], [(ns, e) for ns, e in out if e.get("file_type") in SHAPEFILE_MEMBERS]


def escape(value):
    if value is None:
        return r"\N"
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def unescape(field):
    if field == r"\N":
        return None
    out, i = [], 0
    while i < len(field):
        c = field[i]
        if c == "\\" and i + 1 < len(field):
            out.append({"t": "\t", "n": "\n", "r": "\r", "\\": "\\"}.get(field[i + 1], field[i + 1]))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def kind_of(dtype):
    dtype = str(dtype)
    if dtype.startswith(("int", "uint")):
        return "int"
    if dtype.startswith("float"):
        return "float"
    return "text"


def render(value, kind):
    import math
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if kind == "int":
        return str(int(value))
    if kind == "float":
        return repr(float(value))
    return str(value)


def export(inventory_path, bundle, out_dir):
    import geopandas
    import numpy as np
    import pyogrio
    import shapely
    from pyproj import CRS
    inventory = json.load(open(inventory_path))
    (ns, shp), members = bundle_entries(inventory, bundle)
    hashes = {}
    for _, e in members:
        actual = sha256_file(e["path"])
        if actual != e["actual_sha256"]:
            raise GeometryImportFailure(f"{e['id']}: sha256 {actual} differs from the inventory")
        hashes[e["id"]] = {"path": e["path"], "sha256": actual, "bytes": os.path.getsize(e["path"])}
    info = pyogrio.read_info(shp["path"])
    kinds = {name: kind_of(dtype) for name, dtype in zip(info["fields"], info["dtypes"])}
    frame = geopandas.read_file(shp["path"])
    columns = [c for c in frame.columns if c != frame.geometry.name]
    if columns != list(info["fields"]):
        raise GeometryImportFailure(f"{bundle}: read_file columns differ from the driver field list")
    prj_path = shp["path"][:-4] + ".prj"
    prj = open(prj_path, encoding="utf-8").read() if os.path.exists(prj_path) else None
    epsg = frame.crs.to_epsg(min_confidence=100) if frame.crs is not None else None
    prj_alone = CRS.from_wkt(prj).to_epsg(min_confidence=100) if prj else None
    geoms = frame.geometry.values
    has_z = bool(np.any(shapely.has_z(geoms[~shapely.is_missing(geoms)])))
    wkb = shapely.to_wkb(geoms, hex=True, output_dimension=3 if has_z else 2, byte_order=1, flavor="iso")
    os.makedirs(out_dir, exist_ok=False)
    rows_path = os.path.join(out_dir, "rows.tsv")
    with open(rows_path, "w", encoding="utf-8", newline="\n") as f:
        values = {c: frame[c].astype(object).where(frame[c].notna(), None).tolist() for c in columns}
        for i in range(len(frame)):
            fields = [str(i)] + [escape(render(values[c][i], kinds[c])) for c in columns]
            fields.append(r"\N" if wkb[i] is None else wkb[i].lower())
            f.write("\t".join(fields) + "\n")
    types = frame.geometry.geom_type.fillna("<null>").value_counts().to_dict()
    record = {"bundle": bundle, "namespace": ns, "shp_entry": shp["id"], "table": table_name(shp["id"]),
              "members": hashes, "encoding": info.get("encoding"), "driver_geometry_type": info.get("geometry_type"),
              "columns": [{"name": c, "kind": kinds[c], "sql_type": SQL_TYPES[kinds[c]]} for c in columns],
              "srid": int(epsg or 0), "prj": prj,
              "srid_basis": {"reader_crs_epsg": epsg, "prj_alone_pyproj_epsg": prj_alone,
                             "reader_crs": frame.crs.to_string() if frame.crs is not None else None},
              "has_z": has_z, "rows": int(len(frame)),
              "geometry_types": {k: int(v) for k, v in types.items()}, "rows_sha256": sha256_file(rows_path),
              "reader": {"geopandas": geopandas.__version__, "pyogrio": pyogrio.__version__, "shapely": shapely.__version__}}
    json.dump(record, open(os.path.join(out_dir, "export.json"), "w"), indent=1)
    return record


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def same(a, b, kind):
    if a is None or b is None:
        return a is None and b is None
    if kind == "int":
        return int(a) == int(b)
    if kind == "float":
        return float(a) == float(b)
    return a == b


def load(export_dir, dsn, report_path):
    import psycopg2
    record = json.load(open(os.path.join(export_dir, "export.json")))
    rows_path = os.path.join(export_dir, "rows.tsv")
    if sha256_file(rows_path) != record["rows_sha256"]:
        raise GeometryImportFailure("rows.tsv differs from its export record")
    schema, table, srid = record["namespace"], record["table"], record["srid"]
    qualified = f"{quote(schema)}.{quote(table)}"
    names = ["_fid"] + [c["name"] for c in record["columns"]] + ["geom"]
    kinds = ["int"] + [c["kind"] for c in record["columns"]] + ["text"]
    t0 = time.time()
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {quote(schema)}")
            cur.execute(f"DROP TABLE IF EXISTS {qualified}")
            cols = ", ".join(f"{quote(c['name'])} {c['sql_type']}" for c in record["columns"])
            dims = "GeometryZ" if record["has_z"] else "Geometry"
            cur.execute(f"CREATE TABLE {qualified} (_fid bigint PRIMARY KEY, {cols}{', ' if cols else ''}"
                        f"geom geometry({dims}, {srid}))")
            staging = "_geom_stage"
            cur.execute(f"CREATE TEMP TABLE {staging} (_fid bigint, {cols}{', ' if cols else ''}geom_hex text) ON COMMIT DROP")
            with open(rows_path, encoding="utf-8") as f:
                cur.copy_expert(f"COPY {staging} FROM STDIN", f)
            attr = ", ".join(quote(c["name"]) for c in record["columns"])
            cur.execute(f"INSERT INTO {qualified} SELECT _fid, {attr}{', ' if attr else ''}"
                        f"ST_SetSRID(ST_GeomFromWKB(decode(geom_hex, 'hex')), {srid}) FROM {staging}")
            cur.execute(f"CREATE INDEX ON {qualified} USING gist (geom)")
            cur.execute(f"ANALYZE {qualified}")
            readback = os.path.join(export_dir, "readback.tsv")
            with open(readback, "w", encoding="utf-8", newline="\n") as f:
                cur.copy_expert(f"COPY (SELECT _fid, {attr}{', ' if attr else ''}encode(ST_AsBinary(geom, 'NDR'), 'hex') "
                                f"FROM {qualified} ORDER BY _fid) TO STDOUT", f)
            mismatches, count = [], 0
            with open(rows_path, encoding="utf-8") as a, open(readback, encoding="utf-8") as b:
                for count, (la, lb) in enumerate(zip(a, b), 1):
                    fa, fb = la.rstrip("\n").split("\t"), lb.rstrip("\n").split("\t")
                    for name, kind, x, y in zip(names, kinds, fa, fb):
                        if not same(unescape(x), unescape(y), kind) and len(mismatches) < 20:
                            mismatches.append({"row": count, "column": name})
                    if len(fa) != len(fb):
                        mismatches.append({"row": count, "column": "<field count>"})
            cur.execute(f"SELECT count(*), count(*) FILTER (WHERE geom IS NOT NULL AND ST_SRID(geom) <> %s), "
                        f"count(*) FILTER (WHERE NOT ST_IsValid(geom)), count(*) FILTER (WHERE geom IS NULL) FROM {qualified}",
                        (srid,))
            rows, srid_bad, invalid, null_geom = cur.fetchone()
            ok = rows == record["rows"] == count and not mismatches and srid_bad == 0
            if not ok:
                raise GeometryImportFailure(json.dumps({"rows": rows, "expected": record["rows"], "compared": count,
                                                        "srid_mismatch": srid_bad, "mismatches": mismatches}))
            cur.execute("CREATE TABLE IF NOT EXISTS public._geometry_bundles (bundle text PRIMARY KEY, "
                        "schema_name text, table_name text, srid int, prj text, rows bigint, rows_sha256 text, members jsonb)")
            cur.execute("INSERT INTO public._geometry_bundles VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (bundle) DO UPDATE "
                        "SET schema_name=EXCLUDED.schema_name, table_name=EXCLUDED.table_name, srid=EXCLUDED.srid, "
                        "prj=EXCLUDED.prj, rows=EXCLUDED.rows, rows_sha256=EXCLUDED.rows_sha256, members=EXCLUDED.members",
                        (record["bundle"], schema, table, srid, record["prj"], rows, record["rows_sha256"],
                         json.dumps(record["members"])))
            cur.execute("SELECT pg_total_relation_size(%s), pg_relation_size(%s), pg_indexes_size(%s)",
                        (f"{schema}.{table}",) * 3)
            total, heap, indexes = cur.fetchone()
        result = {"status": "verified", "bundle": record["bundle"], "table": f"{schema}.{table}", "srid": srid,
                  "rows": rows, "attributes_compared": len(record["columns"]), "wkb_byte_equal": True,
                  "invalid_geometries_recorded": invalid, "null_geometries": null_geom,
                  "geometry_types": record["geometry_types"], "members": record["members"],
                  "rows_sha256": record["rows_sha256"], "readback_sha256": sha256_file(readback),
                  "bytes": {"total": total, "heap_and_toast": total - indexes, "heap": heap, "indexes": indexes},
                  "seconds": round(time.time() - t0, 1)}
    except Exception as exc:
        result = {"status": "failed", "bundle": record["bundle"], "error": str(exc)[:4000]}
    finally:
        conn.close()
    report = json.load(open(report_path)) if os.path.exists(report_path) else {}
    report[record["bundle"]] = result
    json.dump(report, open(report_path, "w"), indent=1)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--inventory", required=True)
    e.add_argument("--bundle", required=True)
    e.add_argument("--out", required=True)
    l = sub.add_parser("load")
    l.add_argument("--export", required=True)
    l.add_argument("--dsn", required=True)
    l.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "export":
        r = export(args.inventory, args.bundle, args.out)
        print(json.dumps({k: r[k] for k in ("bundle", "table", "rows", "srid", "geometry_types")}))
        return 0
    r = load(args.export, args.dsn, args.report)
    print(json.dumps({k: v for k, v in r.items() if k != "members"}))
    return 0 if r["status"] == "verified" else 1


if __name__ == "__main__":
    sys.exit(main())
