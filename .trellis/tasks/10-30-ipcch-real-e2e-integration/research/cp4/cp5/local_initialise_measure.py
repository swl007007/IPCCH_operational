"""CP5 sizing (offline): entrypoint_v2.initialise_store for real and smoke over the STAGED installed tree (the exact bytes
COPY'd into the image at /opt/ipcch) into a local fake object store; reports time and the report (RSS via the guard).

usage: local_initialise_measure.py CONTEXT_IPCCH_DIR STORE_DIR
"""
import json
import sys
import time

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import entrypoint_v2 as ep

ctx, store_dir = sys.argv[1], sys.argv[2]
cfg = ep.load_config(f"{ctx}/deployment.json")
cfg = {**cfg, "installed": {m: {k: v.replace("/opt/ipcch", ctx) for k, v in i.items()} for m, i in cfg["installed"].items()}}
store = LocalObjectStore(store_dir)
for mode, acceptor in (("real", None), ("smoke", "cp5-local-sizing")):
    t = time.time()
    report = ep.initialise_store(cfg, mode, store=store, acceptor=acceptor)
    print("INIT", mode, round(time.time() - t, 1), json.dumps(report, default=str)[:1500])
