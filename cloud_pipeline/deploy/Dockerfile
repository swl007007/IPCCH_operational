# October cloud delivery runtime: Cloud Run preparation/delivery jobs and the Batch extract worker.
# Python 3.12.3 matches the frozen scoring environment recorded by the FEWS package manifests.
FROM python:3.12.3-slim

WORKDIR /app
COPY requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir --no-deps -r /app/requirements.lock.txt && pip check

COPY cloud /app/cloud
COPY fewsnet_partitioned_rf_pipeline /app/fewsnet_partitioned_rf_pipeline
COPY model_pipeline /app/model_pipeline
COPY tools /app/tools

ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1
# Accepted IPCCH v2 installation (task 10-30): staged and verified by deploy/build_context.sh, re-verified here offline
# against the staged INSTALL.json and the pinned envelope sha256 (no network, no download of mutable artifacts).
ARG IPCCH_ENVELOPE_SHA256
COPY ipcch /opt/ipcch
RUN test -n "$IPCCH_ENVELOPE_SHA256" \
    && python3 -m cloud.ipcch.install verify --root /opt/ipcch --envelope-sha256 "$IPCCH_ENVELOPE_SHA256" \
       --against /opt/ipcch/INSTALL.json
LABEL ipcch.install.manifest="/opt/ipcch/INSTALL.json"
LABEL ipcch.entrypoint.v2_config="/opt/ipcch/deployment.json"
LABEL ipcch.entrypoint.prepare_plan="python3 -m cloud.orchestrator.prepare plan"
LABEL ipcch.entrypoint.prepare_extract="python3 -m cloud.orchestrator.prepare extract"
CMD ["python3", "-m", "cloud.orchestrator.prepare", "--help"]
