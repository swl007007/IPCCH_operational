"""MLflow DatasetInput for a published validity-pooled run (task 10-17-ipcch-idp-augmented-pooled).

Only recipes that declare ``dataset_input`` use this; it runs inside ``publication._finalize`` after the artifacts are
logged and before the completion flags, so a failure leaves the publication incomplete and recoverable. The dataset
is the run's own modeling row index ``contexts/arm_rows.csv.gz`` (context ``modeling_panel_index``): a row index, not
the complete X/y. Input tags point at the source manifest/IDP source hashes and generations, the memberships and the
local-IDP ledger. An identical association is a no-op; a conflicting same-key association or a lost prior input stops.
The same step records the LoggedModel as the run's model output (``source_run_id`` alone leaves the run's logged-model
field empty in the UI) and logs the model's Dataset metric: MLflow 3.17's Models view derives a LoggedModel's Dataset
only from its metrics' dataset_name/dataset_digest, so the DatasetInput alone leaves that column empty (task 10-18).
"""
import gzip
import hashlib
import io
import json
import os

COLUMNS = (("row", "long"), ("admin_code", "long"), ("target_ord", "long"), ("label_kind", "string"),
           ("source_family", "long"), ("source_available_ord", "long"))
CONTEXT = "modeling_panel_index"
SEMANTICS = ("arm-specific modeling row index (row -> admin_code, target_ord, label_kind, source_family, source availability) "
             "used by every annual context of this run; it is not the complete X/y dataset; annual fitting/calibration/scoring "
             "memberships are in memberships.npz and the local-IDP feature values in the idp ledger")
ALL_LABEL_ARMS = frozenset({"validity_augmented", "validity_augmented_idp", "validity_augmented_idp_hstack",
                            # task 10-19 refresh arms (all labels, local-IDP features)
                            "validity_augmented_idp_202610", "validity_augmented_idp_202610_hindcast2325",
                            "validity_augmented_idp_202610_rolling36",
                            # task 10-20 aggregated-ACLED candidate (augmented labels; paired with the production run)
                            "validity_augmented_idp_202610_acledagg_lag1_uncal",
                            # task 10-21 tuned aggregated-ACLED arm (formal refits; augmented labels)
                            "validity_augmented_idp_202610_acledagg_lag1_uncal_hpt"})
# Descriptive row count of the DatasetInput (not a score), linked to the LoggedModel; same key as the 2026-10-17 repair.
MODEL_DATASET_METRIC = "dataset.modeling_panel_index.rows"


def object_generation(uri, project=None):
    """GCS generation of an existing object, or None for a local path."""
    if not uri.startswith("gs://"):
        return None
    from research_cloud.training.common import storage_client, TARGET_PROJECT
    bucket, _, name = uri[5:].partition("/")
    blob = storage_client(project or TARGET_PROJECT).bucket(bucket).blob(name)
    blob.reload()
    return str(blob.generation)


# MLflow keys an experiment's datasets by (name, digest) and keeps the first source: a family that publishes the
# identical keyed cohort (same content digest) into the same experiment as the validity baseline needs its own dataset
# name, or its run is linked to the baseline's dataset entity (task 10-18 F0).
DATASET_TITLES = {"ipcch_direct_fourclass": "IPCCH direct four-class"}


