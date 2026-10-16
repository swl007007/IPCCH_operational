# Checkpoint P2d: MLflow service launcher, access model and assistant path (written 2026-10-16 04:06:41 EDT by `date`)

All evidence here comes from local rehearsal against the disposable PostgreSQL (`scratch/pg-rehearsal`).
- No cloud resource was used and no provider was called.
- Secrets were throwaway values in `scratch/svc-rehearsal/` (mode 600/700). All reports in `p2-service-733f2c0/` were scanned and are free of those values.
- Real ADC was isolated: `HOME`, `CLOUDSDK_CONFIG` and `GOOGLE_APPLICATION_CREDENTIALS` pointed at the scratch directory.
- The pre-existing local IPCCH MLflow service (`~/.venvs/ipcch-mlflow`, port 5000) was not touched.

Native code: `40f43d4`, `44350b6`, `2791308`, `733f2c0` (`research_cloud/service/`).

## Launcher (`start.py`): the base contract, refused otherwise

- **Server and stores:**
  - MLflow 3.17.0.
  - PostgreSQL tracking and auth URIs.
  - `MLFLOW_BASIC_AUTH_FAIL_CLOSED=true`.
  - Stable Flask secret and Gateway KEK, taken from the environment (Secret Manager in the cloud).
  - A private auth ini (mode 600, `default_permission = READ`).
- **Provider and job controls:**
  - `MLFLOW_GATEWAY_ALLOWED_PROVIDERS` is pinned to `vertex_ai` in every mode, and any other value is refused (supervisor scout S20). The guard wraps only the aiohttp choke point; LiteLLM and Bedrock have their own SDK exits.
  - Server job execution is forced off and SQL trace rollups are refused. Job workers could call providers outside the Gateway on the service's ADC.
- **Workspaces** are enabled; see the access model below.
- **Assistant:** armed only when all of the following are present:
  - read-only assistant credentials;
  - the provider pin;
  - an endpoint name;
  - a valid guard config with a reachable ledger.

  Otherwise it runs in `deny` mode: remote assistant off, empty assistant config, all provider egress refused. Either way, the service hook must be shown active in a fresh interpreter with the same environment (and, when armed, every assistant patch marker) before `mlflow server --app-name basic-auth` (uvicorn, 1 worker) starts.
- **Tests:** `test_service_start.py` 12 and `test_service_guard.py` 13, all passing.

## Access model: native workspace roles (`workspace_roles.py`)

**Finding.** With workspaces disabled, MLflow 3.17 lets any authenticated READ user create experiments, registered models and Gateway secrets. This was observed over HTTP on the rehearsal server. Native DENY cannot fix it: a wildcard DENY also blocks reads of every resource of that type, and it overrides a positive grant on the same key (observed; `requirements.py` fold). With workspaces enabled, creation needs a workspace-wide USE grant, while a role's READ on a type wildcard confers reads.

**Layout, explicitly separating copied grants from deliberate additions:**
- Every copied user, role, role permission and assignment is kept. The applier diffs before/after and fails if a copied grant disappears.
- `ipcch-readers` (READ on `experiment:*`, `registered_model:*`, `prompt:*`) goes to each non-admin user without a workspace grant. This preserves the read access those users had through `default_permission = READ`. The deliberate restriction is that they can no longer create top-level resources.
- `ipcch-job-writers` (workspace USE plus EDIT on listed existing experiments) goes only to the dedicated job identities.

**On a disposable copy of the r1-copied stores** (`workspace-roles-wsc.json`, 15/15; usernames replaced by labels):
- Throwaway passwords were set only in that copy.
- **Admin:** 3 grants copied unchanged.
- **Copied non-admin principal:**
  - Its Gateway endpoint USE is unchanged and still effective (`allowed: true, permission: USE`), plus 3 added READ grants.
  - It sees all 6 experiments.
  - Creating experiments, registered models and Gateway secrets is refused (403), as is creating runs.
