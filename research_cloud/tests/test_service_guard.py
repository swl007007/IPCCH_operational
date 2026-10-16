"""Assistant spend guard: payload contract, bounds, usage parsing, PostgreSQL admission and the guarded egress path.

Ledger/egress tests need a disposable PostgreSQL given by RC_TEST_PG (libpq string without dbname, superuser).
No provider is called: the guarded egress wraps a fake upstream.
"""
import asyncio
import contextlib
import json
import os
import tempfile
import unittest
import uuid
from decimal import Decimal

from research_cloud.service import guard

PG = os.environ.get("RC_TEST_PG")
URL_BASE = "https://us-central1-aiplatform.googleapis.com/v1/projects/p-test/locations/us-central1/publishers/google/models"


def config(**over):
    cfg = {"dsn_env": "RC_GUARD_TEST_DSN", "project": "p-test", "location": "us-central1", "model": "gemini-test",
           "price_source": "test", "input_usd_per_mtok": 1.0, "output_usd_per_mtok": 10.0, "monthly_allocation_usd": 1.0,
           "model_max_input_tokens": 100_000, "output_reservation_factor": 2, "max_output_tokens": 1000,
           "max_request_bytes": 50_000, "max_in_flight": 2, "request_timeout_s": 60, "settle_grace_s": 30}
    cfg.update(over)
    return cfg


def write_config(cfg):
    path = os.path.join(tempfile.mkdtemp(), "guard.json")
    json.dump(cfg, open(path, "w"))
    return path


def chat(text="hello", **gen):
    body = {"contents": [{"role": "user", "parts": [{"text": text}]}],
            "tools": [{"functionDeclarations": [{"name": "mlflow", "parameters": {"type": "object"}}]}]}
    if gen:
        body["generationConfig"] = gen
    return body


