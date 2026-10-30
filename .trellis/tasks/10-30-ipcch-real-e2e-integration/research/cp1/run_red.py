"""CP1 red evidence: run the CP1 tests against the HEAD (1faa6ae) climate_tables module loaded in place of the edited one."""
import importlib.util
import pathlib
import sys

import pytest

here = pathlib.Path(__file__).resolve().parent
import cloud.ipcch  # noqa: E402

spec = importlib.util.spec_from_file_location("cloud.ipcch.climate_tables", here / "climate_tables_HEAD.py")
module = importlib.util.module_from_spec(spec)
sys.modules["cloud.ipcch.climate_tables"] = module
spec.loader.exec_module(module)
cloud.ipcch.climate_tables = module
if "--sparse-only" in sys.argv:
    # HEAD has no ProducedTable: a collection-only placeholder lets the sparse PATCH32 tests (which never use it) run
    # against the HEAD reader; every produced-contract test is excluded by -k.
    module.ProducedTable = lambda *a, **k: None
    args = ["-k", "sparse or stays_missing", "tests/cloud/test_ipcch_produced_tables.py"]
else:
    args = ["tests/cloud/test_ipcch_produced_tables.py", "tests/cloud/test_ipcch_climate_tables.py"]
sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", "-rf", *args]))
