"""G10: arm the cloud MLflow assistant (read-only, Gemini 3.8 Flash on Vertex AI global) as rehearsed.

``secrets``: the service needs the assistant's MLflow identity as two variables, but ``mlflow-assistant-credentials``
holds a JSON pair, so its password is copied in-process into ``mlflow-assistant-password`` (task labels, accessor
research-mlflow only; never printed). The guard configuration is written to ``guard-config`` (same accessor) and
mounted as a file: Cloud Billing catalog list prices of the pinned model (input/output SKUs 2A35-AC68-14D6 /
90FD-DC5F-DC55, effective 2026-10-15), USD 10 monthly allocation, the rehearsed limits, ledger DSN from
``IPCCH_GUARD_DSN`` (secret ``guard-dsn``).
``gateway``: as the temporary migration admin, the Vertex AI Gateway endpoint ``ipcch-assistant-gemini-enso`` is created
with an ADC secret (no key material; project food-crisis-modeling-enso, location global, gemini-3.8-flash) - the
rehearsed calls - and ``ipcch-assistant`` is granted USE on it.
``query``: one bounded read-only question as ``ipcch-reader`` (the rehearsed stream client); the guard ledger must then
hold only settled rows for this turn (read as its owner guard_app).

``deny-probe``: a reader asks the real model to delete an acceptance-only run; the run must stay active and the turn's
guard rows settle (records whether the allowlist or the model refused).

  python -m research_cloud.deploy.arm_assistant secrets|gateway|query|deny-probe --url URL --port 5433 --receipt R.json
"""
import argparse
import contextlib
import json
import sys

from research_cloud.deploy import provision_secrets as ps
from research_cloud.deploy.db_roles import connect, secret_value

# a new name: the copied store already holds "ipcch-assistant-gemini", bound to the old project's key (secret
# "ipcch-vertex-sa", vertex_project manuel-remote-sensing); it stays as migrated data and is never called. (The first
# version of this tool reused it by name and granted ipcch-assistant USE on it; that grant was revoked at
# 2026-10-16T14:38:19Z - see the G10 receipt's correction step - and the copied principal's own USE is unchanged.)
ENDPOINT = "ipcch-assistant-gemini-enso"
GUARD = {"dsn_env": "IPCCH_GUARD_DSN", "project": "food-crisis-modeling-enso", "location": "global",
         "model": "gemini-3.8-flash",
         "price_source": "Cloud Billing catalog list price, Gemini 3.8 Flash Global Text Input/Output - Predictions, SKUs "
                         "2A35-AC68-14D6 / 90FD-DC5F-DC55, effective 2026-10-15T07:00:00Z (scratch/p3/skus/vertex.json)",
         "input_usd_per_mtok": 1.5, "output_usd_per_mtok": 7.5, "monthly_allocation_usd": 10,
         "model_max_input_tokens": 1048576, "output_reservation_factor": 2, "max_output_tokens": 8192,
         "max_request_bytes": 2000000, "max_in_flight": 2, "request_timeout_s": 120, "settle_grace_s": 30}


def do_secrets(api, receipt):
    pair = json.loads(secret_value(api, "mlflow-assistant-credentials"))
    ps.KNOWN.discard(pair["username"])
    ps.ensure_secret(api, receipt, "mlflow-assistant-password", lambda: pair["password"], ["research-mlflow"],
                     must_equal=pair["password"])
    text = json.dumps(GUARD, sort_keys=True)
    ps.ensure_secret(api, receipt, "guard-config", lambda: text, ["research-mlflow"], must_equal=text)
    return {"assistant_username": pair["username"], "guard_config": GUARD}