def payload(root, record, generation=object_generation):
    """Validated dataset/input-tag payload for one saved trial directory (``root``) and its record."""
    import numpy as np
    import pandas as pd
    cfg, h = record["config"], int(record["config"]["horizon"])
    arm = cfg["arm"]
    prefix = record["output"].rstrip("/")
    content = gzip.decompress(open(os.path.join(root, "contexts", "arm_rows.csv.gz"), "rb").read())
    full = hashlib.sha256(content).hexdigest()
    rows = pd.read_csv(io.BytesIO(content), keep_default_na=False)
    if list(rows.columns) != [c for c, _ in COLUMNS]:
        raise ValueError(f"arm_rows columns {list(rows.columns)}")
    region = cfg.get("region")
    labels = pd.read_csv(os.path.join(root, "dataset", "labels.csv.gz"), keep_default_na=False, na_values=[""],
                         dtype={"anl_id": str, "iso2": str},
                         usecols=["admin_code", "month_ord", "label_kind", "source_family", "source_available_ord",
                                  *(["iso2"] if region else [])])
    proj = (labels if arm in ALL_LABEL_ARMS else labels[labels["label_kind"] == "original"]).reset_index(drop=True)
    if region:      # SA-local (task 10-17): the projection is restricted to the region's countries; 'NA' is Namibia
        proj = proj[proj["iso2"].isin(list(region["iso2"]))].reset_index(drop=True)
    if not (np.array_equal(rows["row"].to_numpy(), np.arange(len(rows))) and len(rows) == len(proj)
            and np.array_equal(rows["admin_code"].to_numpy(), proj["admin_code"].to_numpy())
            and np.array_equal(rows["target_ord"].to_numpy(), proj["month_ord"].to_numpy())
            and np.array_equal(rows["label_kind"].astype(str).to_numpy(), proj["label_kind"].astype(str).to_numpy())
            and np.array_equal(rows["source_family"].to_numpy(), proj["source_family"].to_numpy())
            and np.array_equal(rows["source_available_ord"].to_numpy(), proj["source_available_ord"].to_numpy())):
        raise ValueError("arm_rows is not the arm-selected labels projection with a sequential row index")
    spec = cfg["dataset_input"]
    ledger_rel = spec["idp_ledger"].format(h=h)
    for rel in ("contexts/arm_rows.csv.gz", "contexts/memberships.npz", ledger_rel):
        if not os.path.exists(os.path.join(root, rel)):
            raise ValueError(f"dataset pointer {rel} is not a saved trial output")
    manifest = record.get("input_manifest") or {}
    files = (manifest.get("content") or {}).get("files") or {}
    src = files.get(spec["source_role"])
    if not src or not src.get("sha256"):
        raise ValueError(f"input manifest lacks the {spec['source_role']} source")
    kinds = rows["label_kind"].value_counts().to_dict()
    uri = f"{prefix}/contexts/arm_rows.csv.gz"
    tags = {"mlflow.data.context": CONTEXT, "semantics": SEMANTICS, "content.sha256": full, "arm": arm, "lead_months": f"{h:02d}",
            "gcs.generation": generation(uri) or "local",
            "memberships.uri": f"{prefix}/contexts/memberships.npz",
            "memberships.gcs.generation": generation(f"{prefix}/contexts/memberships.npz") or "local",
            "idp_ledger.uri": f"{prefix}/{ledger_rel}", "idp_ledger.gcs.generation": generation(f"{prefix}/{ledger_rel}") or "local",
            "idp_ledger.sha256": hashlib.sha256(open(os.path.join(root, ledger_rel), "rb").read()).hexdigest(),
            "input_manifest.sha256": manifest.get("sha256") or "unavailable",
            "idp_source.uri": src["uri"], "idp_source.sha256": src["sha256"],
            "idp_source.gcs.generation": str(src.get("gcs_generation", "local")),
            "label_kind_counts": json.dumps(kinds, sort_keys=True)}
    if region:
        tags.update({"region": region["name"], "region_iso2": ",".join(region["iso2"])})
    scope = f"{region['name']} | " if region else ""
    title = DATASET_TITLES.get((record.get("identity") or {}).get("family"), "IPCCH validity")
    corrected = cfg.get("corrected_input") or cfg.get("ch_correction")
    if corrected:   # task 10-27: a corrected-input refit keeps the original run's row index (same digest) but not its inputs;
        title = f"{title} ({corrected['data_version']})"   # its own dataset entity, never the original run's
    if cfg.get("ch_correction"):    # task 10-28: the CH links input and lineage counts identify the label preparation
        ch_src = files.get("ch_links") or {}
        if not ch_src.get("sha256"):
            raise ValueError("input manifest lacks the ch_links source")
        tags.update({"ch_links.uri": ch_src["uri"], "ch_links.sha256": ch_src["sha256"],
                     "ch_links.gcs.generation": str(ch_src.get("gcs_generation", "local")),
                     "ch_correction.data_version": cfg["ch_correction"]["data_version"]})
    return {"dataset": {"name": f"{title} | {scope}{arm} | H{h:02d} | modeling panel index", "digest": full[:32], "source_type": "gs" if uri.startswith("gs://") else "local",
                        "source": json.dumps({"uri": uri}),
                        "schema": json.dumps({"mlflow_colspec": [{"name": c, "type": t} for c, t in COLUMNS]}),
                        "profile": json.dumps({"num_rows": int(len(rows)), "num_elements": int(len(rows) * len(COLUMNS))})},
            "input_tags": tags}


def entity(p):
    from mlflow.entities import Dataset, DatasetInput, InputTag
    d = p["dataset"]
    return DatasetInput(dataset=Dataset(name=d["name"], digest=d["digest"], source_type=d["source_type"], source=d["source"],
                                        schema=d["schema"], profile=d["profile"]),
                        tags=[InputTag(k, v) for k, v in sorted(p["input_tags"].items())])


def existing_match(run, p):
    """None if the dataset key is absent; True if an identical association exists; raise on a conflicting one."""
    d = p["dataset"]
    for di in (run.inputs.dataset_inputs if run.inputs else []):
        ds = di.dataset
        if ds.name == d["name"] and ds.digest == d["digest"]:
            same = (ds.source_type == d["source_type"] and ds.source == d["source"] and ds.schema == d["schema"]
                    and ds.profile == d["profile"] and {t.key: t.value for t in di.tags} == p["input_tags"])
            if not same:
                raise ValueError(f"dataset {d['name']}/{d['digest']} exists on the run with different metadata")
            return True
    return None


