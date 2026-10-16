"""Regressions for the service rehearsal tooling: role-layout precondition and the assistant probes' predicates.

No server or network: the role applier runs against an in-memory fake of the admin API.
"""
import json
import unittest

from research_cloud.service import rehearse_assistant, rehearsal_upstream, workspace_roles

READERS = [[t, "*", "READ"] for t in workspace_roles.READ_TYPES]


def snap(users, roles):
    return {"users": users, "roles": roles}


class FakeApi:
    """Admin REST API over an in-memory auth store; records every mutating call."""

    def __init__(self, users, roles):
        self.users, self.roles, self.mutations = users, roles, []

    def __call__(self, method, path, body=None, params=None):
        if method != "GET":
            self.mutations.append((method, path))
        if path.endswith("/users/roles/list"):
            return {"roles": [{"id": i} for i in self.users[params["username"]]["role_ids"]]}
        if path.endswith("/roles/list"):
            return {"roles": [{"id": i, "name": r["name"], "workspace": "default"} for i, r in self.roles.items()]}
        if path.endswith("/roles/permissions/list"):
            return {"role_permissions": [{"resource_type": a, "resource_pattern": b, "permission": c}
                                         for a, b, c in self.roles[params["role_id"]]["permissions"]]}
        if path.endswith("/users/list"):
            return {"users": [{"username": n, "is_admin": u["is_admin"]} for n, u in self.users.items()]}
        if path.endswith("/roles/create"):
            rid = max(self.roles, default=0) + 1
            self.roles[rid] = {"name": body["name"], "permissions": []}
            return {"role": {"id": rid}}
        if path.endswith("/roles/permissions/add"):
            self.roles[body["role_id"]]["permissions"].append((body["resource_type"], body["resource_pattern"], body["permission"]))
            return {}
        if path.endswith("/roles/assign"):
            self.users[body["username"]]["role_ids"].append(body["role_id"])
            return {}
        raise AssertionError(path)


class RolePrecondition(unittest.TestCase):
    def base(self):
        users = {"admin": {"is_admin": True, "role_ids": [1]}, "assistant": {"is_admin": False, "role_ids": [2]},
                 "reader": {"is_admin": False, "role_ids": []}, "job": {"is_admin": False, "role_ids": []}}
        roles = {1: {"name": "gw-admin", "assignees": ["admin"], "permissions": [["gateway_endpoint", "1", "MANAGE"]]},
                 2: {"name": "gw-use", "assignees": ["assistant"], "permissions": [["gateway_endpoint", "1", "USE"]]}}
        return users, roles

    def test_clean_store_has_no_conflict(self):
        self.assertEqual(workspace_roles.conflicts(snap(*self.base()), ["job"], "assistant", ["7"]), [])

    def test_conflicts_are_reported(self):
        cases = []
        users, roles = self.base()
        roles[3] = {"name": "ipcch-readers", "assignees": [], "permissions": READERS + [["experiment", "*", "EDIT"]]}
        cases.append((users, roles, "managed role ipcch-readers"))
        users, roles = self.base()
        roles[3] = {"name": "legacy-edit", "assignees": ["reader"], "permissions": [["experiment", "4", "EDIT"]]}
        users["reader"]["role_ids"] = [3]
        cases.append((users, roles, "ordinary reader holds EDIT"))
        users, roles = self.base()
        users["assistant"]["is_admin"] = True
        cases.append((users, roles, "assistant identity is an administrator"))
        users, roles = self.base()
        roles[2]["permissions"] = [["gateway_endpoint", "1", "MANAGE"]]
        cases.append((users, roles, "assistant identity holds MANAGE"))
        users, roles = self.base()
        roles[3] = {"name": "ipcch-job-writers", "assignees": ["reader"], "permissions": [["workspace", "*", "USE"]]}
        cases.append((users, roles, "outside the job identities"))
        for users, roles, fragment in cases:
            found = workspace_roles.conflicts(snap(users, roles), ["job"], "assistant", ["7"])
            self.assertTrue(any(fragment in c for c in found), (fragment, found))

    def test_conflict_makes_no_change(self):
        users, roles = self.base()
        roles[3] = {"name": "legacy-edit", "permissions": [("experiment", "4", "EDIT")]}
        users["reader"]["role_ids"] = [3]
        api = FakeApi(users, {k: {"name": v["name"], "permissions": [tuple(p) for p in v["permissions"]]} for k, v in roles.items()})
        with self.assertRaisesRegex(RuntimeError, "no change made"):
            workspace_roles.apply(api, ["job"], ["7"], assistant_user="assistant")
        self.assertEqual(api.mutations, [])

    def test_assistant_declared_as_job_identity_is_refused_without_change(self):
        users, roles = self.base()
        api = FakeApi(users, {k: {"name": v["name"], "permissions": [tuple(p) for p in v["permissions"]]} for k, v in roles.items()})
        with self.assertRaisesRegex(RuntimeError, "also declared a job identity"):
            workspace_roles.apply(api, ["job", "assistant"], ["7"], assistant_user="assistant")
        self.assertEqual(api.mutations, [])

    def test_clean_apply_preserves_copied_state(self):
        users, roles = self.base()
        api = FakeApi(users, {k: {"name": v["name"], "permissions": [tuple(p) for p in v["permissions"]]} for k, v in roles.items()})
        report = workspace_roles.apply(api, ["job"], ["7"], assistant_user="assistant")
        self.assertEqual(report["preserved"], {"users": True, "roles": True})
        self.assertEqual(report["added"]["reader"]["effective_added"], [tuple(r) for r in sorted(map(tuple, READERS))])
        self.assertIn(("workspace", "*", "USE"), report["added"]["job"]["effective_added"])
        self.assertEqual(report["added"]["admin"]["role_ids"], [])


