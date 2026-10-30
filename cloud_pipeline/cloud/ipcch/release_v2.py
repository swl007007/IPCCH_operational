"""Publish one v2 IPCCH run: delivery assembly bound to the current snapshot, upload, verified publication (task 10-29;
R17, R18, R36, R37, R39, R47, R63, R66 and the CP4 rulings).

``publish_ipcch_run`` reads the current snapshot and requires its generation to be the request's expected pointer
generation (the CAS precondition); the delivery's other-system member is inherited from EXACTLY that snapshot; the new
IPCCH member is written from the scored batch; shared reports are merged; the tree is uploaded create-only under the
mode root; ``publication.publish`` then verifies the stored delivery (``delivery_v2.verify_delivery``) before the
candidate record or the pointer CAS. A moved pointer is ``publication_failed`` (no rebase, no rescoring); the generated
batch and the uploaded delivery stay reported.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Mapping

from cloud.ipcch import delivery_member as dm
from cloud.ipcch import delivery_v2 as dv
from cloud.ipcch import publication as pub


def ipcch_member_record(prov: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract": dm.CONTRACT, "mode": prov["mode"], "execution_month": prov["execution_month"],
            "feature_origin": prov["feature_origin"], "horizons": prov["horizons"],
            "model_horizons": [h["model_horizon_months"] for h in prov["horizons"]],
            "public_leads": [h["public_lead_months"] for h in prov["horizons"]], "package": prov["package"],
            "batch": prov["batch"], "provenance_sha256": prov["provenance_sha256"],
            "provenance_files": sorted(prov["files"])}


def publish_ipcch_run(store, root_uri: str, *, namespace: str, run_id: str, mode: str, publication: str,
                      expected_pointer_generation: str, request_ref: Mapping[str, str], member_inputs: Mapping[str, Any],
                      workdir: str, now=None) -> dict[str, Any]:
    snapshot = pub.read_current(store, root_uri, namespace)
    if publication == "current" and snapshot["generation"] != str(expected_pointer_generation):
        return {"status": "publication_failed", "stage": "precheck",
                "reason": f"pointer generation {snapshot['generation']} != expected {expected_pointer_generation}"}
    with tempfile.TemporaryDirectory(prefix=f"v2-delivery-{run_id}-", dir=workdir) as tmp:
        out = Path(tmp) / "delivery"
        prov = dm.write_member(out, **member_inputs)
        members = {"ipcch": ipcch_member_record(prov)}
        current = pub.members(snapshot["record"])
        if "fewsnet" in current:                           # the other system: exactly the bound snapshot's member
            members["fewsnet"] = dv.inherit(out, store, root_uri, "fewsnet", current["fewsnet"])
        dv.merge_shared_reports(out, members)
        dv.write_manifest(out, run_id=run_id, members=members)
        ref = dv.upload(store, root_uri, run_id, out)
    new = {"ipcch": {**members["ipcch"], "delivery": {"manifest": ref}}}
    result = pub.publish(store, root_uri, run_id=run_id, namespace=namespace, publication=publication, mode=mode,
                         expected_pointer_generation=str(expected_pointer_generation), request_ref=request_ref,
                         new_members=new, delivery={"manifest": ref},
                         verify_delivery=lambda snap, rec: dv.verify_delivery(store, delivery_ref=ref, snapshot=snap,
                                                                             record=rec),
                         now=now)
    return {**result, "delivery": {"manifest": ref}, "members": sorted(members)}