class ConfigAndContract(unittest.TestCase):
    def setUp(self):
        os.environ["RC_GUARD_TEST_DSN"] = "dbname=unused"

    def test_every_limit_is_validated(self):
        guard.load_config(write_config(config()))
        for key, value in (("max_output_tokens", 0), ("max_in_flight", True), ("request_timeout_s", 1.5),
                           ("settle_grace_s", -1), ("input_usd_per_mtok", float("nan")), ("output_reservation_factor", 0.5),
                           ("monthly_allocation_usd", "10"), ("model_max_input_tokens", None), ("model", " "),
                           ("output_usd_per_mtok", float("inf"))):
            with self.assertRaises(guard.GuardRefusal, msg=key):
                guard.load_config(write_config(config(**{key: value})))

    def test_unsupported_inputs_are_refused(self):
        guard.check_contract(chat())
        bad = [{"contents": [{"role": "user", "parts": [{"inlineData": {"mimeType": "image/png", "data": "AA=="}}]}]},
               {"contents": [{"role": "user", "parts": [{"fileData": {"fileUri": "gs://b/video.mp4"}}]}]},
               dict(chat(), cachedContent="projects/p/cachedContents/1"),
               dict(chat(), tools=[{"googleSearch": {}}]),
               dict(chat(), tools=[{"codeExecution": {}}]),
               chat(responseModalities=["AUDIO"]),
               chat(responseMimeType="image/png"),
               chat(thinkingConfig={"thinkingLevel": "HIGH", "mediaResolution": "x"}),
               {"contents": [{"role": "user", "parts": [{}]}]}]
        for payload in bad:
            with self.assertRaises(guard.GuardRefusal, msg=json.dumps(payload)[:80]):
                guard.check_contract(payload)

    def test_bounds_force_one_candidate_and_clamp_output(self):
        cfg = config()
        body, out = guard.bound_payload(cfg, chat(candidateCount=4, maxOutputTokens=99_999, thinkingConfig={"thinkingLevel": "HIGH"}))
        gen = body["generationConfig"]
        self.assertEqual((gen["candidateCount"], gen["maxOutputTokens"], out), (1, 1000, 1000))
        self.assertEqual(guard.bound_payload(cfg, chat())[1], 1000)        # absent cap -> configured cap
        for gen_bad in ({"maxOutputTokens": 0}, {"maxOutputTokens": 2.5}, {"maxOutputTokens": "10"}):
            with self.assertRaises(guard.GuardRefusal):
                guard.bound_payload(cfg, chat(**gen_bad))

    def test_reservation_is_full_input_context_plus_scaled_output_cap(self):
        # 100,000 input tokens at $1/M + 2 x 1,000 output tokens at $10/M, whatever the request size
        self.assertEqual(guard.reservation(config(), 1000), Decimal("0.12"))
        # 333 x 1.5 = 499.5 output tokens, rounded up to 500
        self.assertEqual(guard.reservation(config(output_reservation_factor=1.5), 333), Decimal("0.105"))

    def test_unexplained_total_is_not_settled_low(self):
        # regression: 15 itemized tokens against a 10,000 total must not settle at the 15
        self.assertIsNone(guard.parse_usage({"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 10_000}))
        self.assertEqual(guard.parse_usage({"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15}),
                         {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 0, "toolUsePromptTokenCount": 0})

    def test_usage_must_be_complete_and_well_formed(self):
        good = {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 7, "totalTokenCount": 22}
        counts = guard.parse_usage(good)
        self.assertEqual(guard.usage_cost(config(), counts)[1:], (10, 12))     # thinking billed as output
        for bad in (None, {}, {"promptTokenCount": 10}, dict(good, candidatesTokenCount=-1),
                    dict(good, promptTokenCount=1.0), dict(good, thoughtsTokenCount="7"), dict(good, totalTokenCount=3),
                    dict(good, candidatesTokenCount=True), {k: v for k, v in good.items() if k != "totalTokenCount"}):
            self.assertIsNone(guard.parse_usage(bad), msg=bad)


class FakeContent:
    def __init__(self, lines, hang=False):
        self.lines, self.hang = lines, hang

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for line in self.lines:
            yield line
        if self.hang:
            await asyncio.sleep(3600)


class FakeResponse:
    def __init__(self, body=None, lines=(), hang=False):
        self.body, self.content = body, FakeContent(list(lines), hang)

    async def json(self):
        return self.body


def sse(chunk):
    return ("data: " + json.dumps(chunk) + "\n").encode()


@unittest.skipUnless(PG, "RC_TEST_PG not set")
class LedgerAndEgress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg2
        cls.db = "guard_" + uuid.uuid4().hex[:10]
        admin = psycopg2.connect(PG + " dbname=postgres")
        admin.autocommit = True
        admin.cursor().execute(f"CREATE DATABASE {cls.db}")
        admin.close()
        os.environ["RC_GUARD_TEST_DSN"] = f"{PG} dbname={cls.db}"

    @classmethod
    def tearDownClass(cls):
        import psycopg2
        admin = psycopg2.connect(PG + " dbname=postgres")
        admin.autocommit = True
        admin.cursor().execute(f"DROP DATABASE {cls.db} WITH (FORCE)")
        admin.close()

    def setUp(self):
        self.cfg = config()
        self.ledger = guard.Ledger(self.cfg)
        self.ledger.ensure_schema()
        self.sql("TRUNCATE ipcch_assistant_ledger")

    def sql(self, statement, args=()):
        with contextlib.closing(self.ledger.connect()) as c, c, c.cursor() as cur:
            cur.execute(statement, args)
            return cur.fetchall() if cur.description else None

    def rows(self):
        return self.sql("SELECT status, reserved_usd, actual_usd, thought_tokens FROM ipcch_assistant_ledger ORDER BY id")

    def test_allocation_counts_open_uncertain_and_settled_rows(self):
        a = self.ledger.reserve(Decimal("0.4"), "a")
        b = self.ledger.reserve(Decimal("0.4"), "b")
        with self.assertRaises(guard.GuardRefusal):          # 0.8 charged + 0.4 > 1.0
            self.ledger.reserve(Decimal("0.4"), "c")
        self.ledger.settle(a, {"promptTokenCount": 1000, "candidatesTokenCount": 100, "thoughtsTokenCount": 900,
                                "totalTokenCount": 2000}, True)
        self.ledger.settle(b, {"promptTokenCount": 10}, True)   # malformed: stays charged at its reservation
        self.assertEqual([r[0] for r in self.rows()], ["settled", "uncertain", "rejected"])
        self.assertEqual(self.rows()[0][2:], (Decimal("0.01100000"), 900))
        self.ledger.reserve(Decimal("0.5"), "d")              # 0.011 + 0.4 + 0.5 <= 1.0
        with self.assertRaises(guard.GuardRefusal):
            self.ledger.reserve(Decimal("0.1"), "e")

    def test_partial_readback_never_lowers_the_charge(self):
        a = self.ledger.reserve(Decimal("0.3"), "a")
        self.ledger.settle(a, {"promptTokenCount": 10, "candidatesTokenCount": 1, "totalTokenCount": 11}, False)   # stream without finish
        self.assertEqual(self.rows()[0][0], "uncertain")
        with self.assertRaises(guard.GuardRefusal):
            self.ledger.reserve(Decimal("0.71"), "b")          # charged at max(0.3, observed) = 0.3

    def test_concurrency_expires_only_after_enforced_timeout_but_spend_remains(self):
        self.ledger.reserve(Decimal("0.1"), "a")
        self.ledger.reserve(Decimal("0.1"), "b")
        with self.assertRaisesRegex(guard.GuardRefusal, "concurrency"):
            self.ledger.reserve(Decimal("0.1"), "c")
        self.sql("UPDATE ipcch_assistant_ledger SET created_at = now() - interval '89 seconds' WHERE status = 'reserved'")
        with self.assertRaisesRegex(guard.GuardRefusal, "concurrency"):   # 60 s timeout + 30 s grace not yet passed
            self.ledger.reserve(Decimal("0.1"), "c")
        self.sql("UPDATE ipcch_assistant_ledger SET created_at = now() - interval '91 seconds' WHERE status = 'reserved'")
        self.ledger.reserve(Decimal("0.75"), "d")
        with self.assertRaisesRegex(guard.GuardRefusal, "allocation"):   # expired reservations still count to spend
            self.ledger.reserve(Decimal("0.1"), "e")

    def run_egress(self, response=None, path="gemini-test:streamGenerateContent?alt=sse", payload=None, ledger=None,
                   consume="lines"):
        calls = []

        @contextlib.asynccontextmanager
        async def upstream(headers, base_url, path, payload, *, ssrf_protect=True):
            calls.append(payload)
            yield response

        egress = guard.make_egress(upstream, self.cfg, ledger or self.ledger)

        async def go():
            async with egress({}, URL_BASE, path, payload or chat()) as r:
                if consume == "lines":
                    return [line async for line in r.content]
                return await r.json()
        return asyncio.run(go()), calls

    def test_stream_settles_with_thinking_tokens(self):
        usage = {"promptTokenCount": 50, "candidatesTokenCount": 20, "thoughtsTokenCount": 30, "totalTokenCount": 100}
        lines = [sse({"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}),
                 sse({"candidates": [{"finishReason": "STOP"}], "usageMetadata": usage})]
        out, calls = self.run_egress(FakeResponse(lines=lines))
        self.assertEqual(len(out), 2)
        self.assertEqual(calls[0]["generationConfig"]["maxOutputTokens"], 1000)
        status, reserved, actual, thoughts = self.rows()[0]
        self.assertEqual((status, actual, thoughts), ("settled", Decimal("0.00055000"), 30))
        self.assertGreater(reserved, actual)

    def test_stream_without_finish_or_with_bad_usage_stays_uncertain(self):
        self.run_egress(FakeResponse(lines=[sse({"usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 1}})]))
        self.run_egress(FakeResponse({"usageMetadata": {"promptTokenCount": -5, "candidatesTokenCount": 1}}),
                        path="gemini-test:generateContent", consume="json")
        self.assertEqual([r[0] for r in self.rows()], ["uncertain", "uncertain"])

    def test_refusals_happen_before_any_upstream_call(self):
        from fastapi import HTTPException
        cases = [dict(path="other-model:generateContent"),
                 dict(payload={"contents": [{"role": "user", "parts": [{"fileData": {"fileUri": "gs://b/x"}}]}]}),
                 dict(payload=chat("x" * 60_000)),
                 dict(ledger=guard.Ledger(self.cfg, connect=lambda: (_ for _ in ()).throw(OSError("db down"))))]
        for case in cases:
            with self.assertRaises(HTTPException, msg=str(case)[:60]) as ctx:
                self.run_egress(FakeResponse(lines=[]), **case)
            self.assertIn(ctx.exception.status_code, (403, 503))
        self.assertEqual(self.rows(), [])

    def test_hung_stream_is_cut_at_the_request_timeout(self):
        self.cfg["request_timeout_s"] = 1
        with self.assertRaises(asyncio.TimeoutError):
            self.run_egress(FakeResponse(lines=[sse({"candidates": []})], hang=True))
        self.assertEqual(self.rows()[0][0], "uncertain")


if __name__ == "__main__":
    unittest.main()
