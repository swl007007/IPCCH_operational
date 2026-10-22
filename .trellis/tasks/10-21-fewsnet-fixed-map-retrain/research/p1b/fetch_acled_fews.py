"""Run the existing staging ACLED fetcher with the task's availability cutoff and output dir.

Same query semantics as the 2026-10-19 fetch (three conflict families, same 53-country ISO
set) so the FEWS nearest-admin3 matching keeps its cross-border event pool. Only FROM/TO and
the output directory change. The bearer token is read inside the fetcher process and never
printed or written.
"""
import importlib.util
import sys

TOOL = "/home/swl007007/projects/food-crisis-research/staging/ipcch-update-202610/tools/fetch_acled.py"
spec = importlib.util.spec_from_file_location("fetch_acled", TOOL)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ROOT = sys.argv[1]
module.RAW = sys.argv[1] + "/sources/acled/raw"
module.FROM, module.TO = "2025-01-01", "2026-10-21"
module.main()
