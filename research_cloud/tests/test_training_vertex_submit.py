"""vertex_submit admission against a temporary ledger and a fake provider: one POST per reservation (a repeated or
concurrent submit is refused at the atomic claim), ambiguous outcomes stay held and are reconciled by the claim label,
specs larger than the reservation are refused, and poll records nothing unless HTTP 200 returns the bound job."""
import json
import os
import tempfile
import threading
import unittest

from research_cloud.cost import ledger as L
from research_cloud.training import vertex_submit as vs

DETAIL = {"machine": "n1-standard-4", "trials": 1, "timeout_s": 900, "boot_disk_gib": 100}


def spec(machine="n1-standard-4", timeout="900s", retries=True):
    return {"displayName": "t", "jobSpec": {"workerPoolSpecs": [{"machineSpec": {"machineType": machine}, "replicaCount": "1",
                                                                 "containerSpec": {"imageUri": "i@sha256:x"}}],
                                            "scheduling": {"timeout": timeout, "disableRetries": retries}}}


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.content = json.dumps(body).encode()

    def json(self):
        return self._body


class Provider:
    def __init__(self):
        self.posts, self.jobs, self.lose_ack, self.lock = [], {}, False, threading.Lock()

    def post(self, url, headers=None, json=None, timeout=None):
        with self.lock:
            name = f"projects/p/locations/us-central1/customJobs/{len(self.posts) + 1}"
            self.posts.append(json)
            self.jobs[name] = {"name": name, "state": "JOB_STATE_PENDING", "labels": json["labels"]}
        if self.lose_ack:
            raise TimeoutError("lost acknowledgement")
        return Resp(200, self.jobs[name])

    def get(self, url, headers=None, params=None, timeout=None):
        if params and "filter" in params:
            claim = params["filter"].split('"')[1]
            return Resp(200, {"customJobs": [j for j in self.jobs.values() if j["labels"].get("ipcch-claim") == claim]})
        name = url.split("/v1/", 1)[1]
        return Resp(200, self.jobs[name]) if name in self.jobs else Resp(404, {})


class Submit(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.conn = L.connect(os.path.join(self.dir, "l.sqlite"))
        L.reserve(self.conn, "training", "2026-10", "op", 0.1, json.dumps(DETAIL))
        self.p = Provider()
        vs.requests = type("R", (), {"post": staticmethod(self.p.post), "get": staticmethod(self.p.get)})
        vs.headers = lambda: {}

    def write(self, body):
        path = os.path.join(self.dir, "spec.json")
        json.dump(body, open(path, "w"))
        return path

    def test_single_post_and_repeat_refused(self):
        path = self.write(spec())
        self.assertEqual(vs.submit(self.conn, path, "custom", "op", self.dir), 0)
        with self.assertRaises(SystemExit):
            vs.submit(self.conn, path, "custom", "op", self.dir)
        self.assertEqual(len(self.p.posts), 1)
        self.assertEqual(L._get(self.conn, "op")[1], "projects/p/locations/us-central1/customJobs/1")

    def test_concurrent_submits_post_once(self):
        path, results = self.write(spec()), []

        def go():
            conn = L.connect(os.path.join(self.dir, "l.sqlite"))
            try:
                results.append(vs.submit(conn, path, "custom", "op", self.dir))
            except (SystemExit, L.LedgerError) as e:
                results.append(type(e).__name__)
        threads = [threading.Thread(target=go) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(self.p.posts), 1)
        self.assertEqual(results.count(0), 1)

    def test_lost_ack_held_then_reconciled_never_retried(self):
        path = self.write(spec())
        self.p.lose_ack = True
        self.assertEqual(vs.submit(self.conn, path, "custom", "op", self.dir), 2)
        self.assertTrue(L._get(self.conn, "op")[1].startswith("claim:"))
        with self.assertRaises(SystemExit):
            vs.submit(self.conn, path, "custom", "op", self.dir)           # held claim: no second POST
        self.assertEqual(len(self.p.posts), 1)
        with self.assertRaises(L.LedgerError):
            L.release(self.conn, "op", "evidence")                          # a claim blocks plain release
        self.assertEqual(vs.reconcile(self.conn, "custom", "op", self.dir), 0)
        self.assertEqual(L._get(self.conn, "op")[1], "projects/p/locations/us-central1/customJobs/1")

    def test_absent_job_released_only_with_lookup(self):
        path = self.write(spec())
        self.p.lose_ack = True
        vs.submit(self.conn, path, "custom", "op", self.dir)
        self.p.jobs.clear()                                                 # the provider never created it
        self.assertEqual(vs.reconcile(self.conn, "custom", "op", self.dir), 1)
        self.assertEqual(L._get(self.conn, "op")[0], "reserved")
        self.assertEqual(vs.reconcile(self.conn, "custom", "op", self.dir, release_if_absent=True), 0)
        self.assertEqual(L._get(self.conn, "op")[0], "released")

    def test_spec_larger_than_reservation_refused_before_claim(self):
        for body in (spec(machine="n1-highmem-16"), spec(timeout="7200s"), spec(retries=False)):
            with self.assertRaises(SystemExit):
                vs.submit(self.conn, self.write(body), "custom", "op", self.dir)
        self.assertEqual((self.p.posts, L._get(self.conn, "op")[1]), ([], None))

    def test_poll_requires_bound_name_and_200(self):
        path = self.write(spec())
        vs.submit(self.conn, path, "custom", "op", self.dir)
        name = L._get(self.conn, "op")[1]
        self.p.jobs[name]["name"] = "projects/p/locations/us-central1/customJobs/999"   # provider returns another job
        with self.assertRaises(SystemExit):
            vs.poll(self.conn, "custom", "op", self.dir, sleep=lambda s: None)
        self.p.jobs[name]["name"] = name
        del self.p.jobs[name]                                                # HTTP 404
        with self.assertRaises(SystemExit):
            vs.poll(self.conn, "custom", "op", self.dir, sleep=lambda s: None)
        self.assertIsNone(L._get(self.conn, "op")[2])                        # nothing observed
        self.p.jobs[name] = {"name": name, "state": "JOB_STATE_SUCCEEDED", "labels": {}}
        self.assertEqual(vs.poll(self.conn, "custom", "op", self.dir, sleep=lambda s: None), 0)
        self.assertEqual(L._get(self.conn, "op")[2], "JOB_STATE_SUCCEEDED")


if __name__ == "__main__":
    unittest.main()
