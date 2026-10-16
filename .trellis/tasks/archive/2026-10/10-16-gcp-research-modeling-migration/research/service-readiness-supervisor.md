# P2 service readiness: installed-code findings

Read-only exploration on 2026-10-16 during an executor provider retry. These are implementation pointers, not service/cloud acceptance. No credentials, accounts or cloud resources were read.

Paths:
- `S=/home/swl007007/projects/food-crisis-research/sources/Food_Crisis_Cluster/IPCCHMLflow`
- `M=/home/swl007007/projects/food-crisis-research/envs/mlflow-svc/lib/python3.12/site-packages/mlflow`

## Concrete reuse and integration points

1. Keep MLflow's supported `--app-name basic-auth` **uvicorn** path. `M/server/auth/__init__.py:9011-9016` returns FastAPI and adds native permission middleware only when `_MLFLOW_SGI_NAME == uvicorn`. `M/server/__init__.py:224-245,429-449` resolves app entry points and bootstraps auth. A Flask/Gunicorn-only wrapper does not preserve the same Gateway/assistant/native artifact routes.
2. Tracking PostgreSQL URI and auth PostgreSQL URI are separate. Auth configuration uses `MLFLOW_AUTH_CONFIG_PATH` and ini `database_uri` (`M/server/auth/config.py:31-60`). Preserve all current auth tables: installed RBAC uses users/roles/role_permissions/user_role_assignments; legacy experiment/model permission tables alone are insufficient (`M/server/auth/db/models.py:22-111`). The verified full-store copier already compares all auth tables.
3. Enable `MLFLOW_BASIC_AUTH_FAIL_CLOSED`; native FastAPI routes without a permission validator otherwise fall through (`M/server/auth/__init__.py:8730-8738`). Verify intended allowed routes too; this setting is not proof of complete permission behavior.
4. **Vertex ADC is supported by this installed release.** Use provider `vertex_ai`, model auth_config with `vertex_project` / `vertex_location`, and omit explicit vertex_credentials for workload identity. `M/gateway/providers/vertex_ai.py:395-444` calls `google.auth.default`, refreshes credentials and builds the target project's publisher endpoint; default location is global. Provider `gemini` instead requires its API key. `M/server/gateway_api.py:506-511` maps model auth_config. Exact model/project/provider compatibility still needs a bounded live call.
5. Existing `S/assistant_patch.py:119-181` is reusable for its precise command allowlist, local self-call and read-only tools, but its `.pth` startup behavior is fail-open (`:122-124,192-196`). Require explicit startup verification of version, successful patch markers, complete dedicated read-only credentials and loopback `$PORT` URL before enabling the assistant. Do not merely rely on logging an exception from a `.pth` import. Existing permission flags must stay disabled even through assistant permission/tool-result routes.
6. Preserve stable Flask secret and Gateway KEK; generating them per revision can invalidate sessions/encrypted Gateway data (`S/manage.sh:39-42`). The live old-project provider key is not the target credential. Never expose these values in evidence.
7. The assistant reads `~/.mlflow/assistant/config.json` (`M/assistant/config.py:6-7,51-76`); a deterministic container config is required. Existing source `manage.sh` hardcodes localhost:5000, SQLite and local artifact paths. New entry must serve foreground on `0.0.0.0:$PORT`, with assistant self-calls on `127.0.0.1:$PORT`.
8. Installed service dependencies include google-cloud-storage 3.17.1 and psycopg2-binary 2.9.13; these are absent from the old `S/requirements.lock`. Pin required dependencies explicitly in the image. `S/ipcch_model.py:141-162` supports runs:/ downloads, but local path feature lists still require the planned URI mapping/bounded staging.

## Focused validation to reuse

- `S/tests/test_assistant_patch.py:14-54` has a subprocess probe for self URL and X-MLflow-Authorization, and `:69-98` covers command/executor denials. Its no-credential success test at `:100-102` cannot stand as the cloud fail-closed contract.
- Exercise anonymous artifact/Gateway/assistant access, invited read versus write, owner/job write, dedicated assistant READ plus endpoint USE, and role preservation after revision restart. Existing mock-only patch tests do not prove HTTP access control.
- Include assistant message/stream/permission/tool-result behavior; config PUT and skills/install POST are localhost-only (`M/server/assistant/api.py:674-675,751-752`), so remote calls and proxy headers must not turn them into administrative access.

Supervisor directly inspected the uvicorn/native-auth branch, fail-closed branch, Vertex ADC/endpoint implementation and existing assistant patch. Also checked these five installed files against the distribution RECORD hashes: gateway/config.py, gateway/providers/vertex_ai.py, server/__init__.py, server/auth/__init__.py and server/fastapi_app.py; all match. Other anchors above are explorer findings to consult when implementing. No service was started or provider call made by this review.
