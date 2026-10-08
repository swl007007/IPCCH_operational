import pytest

from cloud.common import object_refs


def test_sha256_file_returns_hex_digest(tmp_path):
    target = tmp_path / "artifact.txt"
    target.write_text("ipcch\n")

    assert (
        object_refs.sha256_file(target)
        == "2864ca48237934c19adfdefcecaedb5a130230f0cdb811e302c7567ffe9dfd8d"
    )


def test_required_artifact_accepts_generation_or_checksum():
    assert object_refs.has_immutable_reference({"required": True, "generation": "12"})
    assert object_refs.has_immutable_reference(
        {
            "required": True,
            "checksum": "a" * 64,
            "checksum_algorithm": "sha256",
        }
    )


def test_required_artifact_without_reference_fails():
    with pytest.raises(object_refs.ImmutableReferenceError):
        object_refs.require_immutable_reference(
            {
                "artifact_id": "scaffold",
                "required": True,
                "uri": "gs://bucket/scaffold.csv",
            }
        )


def test_image_digest_must_be_digest_pinned():
    assert object_refs.is_digest_pinned_image("us/pkg/image@sha256:" + "a" * 64)
    assert not object_refs.is_digest_pinned_image("us/pkg/image:latest")


def test_normalize_gcs_ref_records_generation_and_checksum():
    ref = object_refs.normalize_gcs_ref(
        "gs://bucket/path/file.csv",
        generation="123",
        checksum="b" * 64,
        checksum_algorithm="sha256",
    )

    assert ref == {
        "uri": "gs://bucket/path/file.csv",
        "generation": "123",
        "checksum": "b" * 64,
        "checksum_algorithm": "sha256",
    }
