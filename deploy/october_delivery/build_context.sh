#!/usr/bin/env bash
# Stage a minimal build context (the repository is ~20 GB of data); print its path.
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
ctx="$(mktemp -d /tmp/october-delivery-ctx.XXXXXX)"
cp "$repo/deploy/october_delivery/Dockerfile" "$repo/deploy/october_delivery/requirements.lock.txt" "$ctx/"
for package in cloud fewsnet_partitioned_rf_pipeline model_pipeline tools; do
  rsync -a --exclude '__pycache__' --exclude '*.pyc' "$repo/$package/" "$ctx/$package/"
done
echo "$ctx"
