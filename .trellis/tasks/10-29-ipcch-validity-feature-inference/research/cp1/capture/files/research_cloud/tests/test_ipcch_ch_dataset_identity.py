"""CH-correction DatasetInput identity (task 10-28, SQLite MLflow).

A CH-correction refit names its modeling panel index after its own data version (never the GOSIF-v3 run's name) and
tags the ch_links input that defines its label preparation; the repaired association logic of task 10-27 is reused.
"""
import json

import pytest

from research_cloud.tests.test_training_validity_integration import (  # noqa: F401 - pytest fixtures
    BASELINE, assert_model_dataset, card, dashboard_trial, idp_trial)

ARM = "validity_augmented_idp_202610_acledagg_lag1_uncal_hpt"
VERSION = "gosif-v3-input-20261027+ch-validity-20261028"
LINKS = {"uri": "gs://bucket/inputs/ch-validity-20261028/ch_links.csv.gz", "sha256": "a" * 64, "gcs_generation": "123"}


def ch_record(root, links=True):
    record = json.loads((root / "trial.json").read_text())
    c = card(feature_set="compact282+ae128+acledagg114_lag1+idp_local3", model_type="XGBoost regressor quartet (no calibration)")
    c.update(family_title="Validity-augmented pooled (GOSIF v3 + CH validity 20261028)", arm=ARM)
    record["config"].update(model_card=c, arm=ARM, mode="formal", baseline={**BASELINE, "arm": ARM, "relation": "CH correction"},
                            ch_correction={"kind": "ch_validity_correction", "data_version": VERSION})
    if links:
        record["input_manifest"]["content"]["files"]["ch_links"] = LINKS
    (root / "trial.json").write_text(json.dumps(record))
    return record


def test_ch_correction_names_its_own_dataset_and_tags_ch_links(idp_trial):
    from research_cloud.training import dataset_input
    root, client, eid, content = idp_trial
    plain = dataset_input.payload(root, json.loads((root / "trial.json").read_text()))
    p = dataset_input.payload(root, ch_record(root))
    assert p["dataset"]["name"] == f"IPCCH validity ({VERSION}) | {ARM} | H00 | modeling panel index"
    assert p["dataset"]["name"] != f"IPCCH validity (gosif-v3-input-20261027) | {ARM} | H00 | modeling panel index"
    assert (p["input_tags"]["ch_links.sha256"], p["input_tags"]["ch_links.uri"], p["input_tags"]["ch_links.gcs.generation"]) == (
        LINKS["sha256"], LINKS["uri"], LINKS["gcs_generation"])
    assert p["input_tags"]["ch_correction.data_version"] == VERSION
    extra = {"arm", "ch_links.uri", "ch_links.sha256", "ch_links.gcs.generation", "ch_correction.data_version"}
    assert {k: v for k, v in p["input_tags"].items() if k not in extra} == {k: v for k, v in plain["input_tags"].items() if k != "arm"}


def test_ch_correction_without_ch_links_source_is_refused(idp_trial):
    from research_cloud.training import dataset_input
    root, client, eid, content = idp_trial
    with pytest.raises(ValueError, match="ch_links"):
        dataset_input.payload(root, ch_record(root, links=False))


def test_ch_correction_publishes_one_own_dataset(idp_trial):
    from research_cloud.training import dataset_input, publication
    root, client, eid, content = idp_trial
    record = ch_record(root)
    p = dataset_input.payload(root, record)
    state = publication.finalize(root, experiment="IPCCH dashboard", client=client)
    assert state["status"] == "complete" and state["dataset_input"]["action"] == "logged"
    (di,) = client.get_run(state["run_id"]).inputs.dataset_inputs
    assert (di.dataset.name, di.dataset.digest) == (p["dataset"]["name"], p["dataset"]["digest"])
    assert {t.key: t.value for t in di.tags}["ch_links.sha256"] == LINKS["sha256"]
    assert_model_dataset(client, state, p["dataset"]["name"], p["dataset"]["digest"], 3.0)