def signatures(run):
    return sorted(json.dumps({"name": di.dataset.name, "digest": di.dataset.digest, "source": di.dataset.source,
                              "tags": sorted((t.key, t.value) for t in di.tags)}, sort_keys=True)
                  for di in (run.inputs.dataset_inputs if run.inputs else []))


def associate(c, experiment_id, run_id, identity, p):
    """Log ``p`` on the run unless identical, then read back the run and its scoped experiment search."""
    run = c.get_run(run_id)
    before = signatures(run)
    already = existing_match(run, p)
    if not already:
        c.log_inputs(run_id, datasets=[entity(p)])
    after = c.get_run(run_id)
    if existing_match(after, p) is not True:
        raise ValueError("dataset input readback mismatch")
    if not set(before) <= set(signatures(after)):
        raise ValueError("a prior dataset input was lost")
    found = [r for r in c.search_runs([experiment_id], filter_string=f"tags.`publication.identity` = '{identity}'")
             if r.info.run_id == run_id]
    if len(found) != 1 or existing_match(found[0], p) is not True:
        raise ValueError("experiment search does not show the dataset input")
    return {"action": "noop_identical" if already else "logged", "name": p["dataset"]["name"], "digest": p["dataset"]["digest"],
            "content.sha256": p["input_tags"]["content.sha256"], "search_readback": True}


def link_model_output(c, run_id, model_id):
    """Record the LoggedModel as the run's model output (shown as the run's logged model in the UI); idempotent,
    read back. ``source_run_id`` alone does not populate run outputs."""
    from mlflow.entities import LoggedModelOutput

    def outputs(run):
        return [o.model_id for o in (run.outputs.model_outputs if run.outputs else [])]

    present = model_id in outputs(c.get_run(run_id))
    if not present:
        c.log_outputs(run_id, models=[LoggedModelOutput(model_id=model_id, step=0)])
    if model_id not in outputs(c.get_run(run_id)):
        raise ValueError("run model output readback mismatch")
    return {"action": "noop_identical" if present else "logged", "model_id": model_id}


def model_dataset_check(model, p):
    """Is the LoggedModel's Models-view Dataset exactly this DatasetInput? One ``MODEL_DATASET_METRIC`` with the
    input's row count, step 0, name/digest and the model_id; no metric on the model names another dataset."""
    d = p["dataset"]
    want = (float(json.loads(d["profile"])["num_rows"]), 0, d["name"], d["digest"], model.model_id)
    metrics = [{"key": m.key, "value": m.value, "step": m.step, "dataset_name": getattr(m, "dataset_name", None),
                "dataset_digest": getattr(m, "dataset_digest", None), "model_id": getattr(m, "model_id", None)}
               for m in (model.metrics or [])]
    mine = [m for m in metrics if m["key"] == MODEL_DATASET_METRIC]
    problems = []
    if len(mine) != 1:
        problems.append(f"{len(mine)} {MODEL_DATASET_METRIC} metrics on the model")
    problems += [f"conflicting {m}" for m in mine
                 if (m["value"], m["step"], m["dataset_name"], m["dataset_digest"], m["model_id"]) != want]
    problems += [f"other dataset on {m['key']}: {m['dataset_name']}/{m['dataset_digest']}" for m in metrics
                 if m["dataset_name"] is not None and (m["dataset_name"], m["dataset_digest"]) != (d["name"], d["digest"])]
    return {"ok": not problems, "metrics": mine, "problems": problems}


def log_model_dataset(c, run_id, model_id, p):
    """Log the model's Dataset metric unless identical, then read the LoggedModel back; a conflicting one stops."""
    d = p["dataset"]
    have = model_dataset_check(c.get_logged_model(model_id), p)
    present = bool(have["metrics"])
    if present and not have["ok"]:
        raise ValueError(f"model Dataset metric conflict: {have['problems']}")
    if not present:
        c.log_metric(run_id, MODEL_DATASET_METRIC, float(json.loads(d["profile"])["num_rows"]), step=0,
                     dataset_name=d["name"], dataset_digest=d["digest"], model_id=model_id, synchronous=True)
    after = model_dataset_check(c.get_logged_model(model_id), p)
    if not after["ok"]:
        raise ValueError(f"model Dataset metric readback mismatch: {after['problems']}")
    return {"action": "noop_identical" if present else "logged", "key": MODEL_DATASET_METRIC, "value": after["metrics"][0]["value"],
            "dataset_name": d["name"], "dataset_digest": d["digest"]}
