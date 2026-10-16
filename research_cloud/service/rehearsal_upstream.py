"""Local rehearsal only: a fake Vertex AI Gemini upstream beneath the spend guard.

Loaded by ``hook.py`` only when ``IPCCH_REHEARSAL_FAKE_VERTEX=1``, and refused when ``K_SERVICE`` is set (Cloud Run),
so a deployed service can never use it. It replaces the Gateway's raw ``_aiohttp_post`` *before* the guard wraps it,
and gives Vertex credentials a dummy token, so everything above it runs unchanged: the assistant, its Gateway
self-call with the read-only identity, the provider allowlist, the guard's URL pin, payload contract, reservation
and settlement, and the assistant patch's tool allowlist.

Scripted model: the first turn calls the Bash tool with an ``mlflow experiments search`` command (or, when the
user message contains ``PROBE-DENY``, with a prohibited ``mlflow runs delete`` command); once a tool result is in
the history it answers with text that quotes the tool result's first 120 characters. Each response carries exact
usageMetadata (including thinking tokens) so the ledger settles.
"""
import contextlib
import json
import os

USAGE = {"promptTokenCount": 120, "candidatesTokenCount": 30, "thoughtsTokenCount": 50, "totalTokenCount": 200}


class _Content:
    def __init__(self, lines):
        self._lines = lines

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for line in self._lines:
            yield line


class _Response:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, body, stream):
        self._body = body
        self.content = _Content([("data: " + json.dumps(body) + "\n\n").encode()] if stream else [])

    def raise_for_status(self):
        return None

    async def json(self, *args, **kwargs):
        return self._body

    async def text(self):
        return json.dumps(self._body)


def respond(payload):
    contents = payload.get("contents") or []
    results = [p["functionResponse"] for c in contents for p in c.get("parts") or [] if "functionResponse" in p]
    if results:
        quoted = json.dumps(results[-1].get("response"))[:120]
        part = {"text": f"REHEARSAL-ANSWER tool said: {quoted}"}
    else:
        asked = json.dumps(contents)
        command = ("mlflow runs delete --run-id 0" if "PROBE-DENY" in asked else "mlflow experiments search --max-results 5")
        part = {"functionCall": {"name": "Bash", "args": {"command": command}}}
    return {"candidates": [{"content": {"role": "model", "parts": [part]}, "finishReason": "STOP", "index": 0}],
            "usageMetadata": dict(USAGE)}


def install():
    if os.environ.get("K_SERVICE"):
        raise RuntimeError("the fake Vertex upstream is for local rehearsal only")
    import mlflow.gateway.providers.utils as utils
    from mlflow.gateway.providers.vertex_ai import VertexAIProvider

    @contextlib.asynccontextmanager
    async def fake_post(headers, base_url, path, payload, *, ssrf_protect=True):
        yield _Response(respond(payload), stream="streamGenerateContent" in path)

    class _Token:
        token, valid = "rehearsal-token", True

    utils._aiohttp_post = fake_post
    VertexAIProvider._get_credentials = lambda self: _Token()
