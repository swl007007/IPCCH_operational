from pathlib import Path


PREDICTOR_MODULE = "fewsnet_partitioned_rf_pipeline.vertex.predictor_server"


EXPECTED_DOCKERFILE = f"""FROM python:3.11-slim

ARG SOURCE_GIT_COMMIT

LABEL org.opencontainers.image.title="fewsnet-partitioned-rf-runtime"
LABEL org.opencontainers.image.revision=$SOURCE_GIT_COMMIT
LABEL fewsnet.entrypoint.training="python3 -m fewsnet_partitioned_rf_pipeline.cli.train"
LABEL fewsnet.entrypoint.predictor="python3 -m {PREDICTOR_MODULE}"
LABEL fewsnet.entrypoint.orchestrator="python3 -m fewsnet_partitioned_rf_pipeline.cli.run_latest"

WORKDIR /app
COPY requirements-fewsnet-partitioned-rf.txt /app/
RUN pip install --no-cache-dir -r /app/requirements-fewsnet-partitioned-rf.txt
COPY . /app
ENV PYTHONPATH=/app
ENV FEWSNET_SOURCE_GIT_COMMIT=$SOURCE_GIT_COMMIT
EXPOSE 8080
CMD ["python3", "-m", "fewsnet_partitioned_rf_pipeline.vertex.predictor_server"]
"""


def test_shared_runtime_image_contract_is_exact():
    dockerfile = Path("docker/Dockerfile.fewsnet-partitioned-rf")

    assert dockerfile.read_text(encoding="utf-8") == EXPECTED_DOCKERFILE
