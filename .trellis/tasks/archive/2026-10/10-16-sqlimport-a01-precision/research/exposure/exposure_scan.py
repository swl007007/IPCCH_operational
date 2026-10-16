"""A01 exposure scan over the 53 inventoried CSV sources (read only; design.md "Exposure scan").

Per file: stream physical lines in binary (each line updates sha256; bytes covered must equal the file size and
the sha must equal the inventory), match the CSV integer-field prefilter on every line, and count lines. A file
is single-line iff its physical line count == imported rows + 1 (header). For files with candidate lines or with
multi-line records, a csv.reader pass tokenizes the records spanning candidate lines (and every multi-line
record) and classifies each field holding an integer of 16+ digits against the migrated column type:
  class1  pure integer literal as infer_types sees it, > 15 digits, in a column migrated as double precision
  class2  class1 with int(raw) != int(float(raw))  (actual precision loss; stored value then read back)
  class3  lexical edge: padding/quote/sign/leading zero, or a long integer in a text/bigint column
Usage: python exposure_scan.py --report CSV_IMPORT_REPORT --inventory INVENTORY --out RECEIPT.json [--self-test-only]
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time

FIELD = re.compile(rb'(?<![^,\r\n])\s*"?\s*[+-]?\s*[0-9]{16,}\s*"?\s*(?=,|$)')
PURE = re.compile(r"-?\d+")
EXCLUDED = re.compile(r"\+|-?0\d")          # infer_types keeps these verbatim (text)
LONG = re.compile(r"\d{16,}")
csv.field_size_limit(sys.maxsize)


def self_test():
    cases = [
        (b"a,9007199254740993,9007199254740994\n", 2),            # adjacent integer fields
        (b'a," 9007199254740993 ",x\n', 1),                       # quoted + space padding
        (b"a,+9007199254740993,-9007199254740993\r\n", 2),         # signs, CRLF
        (b"9007199254740993,1\r", 1),                              # line start, CR ending
        (b"a,0.12345678901234567,1e17\n", 0),                      # decimal mantissa / exponent: no match
        (b"a,12345678901234567.5\n", 0),                           # long integer part of a decimal: no match
        (b"a,9007199254740993", 1),                                # end of file without newline
        (b'a,"x\r9007199254740993",y\n', 1),                       # over-inclusive after a CR inside quotes (false positive, conservative)
        (b'a,"\r\n9007199254740993",y\n', 1),                      # quoted field with CRLF padding (second physical line)
        (b"x\r9007199254740993,1\r", 1),                           # CR-only record separators
    ]
    bad = []
    for line, want in cases:
        got = sum(len(FIELD.findall(part)) for part in io.BytesIO(line))
        if got != want:
            bad.append((line, got, want))
    # a token spanning a read boundary: line iteration over a tiny-buffer reader never splits a line
    raw = b"h1,h2\n" + b"1," + b"9" * 20 + b"\n"
    lines = list(io.BufferedReader(io.BytesIO(raw), buffer_size=8))
    if sum(len(FIELD.findall(x)) for x in lines) != 1 or b"".join(lines) != raw:
        bad.append(("tiny-buffer", None, 1))
    return bad


def stream(path):
    h, nbytes, nlines, cand, lone_cr = hashlib.sha256(), 0, 0, {}, 0
    with open(path, "rb") as f:
        for no, line in enumerate(f, 1):
            h.update(line)
            nbytes += len(line)
            nlines = no
            lone_cr += line.count(b"\r") - line.count(b"\r\n")
            m = FIELD.findall(line)
            if m:
                cand[no] = len(m)
    return h.hexdigest(), nbytes, nlines, cand, lone_cr


def classify(value, sql_type):
    digits = LONG.search(value)
    if not digits:
        return None
    pure = bool(PURE.fullmatch(value)) and not EXCLUDED.match(value)
    rec = {"value": value, "type": sql_type}
    if pure and len(value.lstrip("-")) > 15:
        if sql_type == "double precision":
            rec["class"] = "class2" if int(value) != int(float(value)) else "class1"
        else:
            rec["class"] = "class3"
            rec["edge"] = f"long integer in a {sql_type} column (not floated)"
    else:
        s = value.strip().strip('"').strip()
        if not re.fullmatch(r"[+-]?\d{16,}", s):
            return None                                   # 16+ digits inside a non-integer value
        rec["class"] = "class3"
        rec["edge"] = "padding/sign/leading zero"
        if sql_type == "double precision":
            rec["edge"] += "; in a double column: int != int(float) is " + str(int(s) != int(float(s)))
    return rec


def parse_candidates(path, header, types, cand, multiline, everything=False):
    """Aggregated: {(column, class, edge): {"count", "examples" (first 50)}} - never one dict per field in memory."""
    out, records = {}, 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)
        last = reader.line_num
        for src_row, row in enumerate(reader, 1):
            first, last_line = last + 1, reader.line_num
            last = last_line
            span = range(first, last_line + 1)
            if not everything and not (multiline and last_line > first) and not any(n in cand for n in span):
                continue
            records += 1
            for c, typ, value in zip(header, types, row):
                r = classify(value, typ)
                if r:
                    key = (c, r["class"], r.get("edge", ""))
                    agg = out.setdefault(key, {"column": c, "class": r["class"], "edge": r.get("edge", ""), "type": r["type"],
                                               "count": 0, "examples": []})
                    agg["count"] += 1
                    if len(agg["examples"]) < 50:
                        agg["examples"].append({"source_row": src_row, "lines": [first, last_line], "value": r["value"],
                                                "short_row": len(row) < len(header)})
    return list(out.values()), records


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--catalog", required=True, help="cloud-column-catalog.json (per-column migrated sql_type)")
    ap.add_argument("--self-test-only", action="store_true")
    args = ap.parse_args(argv)
    bad = self_test()
    print(json.dumps({"self_test_failures": [str(b) for b in bad]}), flush=True)
    if bad or args.self_test_only:
        return 1 if bad else 0
    report = json.load(open(args.report))["results"]
    catalog = json.load(open(args.catalog))["tables"]
    inv = {}
    for block in json.load(open(args.inventory))["namespaces"].values():
        for f in block["files"]:
            if isinstance(f, dict) and f.get("file_type") == "csv" and str(f.get("proposed_storage", "")).startswith("Cloud SQL table"):
                inv[f["id"]] = f
    files, t0 = [], time.time()
    for eid, res in sorted(report.items()):
        e = inv[eid]
        t = time.time()
        sha, nbytes, nlines, cand, lone_cr = stream(e["path"])
        rec = {"id": eid, "table": res["table"], "double_columns": sum(1 for x in catalog[res["table"]] if x["sql_type"] == "double precision"), "path": e["path"], "inventory_sha256": e["actual_sha256"], "sha256": sha,
               "sha_equal": sha == e["actual_sha256"] == res["sha256"], "bytes": nbytes, "bytes_equal": nbytes == e["actual_bytes"],
               "physical_lines": nlines, "lone_cr": lone_cr, "imported_rows": res["rows"],
               "single_line_records": nlines == res["rows"] + 1 and lone_cr == 0,
               "candidate_lines": len(cand), "candidate_fields": sum(cand.values()), "first_candidate_lines": sorted(cand)[:10]}
        if cand or not rec["single_line_records"]:
            header = next(csv.reader(open(e["path"], newline="", encoding="utf-8-sig")))
            cols = sorted(catalog[res["table"]], key=lambda x: x["position"])
            if [x["source_header"] for x in cols] != header:
                raise SystemExit(f"{eid}: catalog headers differ from the source header")
            types = [x["sql_type"] for x in cols]
            # lone CRs make binary and csv line numbers disagree: tokenize every record of such a file
            fields, records = parse_candidates(e["path"], header, types, cand, not rec["single_line_records"],
                                               everything=lone_cr > 0)
            rec["full_record_parse"] = lone_cr > 0
            rec["records_tokenized"] = records
            rec["fields"] = fields
            rec["field_counts"] = {k: sum(x["count"] for x in fields if x["class"] == k) for k in ("class1", "class2", "class3")}
            rec["class12_columns"] = sorted({x["column"] for x in fields if x["class"] in ("class1", "class2")})
            rec["class3_edges"] = sorted({(x["column"], x["edge"]) for x in fields if x["class"] == "class3"})
        rec["seconds"] = round(time.time() - t, 1)
        files.append(rec)
        print(json.dumps({k: rec.get(k) for k in ("id", "sha_equal", "bytes_equal", "single_line_records", "candidate_lines", "field_counts", "seconds")}), flush=True)
    summary = {"files": len(files), "all_sha_equal": all(f["sha_equal"] for f in files), "all_bytes_equal": all(f["bytes_equal"] for f in files),
               "bytes_covered": sum(f["bytes"] for f in files), "files_with_multiline_records": [f["id"] for f in files if not f["single_line_records"]],
               "files_with_candidates": [f["id"] for f in files if f["candidate_lines"]],
               "class1_fields": sum(f.get("field_counts", {}).get("class1", 0) for f in files),
               "class2_fields": sum(f.get("field_counts", {}).get("class2", 0) for f in files),
               "class3_fields": sum(f.get("field_counts", {}).get("class3", 0) for f in files),
               "seconds": round(time.time() - t0, 1)}
    json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "self_test": "passed", "summary": summary, "files": files},
              open(args.out, "w"), indent=1, default=list)
    print(json.dumps(summary), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