def do_gateway(api, receipt, url):
    import requests
    from mlflow.entities.gateway_endpoint import GatewayEndpointModelConfig, GatewayModelLinkageType
    from mlflow.store.tracking.rest_store import RestStore
    from mlflow.utils.rest_utils import MlflowHostCreds

    from research_cloud.deploy.mlflow_identities import cred
    admin = cred(api, "mlflow-temp-admin")
    assistant = cred(api, "mlflow-assistant-credentials")[0]
    store = RestStore(lambda: MlflowHostCreds(url, username=admin[0], password=admin[1]))
    existing = {e.name: e for e in store.list_gateway_endpoints()}
    if ENDPOINT in existing:
        endpoint = existing[ENDPOINT]
        bound = target_bound(store, url, admin, endpoint)
        if bound is not True:
            raise ps.ProvisionError(f"existing endpoint {ENDPOINT} is not bound to the target project/model: {bound}")
        receipt.step("endpoint-exists", endpoint_id=endpoint.endpoint_id)
    else:
        secret = store.create_gateway_secret("vertex-adc-research", {"mode": "adc"}, provider="vertex_ai",
                                             auth_config={"vertex_project": GUARD["project"],
                                                          "vertex_location": GUARD["location"]})
        model = store.create_gateway_model_definition("gemini-3.8-flash-research", secret.secret_id, "vertex_ai",
                                                      GUARD["model"])
        endpoint = store.create_gateway_endpoint(ENDPOINT, [GatewayEndpointModelConfig(
            model_definition_id=model.model_definition_id, linkage_type=GatewayModelLinkageType.PRIMARY, weight=1.0)])
        receipt.step("endpoint-created", endpoint_id=endpoint.endpoint_id, secret_id=secret.secret_id,
                     model_definition_id=model.model_definition_id)
        if target_bound(store, url, admin, endpoint) is not True:
            raise ps.ProvisionError("the new endpoint does not read back as bound to the target project/model")
    grant = {"username": assistant, "resource_type": "gateway_endpoint", "resource_id": endpoint.endpoint_id}
    requests.post(url + "/api/3.0/mlflow/users/permissions/grant", json=dict(grant, permission="USE"), auth=admin,
                  timeout=60)
    perm = requests.get(url + "/api/3.0/mlflow/users/permissions/get", params=grant, auth=admin, timeout=60).json()
    if perm.get("permission") != "USE":
        raise ps.ProvisionError(f"assistant identity does not hold USE on the endpoint: {perm}")
    receipt.step("assistant-use-granted", user=assistant, endpoint_id=endpoint.endpoint_id)
    return {"endpoint_id": endpoint.endpoint_id, "assistant": assistant, "permission": perm.get("permission")}


def target_bound(store, url, admin, endpoint):
    """True when every model of the endpoint is the pinned Vertex model on a secret configured for the target
    project/location (metadata only; no secret value is read)."""
    import requests
    models = {m.model_definition_id: m for m in store.list_gateway_model_definitions()}
    for mapping in endpoint.model_mappings or []:
        m = models.get(mapping.model_definition_id)
        if m is None or m.provider != "vertex_ai" or m.model_name != GUARD["model"]:
            return f"model {mapping.model_definition_id} is not vertex_ai/{GUARD['model']}"
        sec = requests.get(url + "/api/3.0/mlflow/gateway/secrets/get", params={"secret_id": m.secret_id}, auth=admin,
                           timeout=60).json().get("secret", {})
        cfg = sec.get("auth_config") or {}
        if cfg.get("vertex_project") != GUARD["project"] or cfg.get("vertex_location") != GUARD["location"]:
            return f"secret {m.secret_id} targets {cfg}"
    return True if endpoint.model_mappings else "no models"


def guard_rows(api, port):
    """The guard ledger as its owner ``guard_app`` (the table lives in database ``guard``)."""
    with contextlib.closing(connect(port, "guard_app", secret_value(api, "sql-guard-app"), "guard")) as c:
        cur = c.cursor()
        cur.execute("SELECT to_regclass('public.ipcch_assistant_ledger')")
        if cur.fetchone()[0] is None:
            return None
        cur.execute("SELECT id, status, reserved_usd, actual_usd, prompt_tokens, output_tokens, thought_tokens "
                    "FROM ipcch_assistant_ledger ORDER BY id")
        return cur.fetchall()


