import json
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy/october_delivery"
sys.path.insert(0, str(DEPLOY))
from migration_package import extract, safe_path, sha256, verify, write_json  # noqa: E402
from migration_destination import check_refs, prepare_request, upload_file  # noqa: E402


def sealed(tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    (root / "payload").write_bytes(b"fixed")
    write_json(
        root / "inventory.json",
        {"files": {"payload": {"size": 5, "sha256": sha256(root / "payload")}}},
    )
    return root


def test_inventory_missing_extra_changed(tmp_path):
    root = sealed(tmp_path)
    assert len(verify(root)["files"]) == 1
    (root / "extra").write_text("x")
    with pytest.raises(ValueError, match="inventory mismatch"):
        verify(root)
    (root / "extra").unlink()
    (root / "payload").write_bytes(b"wrong")
    with pytest.raises(ValueError, match="checksum"):
        verify(root)
    (root / "payload").unlink()
    with pytest.raises(ValueError, match="inventory mismatch"):
        verify(root)


@pytest.mark.parametrize(
    "name", ["../bad", "/bad", "a/../bad", "C:/bad", "a\\b", "./x"]
)
def test_unsafe_paths(name):
    with pytest.raises(ValueError):
        safe_path(name)


def test_archive_relocation_and_duplicates(tmp_path):
    root = sealed(tmp_path)
    archive = tmp_path / "valid.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for p in root.iterdir():
            tar.add(p, arcname=p.name)
    assert extract(archive, tmp_path / "relocated") == verify(root)
    archive = tmp_path / "duplicate.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for _ in range(2):
            tar.add(root / "payload", arcname="payload")
    with pytest.raises(ValueError, match="duplicate"):
        extract(archive, tmp_path / "bad")


def test_upload_uses_actual_generation_and_create_only(tmp_path):
    path = tmp_path / "asset"
    path.write_text("value")
    calls = []

    class Blob:
        generation = 981

        def upload_from_filename(self, path, **kw):
            calls.append(kw)

    client = SimpleNamespace(
        bucket=lambda name: SimpleNamespace(blob=lambda name: Blob())
    )
    ref = upload_file(client, "new-bucket", "new/asset", path)
    assert ref == {
        "uri": "gs://new-bucket/new/asset",
        "generation": "981",
        "sha256": sha256(path),
    }
    assert calls == [{"if_generation_match": 0}]


def test_prepare_rebuilds_destination_refs():
    from cloud.batch.remote_sources import SYSTEM_FAMILIES

    refs = {}
    for s in SYSTEM_FAMILIES:
        for name in ["geometry.geojson", "roster.csv"] + [
            f"history/{f}.csv" for f in SYSTEM_FAMILIES[s]
        ]:
            key = f"assets/{s}/{name}"
            refs[key] = {
                "uri": f"gs://new-bucket/{key}",
                "generation": "981",
                "sha256": "a" * 64,
            }
    args = SimpleNamespace(
        prepare_id="prepare-001",
        origin="2026-10",
        cutoff="2026-10-08T23:59:59Z",
        operator="test",
    )
    body, uri = prepare_request({"BUCKET": "new-bucket"}, refs, args)
    assert uri == "gs://new-bucket/prepare_requests/prepare-001/prepare_request.json"
    assert (
        body["systems"]["ipcch"]["history"]["evi"]
        == refs["assets/ipcch/history/evi.csv"]
    )
    assert ".trellis" not in json.dumps(body)


def test_rejects_original_bucket_or_wrong_hash():
    inventory = {"files": {"assets/x": {"sha256": "a" * 64}}}
    ref = {"uri": "gs://old-bucket/x", "generation": "12", "sha256": "a" * 64}
    with pytest.raises(ValueError):
        check_refs(None, {"BUCKET": "new-bucket"}, {"assets/x": ref}, inventory)


def test_dry_run_never_opens_cloud_client(tmp_path, monkeypatch, capsys):
    import migration_destination as md

    root = sealed(tmp_path)
    values = {
        "PROJECT": "new-project",
        "REGION": "us-central1",
        "BUCKET": "new-bucket",
        "REQUEST_BUCKET": "new-requests",
        "SA": "runtime@example.test",
        "WORKFLOW_SA": "workflow@example.test",
        "NAMESPACE": "new-stage",
        "IMAGE": "us-central1-docker.pkg.dev/new-project/images/runtime@sha256:"
        + "a" * 64,
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", None)
    work = tmp_path / "work"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "migration_destination.py",
            "upload",
            "--package",
            str(root),
            "--work",
            str(work),
        ],
    )
    md.main()
    assert json.loads(capsys.readouterr().out)["mode"] == "dry-run"
    assert not work.exists()
    verify(root)


def test_delivery_requires_exact_runtime_verification(tmp_path):
    from migration_destination import delivery_request

    root = sealed(tmp_path)
    (root / "runtime").mkdir()
    (root / "runtime/requirements.lock.txt").write_text("frozen")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}")
    args = SimpleNamespace(runtime_verification=str(receipt))
    with pytest.raises(ValueError, match="runtime equivalence"):
        delivery_request(
            root, {"IMAGE": "new-image@sha256:" + "a" * 64}, {}, args, None
        )
