"""Task 10-29 R60/D3: the v2 FEWS NET member is checked with the existing FEWS-scoped delivery checks (headers,
native keys/roster, predictions, country tables, diagnostics/availability, frozen inputs) and its exact 0/6/12 package
identities - in the writer AND again by the actual publication verifier (Supervisor finding 5 on 6d8ea08)."""

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import delivery_v2 as dv
from cloud.ipcch import fews_v2
from cloud.ipcch import publication as pub
from cloud.ipcch import release_v2 as rv
from tests.cloud import fews_member_fixture as fmf

ROOT = "gs://ops-delivery/root"
REQ = {"uri": "gs://ops/requests/r/run_manifest.json", "generation": "1", "sha256": "a" * 64}
NOW = datetime(2026, 10, 31, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def fixture(tmp_path_factory):
    return fmf.build(tmp_path_factory.mktemp("fews"))


def write(fixture, out, damage=None, packages=None):
    def score(spec, system, target):
        fmf.score_from(fixture)(spec, system, target)
        if damage:
            damage(target)
    return fews_v2.write_member(out, score=score, spec_path=out.parent / "spec.json", origin=fmf.ORIGIN,
                                packages=fixture["packages"] if packages is None else packages, mode="real")


def edit_csv(path, change):
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    change(frame)
    frame.to_csv(path, index=False, lineterminator="\n")


DAMAGE = {
    "country_value": lambda o: edit_csv(o / "scopes/6m/fewsnet/country_predictions.csv",
                                        lambda f: f.__setitem__(f.columns[3], "0.987654")),
    "header": lambda o: edit_csv(o / "scopes/0m/fewsnet/polygon_confidence.csv",
                                 lambda f: f.rename(columns={f.columns[-1]: "renamed"}, inplace=True)),
    "frozen_input": lambda o: (o / "inputs/fewsnet_scope_12m_inference.csv").unlink(),
    "roster_row": lambda o: edit_csv(o / "scopes/0m/fewsnet/polygon_predictions.csv",
                                     lambda f: f.drop(index=f.index[-1], inplace=True)),
    "availability": lambda o: edit_csv(o / "reports/fewsnet_diagnostic_availability.csv",
                                       lambda f: f.drop(index=f.index[0], inplace=True)),
}


def test_valid_member_writes_and_records_exact_packages(fixture, tmp_path):
    record = write(fixture, tmp_path / "out")
    assert record["origin_month"] == fmf.ORIGIN and record["model_package"] == fixture["inventory"]


@pytest.mark.parametrize("damage", sorted(DAMAGE))
def test_writer_refuses_damaged_members(fixture, tmp_path, damage):
    with pytest.raises(fews_v2.FewsMemberError):
        write(fixture, tmp_path / "out", DAMAGE[damage])


def test_writer_refuses_missing_packages(fixture, tmp_path):
    with pytest.raises(fews_v2.FewsMemberError, match="exactly the"):
        write(fixture, tmp_path / "out", packages={})


def publish(store, fixture, tmp_path, run_id, damage=None, tamper_record=None):
    def member(out):
        record = write(fixture, out)
        if damage:
            damage(out)
        if tamper_record:
            tamper_record(record)
        return record
    return rv.publish_member_run(store, ROOT, system="fewsnet", namespace="prod", run_id=run_id, mode="real",
                                 publication="current", expected_pointer_generation="0", request_ref=REQ,
                                 write_member=member, workdir=str(tmp_path), now=NOW)


def test_actual_verifier_publishes_a_valid_member(fixture, tmp_path):
    store = LocalObjectStore(tmp_path / "gcs")
    out = publish(store, fixture, tmp_path, "fews-ok")
    assert out["status"] == "published"
    rec = pub.read_current(store, ROOT, "prod")["record"]
    assert rec["systems"]["fewsnet"]["model_package"] == fixture["inventory"]


@pytest.mark.parametrize("damage", sorted(DAMAGE))
def test_actual_verifier_refuses_damage_after_the_writer(fixture, tmp_path, damage):
    """Damage after the writer's own check (or a writer bypass) is refused by verify_delivery; pointer unchanged."""
    store = LocalObjectStore(tmp_path / "gcs")
    with pytest.raises(dv.DeliveryError, match="does not verify"):
        publish(store, fixture, tmp_path, "fews-bad", damage=DAMAGE[damage])
    assert pub.read_current(store, ROOT, "prod")["generation"] == "0"


@pytest.mark.parametrize("tamper", ["drop_horizon", "wrong_hash", "empty"])
def test_actual_verifier_binds_exact_package_identities(fixture, tmp_path, tamper):
    def change(record):
        inv = record["model_package"]
        if tamper == "drop_horizon":
            for k in [k for k in inv if k.startswith("12m/")]:
                del inv[k]
        elif tamper == "wrong_hash":
            inv[sorted(inv)[0]] = "0" * 64
        else:
            inv.clear()
    store = LocalObjectStore(tmp_path / "gcs")
    with pytest.raises(dv.DeliveryError, match="package_exact"):
        publish(store, fixture, tmp_path, "fews-pkg", tamper_record=change)
    assert pub.read_current(store, ROOT, "prod")["generation"] == "0"


@pytest.mark.parametrize("checksums", ["empty", "partial", "extra_self"])
def test_package_checksum_map_must_cover_every_content_file(fixture, tmp_path, checksums):
    """Supervisor residual on 4fd6146: checksums.json = {} (or a partial map, or one listing itself) with a
    self-consistent external inventory is refused by the writer AND the actual publication verifier."""
    import hashlib
    import shutil
    packages = {}
    for h, d in fixture["packages"].items():
        target = tmp_path / f"pkg-{h}m"
        shutil.copytree(d, target)
        good = json.loads((target / "checksums.json").read_text())
        bad = {"empty": {}, "partial": dict(list(good.items())[:2]),
               "extra_self": {**good, "checksums.json": "0" * 64}}[checksums]
        (target / "checksums.json").write_text(json.dumps(bad))
        packages[h] = target
    with pytest.raises(fews_v2.FewsMemberError, match="package_exact"):
        write(fixture, tmp_path / "out", packages=packages)

    def bypass(out):                                   # the writer's own check bypassed: the verifier still refuses
        fmf.score_from(fixture)(None, "fewsnet", out)
        inv = {}
        for h, d in packages.items():
            shutil.copytree(d, out / f"fewsnet/model_package/{h}m")
            inv.update({f"{h}m/{p.name}": hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.iterdir())})
        return {"contract": fews_v2.FEWS_CONTRACT, "origin_month": fmf.ORIGIN, "mode": "real",
                "model_horizons": [0, 6, 12], "model_package": inv}
    store = LocalObjectStore(tmp_path / "gcs")
    with pytest.raises(dv.DeliveryError, match="package_exact"):
        rv.publish_member_run(store, ROOT, system="fewsnet", namespace="prod", run_id="fews-sums", mode="real",
                              publication="current", expected_pointer_generation="0", request_ref=REQ,
                              write_member=bypass, workdir=str(tmp_path), now=NOW)
    assert pub.read_current(store, ROOT, "prod")["generation"] == "0"