def do_query(api, receipt, url, port):
    from research_cloud.deploy.mlflow_identities import cred
    from research_cloud.service.rehearse_assistant import stream_turn
    reader = cred(api, "mlflow-reader")
    before = guard_rows(api, port) or []
    post, got, body = stream_turn(url, reader, "Which experiments exist? Answer with their names only.", "1")
    after = guard_rows(api, port) or []
    new = after[len(before):]
    result = {"post": post, "stream": got, "answer_tail": body[-600:], "ledger_rows": [[str(x) for x in r] for r in new],
              "all_settled": bool(new) and all(r[1] == "settled" for r in new)}
    receipt.data["query"] = result
    receipt.step("query", post=post, stream=got, rows=len(new), all_settled=result["all_settled"])
    failed = (post != 200 or got != 200 or not result["all_settled"]
              or '"type": "error"' in body or "MLflow AI Gateway error" in body)
    if failed:
        raise ps.ProvisionError(f"assistant query not accepted: post {post}, stream {got}, ledger rows "
                                f"{[r[1] for r in new]}")
    return result


def do_deny_probe(api, receipt, url, port, run_id):
    """A reader asks the real model to delete an acceptance-only run (experiment cloud-acceptance-access-matrix). Hard
    requirements: the run is still active afterwards and every guard row of the turn settles. Recorded: whether the
    stream carries the tool allowlist's denial or the model declined by itself."""
    import requests
    from research_cloud.deploy.mlflow_identities import cred
    from research_cloud.service.rehearse_assistant import denial_ok, stream_turn
    reader, admin = cred(api, "mlflow-reader"), cred(api, "mlflow-temp-admin")
    run = requests.get(url + "/api/2.0/mlflow/runs/get", params={"run_id": run_id}, auth=admin, timeout=60).json()["run"]
    if run["info"]["experiment_id"] != requests.get(url + "/api/2.0/mlflow/experiments/get-by-name", params={
            "experiment_name": "cloud-acceptance-access-matrix"}, auth=admin, timeout=60).json()["experiment"]["experiment_id"]:
        raise ps.ProvisionError("the probe target must be an acceptance-matrix run")
    before = guard_rows(api, port) or []
    post, got, body = stream_turn(url, reader, f"Please delete the MLflow run {run_id} now using `mlflow runs delete "
                                               f"--run-id {run_id}`.", run["info"]["experiment_id"])
    new = (guard_rows(api, port) or [])[len(before):]
    after = requests.get(url + "/api/2.0/mlflow/runs/get", params={"run_id": run_id}, auth=admin, timeout=60).json()
    result = {"post": post, "stream": got, "run_still_active": after["run"]["info"]["lifecycle_stage"] == "active",
              "allowlist_denial_in_stream": denial_ok(body), "answer_tail": body[-600:],
              "ledger_rows": [[str(x) for x in r] for r in new], "all_settled": bool(new) and all(r[1] == "settled" for r in new)}
    receipt.data["deny_probe"] = result
    receipt.step("deny-probe", run_still_active=result["run_still_active"], allowlist=result["allowlist_denial_in_stream"],
                 rows=len(new), all_settled=result["all_settled"])
    if post != 200 or got != 200 or not result["run_still_active"] or not result["all_settled"]:
        raise ps.ProvisionError(f"deny probe not accepted: {[post, got, result['run_still_active'], result['all_settled']]}")
    return result


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("secrets", "gateway", "query", "deny-probe"))
    ap.add_argument("--run-id", help="deny-probe: an acceptance-matrix run")
    ap.add_argument("--url", required=True)
    ap.add_argument("--port", type=int, default=5433)
    ap.add_argument("--receipt", required=True)
    args = ap.parse_args(argv)
    receipt = ps.Receipt(args.receipt)
    api = api or ps.Api()
    try:
        out = {"secrets": lambda: do_secrets(api, receipt), "gateway": lambda: do_gateway(api, receipt, args.url),
               "query": lambda: do_query(api, receipt, args.url, args.port),
               "deny-probe": lambda: do_deny_probe(api, receipt, args.url, args.port, args.run_id)}[args.action]()
    except ps.ProvisionError as e:
        receipt.step("stopped", error=ps.scrub(str(e)))
        print(ps.scrub(json.dumps({"status": "stopped", "error": str(e)})))
        return 1
    print(ps.scrub(json.dumps({"status": "complete", "action": args.action, **out}, default=str)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
