"""Corrected-input DatasetInput identity (task 10-27, SQLite MLflow).

The GOSIF v3 refit keeps the original formal run's labels, cohort and row index, so its modeling panel index has the
same content digest as the original run's dataset in the same experiment. MLflow keys an experiment's datasets by
(name, digest) and keeps the first source: under the shared validity name the refit's run is linked to the original
run's dataset entity and the readback refuses it (formal H6/H0 jobs of 2026-10-28). The refit names its own dataset
after its corrected data version; records without ``corrected_input`` keep the previous name.
"""
import copy
import json

import pytest

from research_cloud.tests.test_training_validity_integration import (  # noqa: F401 - pytest fixtures
    BASELINE, assert_model_dataset, card, dashboard_trial, idp_trial)

ARM = "validity_augmented_idp_202610_acledagg_lag1_uncal_hpt"
VERSION = "gosif-v3-input-20261027"
RELATION = "fixed-parameter refit of the original formal run on a corrected GPP input; every other input unchanged"
ORIGINAL_SRC = json.dumps({"uri": "gs://bucket/trials/ipcch_validity_pooled/5555555555555555555/trial-0/contexts/arm_rows.csv.gz"})


def corrected(root):
    record = json.loads((root / "trial.json").read_text())
    c = card(feature_set="compact282+ae128+oracle12+acledagg114_lag1+idp_local3", model_type="XGBoost regressor quartet (no calibration)")
    c.update(family_title="Validity-augmented pooled (GOSIF v3 20261027)", arm=ARM)
    record["config"].update(model_card=c, arm=ARM, mode="formal", baseline={**BASELINE, "arm": ARM, "relation": RELATION},
                            corrected_input={"kind": "gpp_input_replacement", "data_version": VERSION})
    (root / "trial.json").write_text(json.dumps(record))
    return record


def image_payload(real):
    """The payload of the image that ran the failed jobs: no corrected-input qualifier."""
    def legacy(root, record, **kw):
        plain = copy.deepcopy(record)
        plain["config"].pop("corrected_input")
        return real(root, plain, **kw)
    return legacy


def log_original(client, eid, p):
    """The original formal run's DatasetInput: same name and digest, its own source."""
    from mlflow.entities import Dataset, DatasetInput, InputTag
    run = client.create_run(eid).info.run_id
    d = p["dataset"]
    client.log_inputs(run, datasets=[DatasetInput(
        dataset=Dataset(name=d["name"], digest=d["digest"], source_type="gs", source=ORIGINAL_SRC, schema=d["schema"], profile=d["profile"]),
        tags=[InputTag("mlflow.data.context", "modeling_panel_index")])])
    return run


def test_corrected_input_names_its_own_dataset(idp_trial):
    from research_cloud.training import dataset_input
    root, client, eid, content = idp_trial
    plain = json.loads((root / "trial.json").read_text())
    before = dataset_input.payload(root, plain)
    assert before["dataset"]["name"] == "IPCCH validity | validity_augmented_idp | H00 | modeling panel index"
    record = corrected(root)
    p = dataset_input.payload(root, record)
    assert p["dataset"]["name"] == f"IPCCH validity ({VERSION}) | {ARM} | H00 | modeling panel index"
    assert image_payload(dataset_input.payload)(root, record)["dataset"]["name"] == f"IPCCH validity | {ARM} | H00 | modeling panel index"
    assert p["dataset"]["digest"] == before["dataset"]["digest"] and p["input_tags"] == before["input_tags"] | {"arm": ARM}


def test_corrected_input_publishes_beside_the_original_dataset(idp_trial):
    from research_cloud.training import dataset_input, publication
    root, client, eid, content = idp_trial
    record = corrected(root)
    p = dataset_input.payload(root, record)
    original = log_original(client, eid, image_payload(dataset_input.payload)(root, record))
    state = publication.finalize(root, experiment="IPCCH dashboard", client=client)
    assert state["status"] == "complete" and state["dataset_input"]["action"] == "logged"
    (di,) = client.get_run(state["run_id"]).inputs.dataset_inputs
    assert (di.dataset.name, di.dataset.digest, di.dataset.source) == (p["dataset"]["name"], p["dataset"]["digest"], p["dataset"]["source"])
    assert_model_dataset(client, state, p["dataset"]["name"], p["dataset"]["digest"], 3.0)
    (oi,) = client.get_run(original).inputs.dataset_inputs
    assert oi.dataset.source == ORIGINAL_SRC and oi.dataset.name == f"IPCCH validity | {ARM} | H00 | modeling panel index"


def test_failed_corrected_publication_recovers_same_ids(idp_trial, monkeypatch):
    """The failure of the formal jobs and its recovery: the image's finalize links the run to the original dataset
    entity and stops (run/model FAILED, version created, journal released); a resumed finalize with the corrected
    name completes on the same run/model/version, keeps that legacy association as logged (this trial's tags, the
    original entity's source), adds exactly one input with this trial's own source and leaves the original untouched."""
    from research_cloud.training import dataset_input, publication
    root, client, eid, content = idp_trial
    record = corrected(root)
    real = dataset_input.payload
    new, legacy = real(root, record), image_payload(real)(root, record)
    original = log_original(client, eid, legacy)
    monkeypatch.setattr(dataset_input, "payload", image_payload(real))
    with pytest.raises(ValueError, match="exists on the run with different metadata"):
        publication.finalize(root, experiment="IPCCH dashboard", client=client)
    failed = json.loads((root / "publication.json").read_text())
    assert failed["status"] == "incomplete" and "owner" not in failed and failed["model_version"] == "1"
    rid, mid = failed["run_id"], failed["model_id"]
    assert client.get_run(rid).info.status == "FAILED" and str(client.get_logged_model(mid).status).endswith("FAILED")
    monkeypatch.setattr(dataset_input, "payload", real)
    state = publication.finalize(root, experiment="IPCCH dashboard", client=client)
    assert state["status"] == "complete" and (state["run_id"], state["model_id"]) == (rid, mid)
    assert (state["registered_model"], state["model_version"]) == (failed["registered_model"], failed["model_version"])
    run, model = client.get_run(rid), client.get_logged_model(mid)
    version = client.get_model_version(state["registered_model"], state["model_version"])
    assert run.info.status == "FINISHED" and str(model.status).endswith("READY")
    assert all(t.get("publication.status") == "complete" for t in (run.data.tags, model.tags, version.tags))
    got = {(x.dataset.name, x.dataset.source): {t.key: t.value for t in x.tags} for x in run.inputs.dataset_inputs}
    assert set(got) == {(legacy["dataset"]["name"], ORIGINAL_SRC), (new["dataset"]["name"], new["dataset"]["source"])}
    assert all(tags == new["input_tags"] for tags in got.values())
    assert dataset_input.existing_match(run, new) is True
    assert_model_dataset(client, state, new["dataset"]["name"], new["dataset"]["digest"], 3.0)
    (oi,) = client.get_run(original).inputs.dataset_inputs
    assert (oi.dataset.name, oi.dataset.source) == (legacy["dataset"]["name"], ORIGINAL_SRC)
    again = publication.finalize(root, experiment="IPCCH dashboard", client=client)
    assert again["status"] == "complete" and again["dataset_input"]["action"] == "noop_identical"
    assert len(client.get_run(rid).inputs.dataset_inputs) == 2
    assert len(client.search_logged_models(experiment_ids=[eid])) == 1
