# IPCCH research MLflow service (Cloud Run): MLflow 3.17.0 server with basic auth on PostgreSQL, the spend/egress
# guard hook, the read-only assistant patch and the ipcch-model catalog tool. Built by Cloud Build from a context made
# by research_cloud.images.context (pinned research_cloud tree + exact lock); secrets come from Secret Manager at run time.
FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63

WORKDIR /app
COPY requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir --no-deps -r /app/requirements.lock.txt && pip check
COPY research_cloud /app/research_cloud
COPY context-manifest.json /app/context-manifest.json
# the service hook must load in every interpreter the server starts (start.py verifies it before serving)
RUN cp /app/research_cloud/service/ipcch_service_hook.pth "$(python -c 'import site; print(site.getsitepackages()[0])')/" \
 && printf '#!/bin/sh\nexec python -m research_cloud.service.ipcch_model "$@"\n' > /usr/local/bin/ipcch-model \
 && chmod 0755 /usr/local/bin/ipcch-model

ARG SOURCE_COMMIT
# The hook .pth loads in EVERY interpreter of this image, including the launcher itself before start.prepare runs, and the
# guard refuses unless the Gateway provider allowlist is pinned to vertex_ai - so the pin is part of the image.
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 IPCCH_SERVICE_HOOK=1 IPCCH_MODEL_CLOUD=1 IPCCH_SOURCE_COMMIT=${SOURCE_COMMIT} \
    MLFLOW_GATEWAY_ALLOWED_PROVIDERS=vertex_ai
# an owned, writable HOME for the runtime user (start.py writes $HOME/.mlflow; tools cache under HOME)
RUN mkdir -p /home/app && chown 65534:65534 /home/app
ENV HOME=/home/app
USER 65534:65534
CMD ["python", "-m", "research_cloud.service.start"]
