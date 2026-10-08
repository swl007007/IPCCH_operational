#!/bin/bash
cd "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational"
find cloud fewsnet_partitioned_rf_pipeline model_pipeline tools -name "*.py" -not -path "*__pycache__*" -print0 | sort -z | xargs -0 sha256sum
sha256sum .trellis/tasks/10-07-october-cloud-delivery/research/cp3_evidence/run_local_delivery.py /tmp/oct-prepared-cache/smoke-local-20261008a/* Outcome/model_delivery/202609_h5/20260923_country_confidence_v3/inputs/ipcch_panel.csv Outcome/model_delivery/202609_h5/20260923_country_confidence_v3/inputs/ipcch_april_panel.csv
find model_artifacts/launch_2026_04 -type f -print0 | sort -z | xargs -0 sha256sum
