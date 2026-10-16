"""register_fews_packages.ensure_entry against a fake registry: wrong source/status/tags refuse, a version-less model
is resumed without re-creating the model, and registry errors other than not-found fail."""
import types
import unittest

from mlflow.exceptions import MlflowException

from research_cloud.deploy import register_fews_packages as rf

RUN = types.SimpleNamespace(info=types.SimpleNamespace(run_id="r1"))
WANT = {"package.run_id": "r1", "package.name": "p"}
T = {"package.family": "fewsnet_x", "package.name": "p", "package.status": "complete", "package.json_sha256": "s"}


class Client:
    def __init__(self, models=None, error=None):
        self.models, self.error, self.created_models = models or {}, error, 0

    def get_registered_model(self, name):
        if self.error:
            raise MlflowException("boom", error_code="INTERNAL_ERROR")
        if name not in self.models:
            raise MlflowException("missing", error_code="RESOURCE_DOES_NOT_EXIST")
        return name

    def search_model_versions(self, q):
        return self.models.get(q.split("'")[1], [])

    def create_registered_model(self, name, **k):
        self.created_models += 1
        self.models[name] = []

    def create_model_version(self, name, source, run_id=None, tags=None, description=None):
        v = types.SimpleNamespace(version="1", run_id=run_id, source=source, status="READY", tags=tags)
        self.models[name].append(v)
        return v


def version(**k):
    base = dict(version="1", run_id="r1", source="runs:/r1/package", status="READY", tags=dict(WANT))
    return types.SimpleNamespace(**{**base, **k})


class Entry(unittest.TestCase):
    def check(self, client, verify=True):
        return rf.ensure_entry(client, "m", "runs:/r1/package", RUN, WANT, T, verify=verify)

    def test_exact_entry_passes_and_mismatches_refuse(self):
        self.assertEqual(self.check(Client({"m": [version()]}))["problems"], [])
        for bad in (version(source="runs:/other/package"), version(status="PENDING_REGISTRATION"),
                    version(tags={"package.run_id": "x", "package.name": "p"}), version(run_id="r2")):
            self.assertTrue(self.check(Client({"m": [bad]}))["problems"])
        self.assertTrue(self.check(Client({"m": [version(), version(version="2")]}))["problems"])

    def test_versionless_model_resumed_without_duplicate(self):
        c = Client({"m": []})
        out = self.check(c, verify=False)
        self.assertEqual((out["created"], c.created_models, len(c.models["m"])), (1, 0, 1))

    def test_registry_error_is_not_absence(self):
        with self.assertRaises(MlflowException):
            self.check(Client(error=True), verify=False)


if __name__ == "__main__":
    unittest.main()
