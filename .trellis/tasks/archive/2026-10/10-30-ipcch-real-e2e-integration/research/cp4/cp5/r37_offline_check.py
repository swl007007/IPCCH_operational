"""CP5 R37 offline check (task 10-30): the product guard delivery_job.require_not_activated, evaluated against the LIVE
activated current record, on two in-memory legacy request shapes. NO request is sent or written anywhere."""
import json

from google.cloud import storage

from cloud.common.object_store import GCSObjectStore
from cloud.ipcch import publication as pub
from cloud.orchestrator import delivery_job as dj

store = GCSObjectStore(storage.Client())
root, ns = "gs://food-crisis-test-ipcch-data", "monthly-staging"
snap = pub.read_current(store, root, ns, allow_missing_legacy_record=True)
out = {"current_generation": snap["generation"], "activation": pub.activation(snap["record"])}
for label, req in (("legacy_both_systems_scoring_ipcch", {"release": {"namespace": ns}}),
                   ("legacy_ipcch_only", {"release": {"namespace": ns}, "execution": {"inference_systems": ["ipcch"]}}),
                   ("legacy_fewsnet_only", {"release": {"namespace": ns}, "execution": {"inference_systems": ["fewsnet"]}})):
    try:
        dj.require_not_activated(store, root, req)
        out[label] = "admitted (not rejected by R37)"
    except dj.AcceptanceError as exc:
        out[label] = f"REJECTED: {exc}"[:300]
print(json.dumps(out, indent=1, default=str))
