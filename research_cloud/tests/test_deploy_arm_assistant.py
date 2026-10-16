"""arm_assistant: an endpoint is target-bound only when every model is the pinned Vertex model on a secret configured
for the target project/location; a query with a non-200, an error stream or an unsettled ledger row is refused."""
import types
import unittest
from unittest import mock

from research_cloud.deploy import arm_assistant as aa
from research_cloud.deploy import provision_secrets as ps


def endpoint(*ids):
    return types.SimpleNamespace(model_mappings=[types.SimpleNamespace(model_definition_id=i) for i in ids])


class Store:
    def __init__(self, models):
        self.models = models

    def list_gateway_model_definitions(self):
        return self.models


def model(i, secret, provider="vertex_ai", name="gemini-3.8-flash"):
    return types.SimpleNamespace(model_definition_id=i, secret_id=secret, provider=provider, model_name=name)


class TargetBound(unittest.TestCase):
    def bound(self, models, secrets, ep):
        def get(url, params=None, auth=None, timeout=None):
            return types.SimpleNamespace(json=lambda: {"secret": {"auth_config": secrets[params["secret_id"]]}})
        with mock.patch("requests.get", get):
            return aa.target_bound(Store(models), "u", ("a", "b"), ep)

    def test_target_and_old_project(self):
        good = {"vertex_project": "food-crisis-modeling-enso", "vertex_location": "global"}
        old = {"vertex_project": "manuel-remote-sensing", "vertex_location": "global"}
        self.assertIs(self.bound([model("d1", "s1")], {"s1": good}, endpoint("d1")), True)
        self.assertIn("manuel-remote-sensing", self.bound([model("d1", "s1")], {"s1": old}, endpoint("d1")))
        self.assertIsNot(self.bound([model("d1", "s1", name="other")], {"s1": good}, endpoint("d1")), True)
        self.assertIsNot(self.bound([model("d1", "s1")], {"s1": good}, endpoint()), True)


class Query(unittest.TestCase):
    def run_query(self, post, stream, body, rows):
        seq = iter([[], rows])
        with mock.patch.object(aa, "guard_rows", lambda api, port: next(seq)), \
                mock.patch("research_cloud.service.rehearse_assistant.stream_turn", lambda *a: (post, stream, body)), \
                mock.patch("research_cloud.deploy.mlflow_identities.cred", lambda api, name: ("r", "p")):
            receipt = types.SimpleNamespace(data={}, step=lambda *a, **k: None)
            return aa.do_query(None, receipt, "u", 1)

    def test_refusals(self):
        ok = [(1, "settled", 1, 0.01, 1, 1, 0)]
        self.assertTrue(self.run_query(200, 200, "answer", ok)["all_settled"])
        for args in ((500, None, "", ok), (200, 200, '{"type": "error"}', ok),
                     (200, 200, "answer", [(1, "uncertain", 1, None, None, None, None)]), (200, 200, "answer", [])):
            with self.assertRaises(ps.ProvisionError):
                self.run_query(*args)


if __name__ == "__main__":
    unittest.main()
