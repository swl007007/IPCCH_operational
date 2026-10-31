"""CP3 offline evidence: verify the ACTUAL accepted envelope/package/handoff with the install verifier (every package
and handoff member re-hashed streaming), a freshly generated isolated smoke fixture and the concrete deployment config.
Nothing is copied: the real artifacts are symlinked into a temporary layout (realpath is verified); no cloud call."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
from cloud.ipcch import install  # noqa: E402
from tests.cloud import make_smoke_fixture  # noqa: E402

R = Path("/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final")
ENV = R / "envelope/ipcch-combination-envelope-v2-accepted.json"
PKG = R / "package-build/out-r1/package"
HANDOFF = R / "handoff-build/out-r5-accepted-v1"
SHA = "03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596"
out_dir = Path(sys.argv[1])

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / "ipcch"
    (root / "envelope").mkdir(parents=True)
    os.symlink(ENV, root / install.LAYOUT["envelope"])
    os.symlink(PKG, root / install.LAYOUT["package"])
    os.symlink(HANDOFF, root / install.LAYOUT["handoff"])
    make_smoke_fixture.main([str(root / install.LAYOUT["smoke_root"])])
    (root / install.LAYOUT["config"]).write_bytes(Path("deploy/ipcch_v2_deployment.food-crisis-test.json").read_bytes())
    body = install.verify_tree(root, envelope_sha256=SHA)
(out_dir / "INSTALL.dryrun.json").write_text(json.dumps(body, indent=1, sort_keys=True) + "\n")
print(json.dumps({k: body[k] for k in ("envelope", "package")} | {
    "handoff": {k: v for k, v in body["handoff"].items() if k != "member_sha256"},
    "smoke_fixture": {k: v for k, v in body["smoke_fixture"].items() if k != "member_sha256"},
    "config": body["config"]}, indent=1, sort_keys=True))
