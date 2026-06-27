FROM python:3.11-slim

LABEL org.opencontainers.image.title="ipcch-monthly-e2e-runtime"
LABEL org.opencontainers.image.description="Single repository image for IPCCH Cloud Run, Cloud Batch, and Vertex AI custom-job entrypoints"
LABEL ipcch.entrypoint.orchestrator="python3 -m cloud.orchestrator.main"
LABEL ipcch.entrypoint.batch_worker="python3 -m cloud.batch.evi_worker"
LABEL ipcch.entrypoint.vertex_inference="python3 -m cloud.orchestrator.inference"
LABEL ipcch.entrypoint.local_inference="python3 model_pipeline/run_operational_launch_inference.py"

WORKDIR /app

COPY requirements-cloud.txt /app/requirements-cloud.txt
RUN pip install --no-cache-dir -r /app/requirements-cloud.txt

COPY . /app

ENV PYTHONPATH=/app

CMD ["python3", "-m", "cloud.orchestrator.main", "--help"]
