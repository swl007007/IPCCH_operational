# Historical package replay image for the IPCCH forecasting batch/launch families (56 packages: compact climate/launch
# global and Somalia, origin-safe climate/weather global).
# The lock is the exact freeze of the locally tested replay environment rt-forecast-x320 (verified again in a fresh venv built
# only from it). Entry point: research_cloud.packages.replay PACKAGE_DIR --report REPORT.json.
FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63

WORKDIR /app
COPY requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir --no-deps -r /app/requirements.lock.txt && pip check
COPY research_cloud /app/research_cloud
COPY context-manifest.json /app/context-manifest.json

ARG SOURCE_COMMIT
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 IPCCH_SOURCE_COMMIT=${SOURCE_COMMIT}
# an owned, writable HOME for the runtime user
RUN mkdir -p /home/app && chown 65534:65534 /home/app
ENV HOME=/home/app
USER 65534:65534
ENTRYPOINT ["python", "-m", "research_cloud.packages.replay"]
