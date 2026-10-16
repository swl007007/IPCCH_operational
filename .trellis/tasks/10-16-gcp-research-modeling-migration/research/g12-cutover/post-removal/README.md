# Post-removal access checks, revision research-mlflow-00007-hld (2026-10-16 ~12:49 EDT)

- `access-direct-anonymous-rev00007-postremoval.json`: `staging_access --direct`, **17/17**.
  - No Google identity is used: `--direct` runs with `token=None`, and `Checks.call` sends `X-Serverless-Authorization` only when `iam and self.token`.
  - The rows' `"iam_token": true` is a legacy row-intent field from the IAM-staging matrix. It does **not** mean a header was sent.
- `cloud-access-direct-rev00007-postremoval.json`: `cloud_access --without-admin`, **31/31** (reader, job writer and assistant only).
  - This run never read `mlflow-temp-admin`, and the temporary admin no longer exists.
  - 31 = the earlier 32 rows minus the admin row.
- Same commands, artifact and run as the rev00006 checks (O-063 form), with `--without-admin` added.
