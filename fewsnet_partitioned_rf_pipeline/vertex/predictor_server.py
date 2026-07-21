"""Vertex custom prediction server for one validated FEWSNET model package."""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import uvicorn
from fastapi import Body, FastAPI, HTTPException

from fewsnet_partitioned_rf_pipeline.core.inference import PartitionedRFPredictor
from fewsnet_partitioned_rf_pipeline.core.package import (
    PACKAGE_FILES,
    load_model_package,
)
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    ArtifactStore,
    GCSArtifactStore,
)


def _localize_package(
    artifact_uri: str,
    store: ArtifactStore,
    package_dir: Path,
) -> None:
    artifact_root = artifact_uri.rstrip("/")
    for filename in PACKAGE_FILES:
        store.download_file(
            f"{artifact_root}/{filename}",
            package_dir / filename,
        )


def _validated_instances(
    payload: object,
    predictor: PartitionedRFPredictor,
) -> list[dict]:
    if not isinstance(payload, Mapping) or set(payload) != {"instances"}:
        raise HTTPException(
            status_code=400,
            detail="request body must contain exactly one instances field",
        )
    instances = payload["instances"]
    if not isinstance(instances, list) or not instances:
        raise HTTPException(
            status_code=400,
            detail="instances must be a non-empty array of objects",
        )

    allowed_fields = {
        "admin_code",
        "feature_month",
        *predictor.feature_contract.feature_columns,
    }
    validated: list[dict] = []
    for index, instance in enumerate(instances):
        if not isinstance(instance, Mapping):
            raise HTTPException(
                status_code=400,
                detail=f"instances[{index}] must be an object",
            )
        actual_fields = set(instance)
        if actual_fields != allowed_fields:
            missing = sorted(allowed_fields - actual_fields)
            extra = sorted(actual_fields - allowed_fields)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"instances[{index}] fields differ; "
                    f"missing={missing}, extra={extra}"
                ),
            )
        validated.append(dict(instance))
    return validated


def create_app(
    environ: Mapping[str, str] | None = None,
    store: ArtifactStore | None = None,
) -> FastAPI:
    """Create a fail-closed Vertex prediction app without raising on startup."""
    env = os.environ if environ is None else environ
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    predictor: PartitionedRFPredictor | None = None
    startup_error: Exception | None = None
    port = 8080
    health_route = "/health"
    predict_route = "/predict"

    try:
        port = int(env.get("AIP_HTTP_PORT", "8080"))
        health_route = env.get("AIP_HEALTH_ROUTE", "/health")
        predict_route = env.get("AIP_PREDICT_ROUTE", "/predict")
        artifact_uri = env["AIP_STORAGE_URI"]
        expected_image_digest = env["FEWSNET_CONTAINER_IMAGE_DIGEST"]
        expected_source_git_commit = env["FEWSNET_SOURCE_GIT_COMMIT"]
        artifact_store = store if store is not None else GCSArtifactStore.from_default()
        with tempfile.TemporaryDirectory(prefix="fewsnet-predictor-") as temp_dir:
            package_dir = Path(temp_dir) / "model-package"
            _localize_package(artifact_uri, artifact_store, package_dir)
            predictor = load_model_package(
                package_dir,
                expected_image_digest=expected_image_digest,
                expected_source_git_commit=expected_source_git_commit,
            )
    except Exception as exc:
        startup_error = exc

    api.state.port = port
    api.state.predictor = predictor
    api.state.startup_error = startup_error

    @api.get(health_route)
    def health() -> dict[str, str]:
        if api.state.startup_error is not None:
            raise HTTPException(status_code=503, detail="model package is not ready")
        return {"status": "healthy"}

    @api.post(predict_route)
    def predict(payload: object = Body(...)) -> dict[str, list[dict]]:
        if api.state.startup_error is not None or api.state.predictor is None:
            raise HTTPException(status_code=503, detail="model package is not ready")
        active_predictor = api.state.predictor
        instances = _validated_instances(payload, active_predictor)
        columns = [
            "admin_code",
            "feature_month",
            *active_predictor.feature_contract.feature_columns,
        ]
        try:
            predictions = active_predictor.predict_frame(
                pd.DataFrame(instances, columns=columns)
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        records = predictions.to_dict(orient="records")
        return {"predictions": records}

    return api


app = create_app()


def main() -> None:
    if __name__ == "__main__":
        # `python -m` starts as __main__; alias it so Uvicorn does not load twice.
        sys.modules.setdefault(
            "fewsnet_partitioned_rf_pipeline.vertex.predictor_server",
            sys.modules[__name__],
        )
    uvicorn.run(
        "fewsnet_partitioned_rf_pipeline.vertex.predictor_server:app",
        host="0.0.0.0",
        port=int(os.environ.get("AIP_HTTP_PORT", "8080")),
    )


if __name__ == "__main__":
    main()