class AssistantProbePredicates(unittest.TestCase):
    def test_deny_probe_targets_the_given_run(self):
        run_id = "ab" * 16
        out = rehearsal_upstream.respond({"contents": [{"role": "user", "parts": [{"text": f"PROBE-DENY run={run_id}"}]}]})
        self.assertEqual(out["candidates"][0]["content"]["parts"][0]["functionCall"]["args"]["command"],
                         f"mlflow runs delete --run-id {run_id}")
        with self.assertRaises(ValueError):
            rehearsal_upstream.respond({"contents": [{"role": "user", "parts": [{"text": "PROBE-DENY now"}]}]})

    def stream(self, result):
        answer = rehearsal_upstream.respond({"contents": [
            {"role": "user", "parts": [{"text": "q"}]},
            {"role": "user", "parts": [{"functionResponse": {"name": "Bash", "response": {"result": result}}}]}]})
        text = answer["candidates"][0]["content"]["parts"][0]["text"]
        return "data: " + json.dumps({"content": text}) + "\n"   # as the assistant stream carries it (JSON-escaped)

    def test_listing_predicate_requires_a_successful_listing_with_the_object(self):
        table = "Experiment Id    Name\n---\n5    rehearsal-abc123\n"
        self.assertTrue(rehearse_assistant.listing_ok(self.stream(table), "rehearsal-abc123"))
        self.assertFalse(rehearse_assistant.listing_ok(self.stream("Error: experiment access denied"), "experiment"))
        self.assertFalse(rehearse_assistant.listing_ok(self.stream(table), "rehearsal-other"))
        self.assertFalse(rehearse_assistant.listing_ok("no answer at all", "rehearsal-abc123"))

    def test_denial_predicate_requires_the_allowlist_message(self):
        self.assertTrue(rehearse_assistant.denial_ok(self.stream(
            "Permission denied: this assistant may only run read-only commands: mlflow experiments search")))
        self.assertFalse(rehearse_assistant.denial_ok(self.stream("Run deleted")))


if __name__ == "__main__":
    unittest.main()