- **New job writer:** it creates an experiment and runs in it, and creates runs in listed existing experiment 1. Experiment 2 is refused (403), as is deleting experiment 1.
- **Cutover ordering:** with workspaces on but before the roles are applied, the copied non-admin gets 403 on reads. Roles must therefore be applied before users are served (during the writer freeze).
- **Snapshot scope:** the r1 snapshot holds only these 2 principals. The final freeze must rerun the applier and diff on the live store's users.

## HTTP rehearsals (fresh stores, workspace mode)

| Report | Mode | Result | Checks |
|---|---|---|---|
| `access-deny.json` | deny | 49/49 | (see below) |
| `access-armed.json` | armed | 48/48 | |
| `access-restart.json` | after restart | 7/7 | |

Checks in the deny-mode matrix:
- **Anonymous** (401): tracking, models, artifacts, Gateway, assistant config and Gateway chat, and user creation. Content-free `/health` returns 200.
- **Reader and assistant identities:** they read runs and download artifacts (200). Everything else is 403:
  - writing runs, metrics or artifacts;
  - deleting experiments;
  - creating users;
  - self-escalation to admin and self-granting MANAGE;
  - creating experiments, registered models and Gateway secrets.
- **Job writer:** EDIT writes and proxied artifact upload (200). Experiment delete is refused (403). It can create a new experiment and write runs in it (200).
- **Remote assistant administration** (403 for both admin and the assistant identity): a real escalation attempt (switching to a shell-capable provider with `full_access`) and skills install.
- **Remote assistant chat** in deny mode is refused (403).
- **Gateway:** an admin-created OpenAI-type endpoint (fake key, inert `api_base`) is refused at invocation with exactly 400 "Provider 'openai' is not allowed by the current gateway provider policy". Nothing reaches a network.
- **After restart:** the same principals keep exactly their roles (PostgreSQL-backed).

## Assistant end-to-end (`assistant-armed.json`, 9/9)

This used a rehearsal-only fake Vertex upstream (`rehearsal_upstream.py`). It is injected beneath the guard, only when `IPCCH_REHEARSAL_FAKE_VERTEX=1`, and is refused when `K_SERVICE` is set. Everything above it ran unchanged.

1. The admin created the Vertex endpoint `ipcch-assistant-gemini` (ADC secret with no key material; project `food-crisis-modeling-enso`, location `global`, `gemini-3.8-flash`). The dedicated assistant identity holds USE on it.
2. A reader (remote client) posted a message, and the returned `stream_url` was read to completion.
   - The model requested `mlflow experiments search`.
   - The patched executor ran it with the read-only identity; the final answer quotes the real experiment table.
3. The guard ledger has one settled row per model call: reserved $1.695744 (full 1,048,576-token context at $1.50/M plus 16,384 output tokens at $7.50/M), and settled at exactly $0.00078 including 50 thinking tokens.
4. `PROBE-DENY`: the model requested `mlflow runs delete`. The stream carries the allowlist's "Permission denied" and the probe run stays active.
5. With endpoint USE revoked from the assistant identity, the turn failed with "MLflow AI Gateway error 403: Permission denied" and added no ledger row.
6. No reserved or uncertain rows were left.

## Not yet verified (cloud phase)

- A live Vertex call (G10): actual model availability in the target project, ADC under the Cloud Run identity, real thinking-token usage and the regional price.
- Cloud Run behavior:
  - the front-end client IP versus loopback;
  - streaming through the proxy;
  - timeouts;
  - min 0 / max 1 instances with concurrency 8.
- Secret Manager wiring.
- The image build (Cloud Build) and digest pinning.
- Workspace-mode compatibility on the final-freeze store, and the role applier diff on its live users.
- Copied Gateway secrets were encrypted with the source KEK. On the target, the Vertex endpoint is recreated with an ADC secret, and the copied encrypted source secret is not used.
