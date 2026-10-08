import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("handover_package", Path(__file__).resolve().parents[1] / "deploy/handover_package.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def test_exact_archive_and_source_remains_writable(tmp_path, monkeypatch):
    root = tmp_path / "source"; root.mkdir()
    (root / "payload.txt").write_text("accepted bytes")
    monkeypatch.setattr(package, "MEMBERS", ("payload.txt",))
    archive = tmp_path / "handover.tar.gz"
    inventory = package.build(root, archive)
    assert package.verify(archive) == inventory
    (root / "payload.txt").write_text("next operational version")
    assert package.verify(archive) == inventory
    with pytest.raises(FileExistsError):
        package.build(root, archive)


@pytest.mark.parametrize("name", ["../x", "/x", "a/../b", "C:/x", "a\\b"])
def test_unsafe_member(name):
    with pytest.raises(ValueError):
        package.safe_path(name)
