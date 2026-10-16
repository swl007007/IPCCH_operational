# Vertex AI custom training / HPT trial image: IPCCH rich561 feature snapshot and pooled quartet trial (ipcch_features, ipcch_quartet); lock = the verified rt-geoxgb-x300 runtime (numpy 2.2.6, pandas 2.2.3, xgboost 3.0.0, scipy 1.18.1) + trial extras.
# Built by Cloud Build from a context made by research_cloud.images.context: the pinned research_cloud tree, the pinned
# scientific source (/app/sources/IPCCHGeoXGBExperiment, hash manifest in context-manifest.json) and the exact lock, which was
# verified locally in a fresh venv (tests pass; trial boosters byte-identical to the proven runtime).
FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63

WORKDIR /app
COPY requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir --no-deps -r /app/requirements.lock.txt && pip check
COPY research_cloud /app/research_cloud
COPY sources /app/sources
COPY context-manifest.json /app/context-manifest.json

ARG SOURCE_COMMIT
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 IPCCH_GEOXGB_SRC=/app/sources/IPCCHGeoXGBExperiment IPCCH_SOURCE_COMMIT=${SOURCE_COMMIT}
# an owned, writable HOME for the runtime user (start.py writes $HOME/.mlflow; tools cache under HOME)
RUN mkdir -p /home/app && chown 65534:65534 /home/app \
 && install -m 0755 /app/research_cloud/images/train-entry.sh /usr/local/bin/train-entry
ENV HOME=/home/app
# the container starts as root only so train-entry can hand Vertex's root-owned /var/hypertune mount to the runtime
# user; every command then runs as 65534 (Vertex job specs call /usr/local/bin/train-entry explicitly)
ENTRYPOINT ["/usr/local/bin/train-entry", "python", "-m", "research_cloud.training.ipcch_quartet"]
