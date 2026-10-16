"""End-to-end assistant rehearsal against a local armed server whose Vertex upstream is the rehearsal fake
(``rehearsal_upstream.py``; never on Cloud Run). Exact outcomes only.

1. The admin creates the Vertex AI Gateway endpoint the assistant config names (ADC secret: no key material), and
   grants the dedicated assistant identity USE on it.
2. A reader (READ role, remote client) posts a message; the returned ``stream_url`` is read to completion. The model
   asks for ``mlflow experiments search``; the patched executor runs it with the read-only identity; the final text
   must quote that tool result.
3. ``PROBE-DENY``: the model asks for ``mlflow runs delete``; the stream must carry the allowlist denial and the
   probe run must still exist.
4. The guard ledger must hold one settled row per model call at the exact usage price, and no uncertain rows.
5. Without endpoint USE for the assistant identity, a turn must fail with the Gateway's permission refusal.

  python -m research_cloud.service.rehearse_assistant --url URL --state STATE.json --guard-dsn DSN --out REPORT.json
"""
import argparse
import contextlib
import json
import os
import secrets
from decimal import Decimal

import requests

from research_cloud.service.rehearsal_upstream import quoted_tool_result

REMOTE = {"X-Forwarded-For": "203.0.113.9"}
ENDPOINT = "ipcch-assistant-gemini"


def stream_turn(url, auth, message, experiment_id):
    r = requests.post(url + "/ajax-api/3.0/mlflow/assistant/message", headers=REMOTE, auth=auth, timeout=60,
                      json={"message": message, "experiment_id": experiment_id, "context": {}})
    if r.status_code != 200:
        return r.status_code, None, ""
    stream_url = r.json()["stream_url"]
    s = requests.get(url + stream_url if stream_url.startswith("/") else stream_url, headers=REMOTE, auth=auth,
                     stream=True, timeout=300)
    body = "".join(chunk.decode("utf-8", "replace") for chunk in s.iter_content(None))
    return r.status_code, s.status_code, body


def listing_ok(stream_text, experiment_name):
    """The quoted tool result is a successful experiment listing containing the expected experiment."""
    result = quoted_tool_result(stream_text)
    if result is None or experiment_name not in result:
        return False
    lowered = result.lower()
    return "experiment id" in lowered and "permission denied" not in lowered and "error" not in lowered


def denial_ok(stream_text):
    result = quoted_tool_result(stream_text)
    return result is not None and result.startswith("Permission denied: this assistant may only run read-only commands")


def ledger_rows(dsn):
    import psycopg2
    with contextlib.closing(psycopg2.connect(dsn)) as c, c.cursor() as cur:
        cur.execute("SELECT status, reserved_usd, actual_usd, thought_tokens FROM ipcch_assistant_ledger ORDER BY id")
        return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--guard-dsn", required=True)
    ap.add_argument("--assistant-user", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    url, state = args.url.rstrip("/"), json.load(open(args.state))
    admin = ("admin", os.environ["MLFLOW_AUTH_ADMIN_PASSWORD"])
    reader = tuple(state["auth"]["reader"])
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    from mlflow.entities.gateway_endpoint import GatewayEndpointModelConfig, GatewayModelLinkageType
    from mlflow.store.tracking.rest_store import RestStore
    from mlflow.utils.rest_utils import MlflowHostCreds
    store = RestStore(lambda: MlflowHostCreds(url, username=admin[0], password=admin[1]))
    existing = {e.name: e for e in store.list_gateway_endpoints()}
    if ENDPOINT in existing:
        endpoint = existing[ENDPOINT]
    else:
        tag = secrets.token_hex(3)
        secret = store.create_gateway_secret(f"vertex-adc-{tag}", {"mode": "adc"}, provider="vertex_ai",
                                              auth_config={"vertex_project": "food-crisis-modeling-enso", "vertex_location": "global"})
        model = store.create_gateway_model_definition(f"gemini-3.8-flash-{tag}", secret.secret_id, "vertex_ai", "gemini-3.8-flash")
        endpoint = store.create_gateway_endpoint(ENDPOINT, [GatewayEndpointModelConfig(
            model_definition_id=model.model_definition_id, linkage_type=GatewayModelLinkageType.PRIMARY, weight=1.0)])
    grant = {"username": args.assistant_user, "resource_type": "gateway_endpoint", "resource_id": endpoint.endpoint_id}
    requests.post(url + "/api/3.0/mlflow/users/permissions/grant", json=dict(grant, permission="USE"), auth=admin, timeout=60)
    perm = requests.get(url + "/api/3.0/mlflow/users/permissions/get", params=grant, auth=admin, timeout=60).json()
    check("assistant identity holds USE on the endpoint", perm.get("permission") == "USE", perm)

    rows0 = len(ledger_rows(args.guard_dsn))
    exp_name = requests.get(url + "/api/2.0/mlflow/experiments/get", params={"experiment_id": state["experiment_id"]},
                            auth=admin, timeout=60).json()["experiment"]["name"]
    post, got, body = stream_turn(url, reader, "Which experiments exist?", state["experiment_id"])
    check("reader message accepted and stream read", (post, got) == (200, 200), [post, got])
    check("tool ran with the read-only identity and the quoted result lists the probe experiment",
          listing_ok(body, exp_name), (quoted_tool_result(body) or body[-400:])[:600])
    rows = ledger_rows(args.guard_dsn)[rows0:]
    unit = (Decimal(120) * Decimal("1.5") + Decimal(80) * Decimal("7.5")) / Decimal(1_000_000)
    check("one settled ledger row per model call at the exact usage price",
          len(rows) == 2 and all(r[0] == "settled" and r[2] == unit and r[3] == 50 for r in rows),
          [[str(x) for x in r] for r in rows])

    rows0 = len(ledger_rows(args.guard_dsn))
    post, got, body = stream_turn(url, reader, f"PROBE-DENY run={state['run_id']} please clean up", state["experiment_id"])
    check("prohibited delete of the real probe run denied by the allowlist", (post, got) == (200, 200) and denial_ok(body),
          (quoted_tool_result(body) or body[-400:])[:400])
    run = requests.get(url + "/api/2.0/mlflow/runs/get", params={"run_id": state["run_id"]}, auth=admin, timeout=60)
    check("probe run still active", run.status_code == 200 and run.json()["run"]["info"]["lifecycle_stage"] == "active")
    check("deny turn also settled", all(r[0] == "settled" for r in ledger_rows(args.guard_dsn)[rows0:]))

    requests.post(url + "/api/3.0/mlflow/users/permissions/revoke", json=grant, auth=admin, timeout=60)
    rows0 = len(ledger_rows(args.guard_dsn))
    post, got, body = stream_turn(url, reader, "Which experiments exist?", state["experiment_id"])
    check("without endpoint USE the turn fails before any model call",
          len(ledger_rows(args.guard_dsn)) == rows0 and "REHEARSAL-ANSWER" not in body
          and "MLflow AI Gateway error 403: Permission denied" in body,
          body[-300:])
    requests.post(url + "/api/3.0/mlflow/users/permissions/grant", json=dict(grant, permission="USE"), auth=admin, timeout=60)

    check("no uncertain or reserved rows left", all(r[0] == "settled" for r in ledger_rows(args.guard_dsn)))
    json.dump({"passed": sum(c["ok"] for c in checks), "total": len(checks), "checks": checks}, open(args.out, "w"),
              indent=1, default=str)
    for c in checks:
        print("OK " if c["ok"] else "FAIL", c["check"], "" if c["ok"] else str(c["detail"])[:300])
    return 0 if all(c["ok"] for c in checks) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
