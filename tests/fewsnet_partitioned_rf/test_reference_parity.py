import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from fewsnet_partitioned_rf_pipeline.core.inference import (
    predict_partition_probabilities,
)
from fewsnet_partitioned_rf_pipeline.core.training import train_partition_models


def _assert_probability_parity(actual, expected):
    assert np.allclose(actual, expected, atol=1e-12, rtol=0.0)


def _load_fixture_builder():
    generator_path = (
        Path(__file__).resolve().parents[2]
        / "tools/build_fewsnet_stage3_parity_fixture.py"
    )
    spec = importlib.util.spec_from_file_location(
        "task11_fewsnet_stage3_parity_fixture_builder",
        generator_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_reference_package(reference_root: Path, module_source: str) -> None:
    scripts = reference_root / "scripts"
    scripts.mkdir()
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    (scripts / "compare_partitioned_vs_pooled_rf_k40_nc4.py").write_text(
        module_source,
        encoding="utf-8",
    )


def _isolate_reference_import(monkeypatch, reference_module: str) -> None:
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delitem(sys.modules, "scripts", raising=False)
    monkeypatch.delitem(sys.modules, reference_module, raising=False)


def test_probability_parity_rejects_default_relative_tolerance_gap():
    with pytest.raises(AssertionError):
        _assert_probability_parity(
            np.asarray([1.000005]),
            np.asarray([1.0]),
        )


@pytest.mark.parametrize("prior_state", [False, True])
def test_reference_import_suppresses_bytecode_and_restores_prior_state(
    tmp_path,
    monkeypatch,
    prior_state,
):
    builder = _load_fixture_builder()
    _write_reference_package(
        tmp_path,
        """
RF_PARAMS = {"n_estimators": 1}

def train_pooled_model(*args, **kwargs):
    return None

def train_partitioned_model(*args, **kwargs):
    return None

def predict_partitioned_probability(*args, **kwargs):
    return None
""".lstrip(),
    )
    _isolate_reference_import(monkeypatch, builder.REFERENCE_MODULE)
    monkeypatch.setattr(sys, "dont_write_bytecode", prior_state)

    builder._reference_functions(tmp_path)

    assert sys.dont_write_bytecode is prior_state
    assert sorted(tmp_path.rglob("*.pyc")) == []


@pytest.mark.parametrize("prior_state", [False, True])
def test_reference_import_restores_prior_state_after_exception(
    tmp_path,
    monkeypatch,
    prior_state,
):
    builder = _load_fixture_builder()
    _write_reference_package(
        tmp_path,
        """
import sys

if not sys.dont_write_bytecode:
    raise AssertionError("bytecode writes were not disabled before import")
raise RuntimeError("intentional reference import failure")
""".lstrip(),
    )
    _isolate_reference_import(monkeypatch, builder.REFERENCE_MODULE)
    monkeypatch.setattr(sys, "dont_write_bytecode", prior_state)

    with pytest.raises(RuntimeError, match="intentional reference import failure"):
        builder._reference_functions(tmp_path)

    assert sys.dont_write_bytecode is prior_state


def test_partition_training_matches_frozen_reference_fixture():
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures/fewsnet_partitioned_rf/stage3_reference_parity.json"
    )
    payload = json.loads(fixture.read_text())
    models = train_partition_models(
        np.asarray(payload["X_train"], dtype=float),
        np.asarray(payload["y_train"], dtype=int),
        np.asarray(payload["groups_train"], dtype=int),
        min_samples=int(payload["min_samples"]),
    )
    probability = predict_partition_probabilities(
        models.partition_models,
        models.pooled_model,
        np.asarray(payload["X_test"], dtype=float),
        np.asarray(payload["groups_test"], dtype=int),
    )
    _assert_probability_parity(
        probability,
        payload["expected_probability"],
    )
    assert models.partition_status == {
        int(key): value
        for key, value in payload["expected_partition_status"].items()
    }
    assert (probability >= payload["threshold"]).astype(int).tolist() == payload[
        "expected_class"
    ]
