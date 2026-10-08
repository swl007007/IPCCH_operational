"""Full-scale local CP3 integration run of cloud.orchestrator.deliver (task evidence; no training)."""
import json, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))
from cloud.orchestrator.deliver import deliver, load_prepared_features

prepare_id, out, system = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
# optional 4th argument: FEWSNET checkpoint directory (resume; read-only)
checkpoint = Path(sys.argv[4]) if len(sys.argv) > 4 else None
CACHE = Path("/tmp/oct-prepared-cache") / prepare_id  # pinned objects cached before the cloud window closed


class CachedPinnedReader:
    """Local copies of exact GCS generations (read_pinned still checks every sha256)."""

    def __init__(self, root):
        self.index = json.loads((root / "cache_index.json").read_text())["objects"]
        self.root = root

    def read_bytes(self, uri, generation):
        entry = self.index.get(f"{uri}#{generation}")
        return None if entry is None else (self.root / entry["file"]).read_bytes()


if CACHE.exists():
    manifest = json.loads((CACHE / "prepared_manifest.json").read_text())
    features = load_prepared_features(manifest, CachedPinnedReader(CACHE))
else:
    from google.cloud import storage

    from cloud.orchestrator.prepare import GcsPinnedReader

    client = storage.Client(project="manuel-remote-sensing")
    manifest = json.loads(client.bucket("manuel-remote-sensing-oct-delivery-debug").blob(
        f"prepared/{prepare_id}/prepared_manifest.json").download_as_bytes())
    features = load_prepared_features(manifest, GcsPinnedReader(client))
V3 = REPO / "Outcome/model_delivery/202609_h5/20260923_country_confidence_v3"
FEWS = REPO / "Outcome/fewsnet_partitioned_rf/model_artifacts/local-202604-57cb3b981198-510375f58cd8"
started = time.time()
report = deliver(origin="2026-10", out=out, prepared_families=manifest["families"], prepared_features=features,
                 ipcch_panel=V3 / "inputs/ipcch_panel.csv", ipcch_template=V3 / "inputs/ipcch_april_panel.csv",
                 ipcch_package_root=REPO / "model_artifacts/launch_2026_04",
                 fewsnet_raw=V3 / "inputs/fewsnet_refreshed_raw.csv", fewsnet_packages={h: FEWS / f"{h}m" for h in (0, 6, 12)},
                 census={s: V3 / f"{s}/country_population_reference.csv" for s in ("fewsnet", "ipcch")},
                 geometry={s: V3 / f"{s}/polygons.geojson" for s in ("fewsnet", "ipcch")}, system=system,
                 fewsnet_checkpoint=checkpoint)
print(json.dumps({"elapsed_seconds": round(time.time() - started, 1), "prepare_id": prepare_id, "report": report},
                 indent=2, default=str)[:4000])
