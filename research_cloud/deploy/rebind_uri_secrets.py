"""Add a corrected version to the two MLflow URI secrets whose first version lacks the psycopg2 driver.

Cloud Run revision research-mlflow-00001 failed at start: ``No module named 'psycopg'``. SQLAlchemy 2.1 maps a bare
``postgresql://`` URI to psycopg (v3); the service image ships psycopg2 (the local rehearsal used
``postgresql+psycopg2://``). ``provision_secrets`` composed the URIs without the driver; its templates now carry it.

For ``mlflow-backend-uri`` and ``mlflow-auth-db-uri`` (task-owned): the expected value is composed in-process from
``sql-mlflow-app`` with the corrected template. If the latest version already equals it, nothing changes. Otherwise
the latest version must equal the expected value with the bare ``postgresql://`` scheme - i.e. differ by the driver
only - else the run refuses (no rotation of anything else). A new version is added, read back and must equal the
expected value. Values are never printed or receipted; the receipt records the version numbers.

  python -m research_cloud.deploy.rebind_uri_secrets --receipt RECEIPT.json
"""
import argparse
import base64
import json
import sys

from research_cloud.deploy.provision_secrets import (DEPENDENT, DRIVER, SM, Api, ProvisionError, Receipt, message,
                                                     remember, scrub, secret_state)

NAMES = ("mlflow-backend-uri", "mlflow-auth-db-uri")


def run(api, receipt):
    state, password = secret_state(api, "sql-mlflow-app")
    if state != "task":
        raise ProvisionError(f"sql-mlflow-app is {state}; refusing")
    result = {}
    for name in NAMES:
        expected = remember(DEPENDENT[name][0]({"sql-mlflow-app": password}))
        state, current = secret_state(api, name)
        if state != "task":
            raise ProvisionError(f"secret {name} is {state}; refusing")
        if current == expected:
            result[name] = "already current"
            receipt.step("uri-secret", name=name, result="already current")
            continue
        if current != expected.replace(f"{DRIVER}://", "postgresql://", 1):
            raise ProvisionError(f"secret {name} differs from the composed value by more than the driver; refusing")
        status, ver = api.call("POST", f"{SM}/{name}:addVersion",
                               {"payload": {"data": base64.b64encode(expected.encode()).decode()}})
        if status != 200:
            raise ProvisionError(f"secret {name}: addVersion returned {status} {message(ver)}")
        version = ver.get("name", "").rsplit("/", 1)[-1]
        if secret_state(api, name)[1] != expected:
            raise ProvisionError(f"secret {name}: read-back of the new version differs")
        receipt.data.setdefault("uri_rebind", {})[name] = {"version": version, "driver": DRIVER}
        result[name] = f"version {version}"
        receipt.step("uri-secret", name=name, result=f"added version {version} (driver {DRIVER})")
    return result


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", required=True)
    args = ap.parse_args(argv)
    receipt = Receipt(args.receipt)
    try:
        result = run(api or Api(), receipt)
    except ProvisionError as e:
        receipt.step("stopped", error=scrub(str(e)))
        print(scrub(json.dumps({"status": "stopped", "error": str(e)})))
        return 1
    print(scrub(json.dumps({"status": "complete", **result})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
