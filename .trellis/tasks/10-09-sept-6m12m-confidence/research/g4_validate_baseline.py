"""Gate G4: initialize the real bound bootstrap through ``pipeline.initialize`` with a fake cloud.

Preview mode runs every baseline check (runtime, six model packages, inventory sizes/hashes,
required assets, ``_diagnostics``). Execute mode then runs the upload path against a streaming
fake (hash-only, nothing stored or sent), so the evidence refs are rewritten to pinned refs and
``_diagnostics`` re-validates them with the published model package ids. No real cloud client.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
CP = REPO / "cloud_pipeline"
sys.path.insert(0, str(CP))
import pipeline as p  # noqa: E402


class StreamingFake:
    """Records uploads as (uri -> sha256); never contacts a service."""

    def __init__(self):
        self.objects = {}

    def put(self, uri, path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 22), b""):
                h.update(block)
        digest = h.hexdigest()
        if uri in self.objects and self.objects[uri] != digest:
            raise AssertionError(f"create-only conflict at {uri}")
        self.objects[uri] = digest
        return {"uri": uri, "generation": "1", "sha256": digest}

    def latest(self, uri):
        return None

    def launch(self, ref, deadline):
        raise AssertionError("init must not launch")


def main() -> int:
    baseline = json.loads((CP / "bootstrap/baseline.json").read_text())
    with tempfile.TemporaryDirectory() as work:
        cfg = dict(project="g4-fake", bucket="g4-fake-bucket", request_bucket="g4-fake-requests",
                   image_uri=baseline["runtime"]["image_uri"], namespace="dual-system", work_dir=work,
                   region="us-central1", service_account="g4@example.com", prepare_job="prep",
                   earth_engine_project="g4-fake", operator="g4@example.com")
        preview = p.initialize(NS(baseline=str(CP / "bootstrap"), execute=False), cfg)
        print("preview:", preview, flush=True)
        fake = StreamingFake()
        result = p.initialize(NS(baseline=str(CP / "bootstrap"), execute=True), cfg, cloud=fake)
        init = json.loads((Path(work) / "initialized.json").read_text())
        diagnostics = init["delivery"]["diagnostics"]
        available = [d for d in diagnostics if d["status"] == "available"]
        unavailable = [(d["system"], d["horizon_months"], d["family"], d["reason"]) for d in diagnostics
                       if d["status"] != "available"]
        for entry in available:
            relative = entry["evidence"]["uri"].split(f"/baselines/{init['baseline_id']}/", 1)[1]
            assert relative.startswith("evidence/") and entry["evidence"]["sha256"] == baseline["files"][relative]["sha256"]
        versions = sorted((Path(work) / "model_versions").glob("*.json"))
        per_model = {tuple(json.loads(v.read_text())["model"][k] for k in ("system", "horizon_months")):
                     sum(d["status"] == "available" for d in json.loads(v.read_text())["diagnostics"]) for v in versions}
        report = {"gate": "G4", "preview": preview, "execute": {k: v for k, v in result.items() if k != "initialized"},
                  "baseline_id": init["baseline_id"], "available": len(available), "unavailable": unavailable,
                  "uploads": len(fake.objects), "model_version_records": len(versions),
                  "available_per_model": {f"{s}/{h}m": n for (s, h), n in sorted(per_model.items())}}
        report["passed"] = (len(available) == 13 and unavailable == [
            ("fewsnet", 0, "polygon_confidence", "missing_evidence"), ("fewsnet", 0, "country_confidence", "missing_evidence")]
            and report["baseline_id"] == hashlib.sha256((CP / "bootstrap/baseline.json").read_bytes()).hexdigest())
    (HERE.parent / "g4_validate_baseline.json").write_text(json.dumps(report, indent=1, default=list) + "\n")
    print(json.dumps(report, indent=1, default=list))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
