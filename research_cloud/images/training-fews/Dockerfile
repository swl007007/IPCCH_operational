# Vertex AI custom training / HPT trial image: FEWS NET four-class feature snapshot and pooled trial (fews_features, fews_fourclass); lock = the verified rt-fews-x300 runtime (numpy 2.2.6, pandas 2.2.3, xgboost 3.0.0, polars 1.27.1, geopandas 1.0.1, scikit-learn 1.6.1, scipy 1.15.2) + trial extras.
# Built by Cloud Build from a context made by research_cloud.images.context: the pinned research_cloud tree, the pinned
# scientific source (/app/sources/FEWSNETGeoXGBExperiment, hash manifest in context-manifest.json) and the exact lock, which was
# verified locally in a fresh venv (tests pass; trial boosters byte-identical to the proven runtime).
FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63

WORKDIR /app
COPY requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir --no-deps -r /app/requirements.lock.txt && pip check
COPY research_cloud /app/research_cloud
COPY sources /app/sources
COPY context-manifest.json /app/context-manifest.json

ARG SOURCE_COMMIT
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 FEWS_SRC=/app/sources/FEWSNETGeoXGBExperiment IPCCH_SOURCE_COMMIT=${SOURCE_COMMIT}
# an owned, writable HOME for the runtime user (start.py writes $HOME/.mlflow; tools cache under HOME)
RUN mkdir -p /home/app && chown 65534:65534 /home/app
ENV HOME=/home/app
USER 65534:65534
ENTRYPOINT ["python", "-m", "research_cloud.training.fews_fourclass"]
