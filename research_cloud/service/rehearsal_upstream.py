"""Local rehearsal only: a fake Vertex AI Gemini upstream beneath the spend guard.

Loaded by ``hook.py`` only when ``IPCCH_REHEARSAL_FAKE_VERTEX=1``, and refused when ``K_SERVICE`` is set (Cloud Run),
so a deployed service can never use it. It replaces the Gateway's raw ``_aiohttp_post`` *before* the guard wraps it,
and gives Vertex credentials a dummy token, so everything above it runs unchanged: the assistant, its Gateway
self-call with the read-only identity, the provider allowlist, the guard's URL pin, payload contract, reservation
and settlement, and the assistant patch's tool allowlist.

Scripted model: the first turn calls the Bash tool with an ``mlflow experiments search`` command, or, when the user
message contains ``PROBE-DENY run=<run_id>``, with the prohibited ``mlflow runs delete --run-id <run_id>`` aimed at
that real run. Once a tool result is in the history it answers ``REHEARSAL-ANSWER <<<`` + the full tool result
(up to 4,000 characters) + ``>>>``. Each response carries exact
usageMetadata (including thinking tokens) so the ledger settles.
"""
import contextlib
import json
import os
import re

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
        response = results[-1].get("response")
        text = response.get("result") if isinstance(response, dict) and isinstance(response.get("result"), str) else json.dumps(response)
        part = {"text": f"REHEARSAL-ANSWER <<<{text[:4000]}>>>"}
    else:
        asked = json.dumps(contents)
        if "PROBE-DENY" in asked:
            target = re.search(r"PROBE-DENY run=([0-9a-f]{32})", asked)
            if not target:
                raise ValueError("PROBE-DENY needs run=<32-hex run id>")
            command = f"mlflow runs delete --run-id {target.group(1)}"
        else:
            command = "mlflow experiments search --max-results 50"
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


def quoted_tool_result(stream_text):
    """The tool result the scripted model quoted back, or None. Stream text is JSON-escaped SSE."""
    m = re.search(r"REHEARSAL-ANSWER <<<(.*?)>>>", stream_text, re.S)
    if not m:
        return None
    try:
        return json.loads('"' + m.group(1) + '"')   # undo one level of JSON string escaping
    except ValueError:
        return m.group(1)
