# Bounded runtime identity probe

User goal-scoped cloud authorization, 2026-10-31. Technical scope reviewed by Supervisor.

- Create/update ONLY `ipcch-v2-runtime-preflight-20261031`, us-central1, project feisty-flames-511718-d4.
- Existing digest 487a2315; monthly-runtime SA, 1 task/parallelism 1, 1 CPU, 512 MiB, 300 seconds, zero task retries.
- One execution; max 300 vCPU-seconds and 150 GiB-seconds plus ordinary logging/API usage. No automatic resubmission.
- Exact job declaration: runtime-probe-job.json; exact code: runtime-probe.py.
- Read two known han-sandbox assets and data/request bucket permissions/current metadata. No export, asset/ACL change, source data write or production job/Workflow update.
- Persist job/execution/log evidence. Retain probe definition for reproducibility; no recurring schedule.
- Failed checks remain explicit prerequisites; do not infer success or broaden IAM silently. This verifies identity access using the old image, not the new image or full real E2E.
