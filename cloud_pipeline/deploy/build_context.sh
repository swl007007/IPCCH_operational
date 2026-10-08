#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
ctx="$(mktemp -d)"
cp "$root/deploy/Dockerfile" "$root/requirements.lock.txt" "$ctx/"
for package in cloud fewsnet_partitioned_rf_pipeline model_pipeline tools; do
  cp -R "$root/$package" "$ctx/$package"
done
printf '%s\n' "$ctx"
