"""Build-staging tool (task 10-30): write the isolated smoke fixture root installed at /opt/ipcch/smoke-fixture.

    python -m tests.cloud.make_smoke_fixture OUT_DIR

OUT_DIR (must not exist) receives ``bundle/`` - the existing smoke fixture bundle (manifest ``fixture: true``, 3 areas in
2 fixture countries, synthetic histories for every family, delivered calendar, fixture ACLED tables, geometry,
population and country references; the 527-name feature order of the accepted package). It runs on the operator's
staging machine only: the runtime image receives the written files (hash-bound in INSTALL.json by
``cloud.ipcch.install stage``), never this module, the test suite or pytest. It never reads the real handoff."""

import hashlib
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    from tests.cloud import ipcch_smoke_fixture as fx

    (out,) = argv if argv is not None else sys.argv[1:]
    root = Path(out)
    root.mkdir(parents=True, exist_ok=False)
    bundle, _ = fx.build_bundle(root)
    manifest = (bundle / "handoff_manifest.json").read_bytes()
    print(json.dumps({"fixture_root": str(root), "bundle": str(bundle),
                      "manifest_sha256": hashlib.sha256(manifest).hexdigest()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
