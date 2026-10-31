"""CP3: prepare (not submit) the user-confirmed real E2E selection - ACLED refresh from the verified f2+f3 research
exports, WFP / history_snapshot / all eight research families keep - and validate it under the existing contracts.
Writes into the operator directory only (create-only); no cloud call, no upload, no retained store touched (the R44
first-refresh check runs on a disposable local store)."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
import pandas as pd  # noqa: E402

from cloud.common.object_store import LocalObjectStore  # noqa: E402
from cloud.ipcch import acled as ac  # noqa: E402
from cloud.ipcch import generation as gen  # noqa: E402
from cloud.ipcch import retained  # noqa: E402
from cloud.ipcch.stores import StoreRoot, VersionedTable  # noqa: E402
from cloud.orchestrator import submit_v2 as sv  # noqa: E402

R = Path("/home/swl007007/projects/food-crisis-research")
EXPORTS = R / "staging/ipcch-update-202610/sources/acled_agg/raw/aggregated_2026-10-20"
HANDOFF = R / "scratch/h2h8h14-final/handoff-build/out-r5-accepted-v1"
EXPECTED = "7bcb051fb3569f09cdec7f840c67d4666e586cbffd77b0d3b4a8feaf95e2fce6"
OUT = Path(sys.argv[1])
PROJECT = sys.argv[2]

man = json.loads((EXPORTS / "exports_manifest.json").read_text())
roles = {v["role"]: (k, v) for k, v in man["files"].items()}
f2, f3 = ((EXPORTS / roles[r][0]).read_bytes() for r in ("f2", "f3"))
for r, data in (("f2", f2), ("f3", f3)):
    assert hashlib.sha256(data).hexdigest() == roles[r][1]["sha256"], r
joined = f2 + (b"" if f2.endswith(b"\n") else b"\n") + f3[f3.index(b"\n") + 1:]
assert hashlib.sha256(joined).hexdigest() == EXPECTED
regions = sorted(set(roles["f2"][1]["regions"]) | set(roles["f3"][1]["regions"]))
start = roles["f2"][1]["week_min"]
end = (pd.Timestamp(roles["f3"][1]["week_max"]) + pd.Timedelta(days=6)).strftime("%Y-%m-%d")

OUT.mkdir(parents=True, exist_ok=False)
acled_path = OUT / "acled_regional_aggregate_f2f3.csv"
with open(acled_path, "xb") as f:
    f.write(joined)
assert sv.file_sha256(acled_path) == EXPECTED

# existing contracts: generation's strict CSV read + parse_export against the accepted handoff's own ACLED tables
tables = ac.AcledTables.from_files({k: str(HANDOFF / rel) for k, rel in gen.ACLED_FILES.items()})
frame = retained.strict_csv(joined.decode("utf-8-sig"), "ipcch.acled export", ac.EXPORT_COLUMNS)
rows, parsed = ac.parse_export(frame, start=start, end=end, regions=regions, tables=tables)
first_refresh = {}
for origin in ("2026-08", "2026-09"):                 # O for M = 2026-10 / 2026-11 (M is fixed only at freeze)
    with tempfile.TemporaryDirectory() as tmp:
        table = VersionedTable(LocalObjectStore(tmp), StoreRoot("real", "gs://disposable/ipcch-v2/real"), "acled_agg_weekly")
        ac.refresh(table, rows, start=start, end=end, regions=regions, feature_origin=origin, tables=tables,
                   source_ref={"uri": "local:" + acled_path.name, "generation": "1", "sha256": EXPECTED})
        _, records, _ = ac.saved_weekly(table)
        first_refresh[origin] = {"r44_first_refresh": "passed", "coverage_end": ac.coverage_end(records, tables, origin)}

choices = {name: {"action": "keep"} for name in sv.CHOICES}
choices["acled"] = {"action": "refresh", "file": str(acled_path), "start": start, "end": end, "regions": regions}
selection = {"schema": sv.SELECTIONS_SCHEMA, "mode": "real", "operations": ["ipcch_generation", "ipcch_inference"],
             "publication": "current", "choices": choices}
sel_path = OUT / "selections.json"
with open(sel_path, "x") as f:
    f.write(json.dumps(selection, indent=1, sort_keys=True) + "\n")

import pipeline  # noqa: E402
preview = sv.submit(pipeline.config(PROJECT), sel_path, execute=False, cloud=None)
evidence = {"acled_file": {"path": str(acled_path), "bytes": len(joined), "sha256": EXPECTED},
            "declared": {"start": start, "end": end, "regions": regions, "region_count": len(regions)},
            "parse_export": {**parsed, "rows_kept": int(len(rows)),
                             "required_regions_declared": sorted(tables.required_regions())},
            "first_refresh_by_candidate_origin": first_refresh,
            "selections": {"path": str(sel_path), "sha256": sv.file_sha256(sel_path)},
            "preview": {"run_id_example": preview["run_id"], "structural_and_namespace_validation": "passed",
                        "acled_upload_uri": preview["request"]["ipcch"]["acled"]["file"]["uri"],
                        "note": "no cloud call; refs provisional; M is fixed at submission freeze"}}
print(json.dumps(evidence, indent=1, sort_keys=True))
