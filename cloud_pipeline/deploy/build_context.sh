#!/usr/bin/env bash
# Temporary Docker build context of the v2 runtime image (task 10-30): the four runtime packages plus the verified
# IPCCH installation (accepted envelope/package/handoff, isolated smoke fixture, deployment config) staged by
# `python -m cloud.ipcch.install stage`, which re-hashes every artifact BEFORE the context is printed.
# usage: build_context.sh --envelope FILE --envelope-sha256 SHA --package DIR --handoff DIR \
#                         --smoke-fixture-root DIR --config FILE
# Build with the same pin:  docker build --build-arg IPCCH_ENVELOPE_SHA256=SHA -t IMAGE "$context"
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
declare -A arg=()
while [ $# -gt 0 ]; do
  case "$1" in
    --envelope|--envelope-sha256|--package|--handoff|--smoke-fixture-root|--config) arg["$1"]="$2"; shift 2 ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
done
for flag in --envelope --envelope-sha256 --package --handoff --smoke-fixture-root --config; do
  if [ -z "${arg[$flag]:-}" ]; then echo "missing $flag (the v2 runtime image installs verified IPCCH artifacts)" >&2; exit 2; fi
done
ctx="$(mktemp -d)"
cp "$root/deploy/Dockerfile" "$root/requirements.lock.txt" "$ctx/"
for package in cloud fewsnet_partitioned_rf_pipeline model_pipeline tools; do
  cp -R "$root/$package" "$ctx/$package"
done
find "$ctx" -name __pycache__ -type d -prune -exec rm -rf {} +
PYTHONPATH="$root" PYTHONDONTWRITEBYTECODE=1 "${PYTHON:-python3}" -m cloud.ipcch.install stage --out "$ctx/ipcch" \
  --envelope "${arg[--envelope]}" --envelope-sha256 "${arg[--envelope-sha256]}" --package "${arg[--package]}" \
  --handoff "${arg[--handoff]}" --smoke-fixture-root "${arg[--smoke-fixture-root]}" --config "${arg[--config]}" >&2
printf '%s\n' "$ctx"
