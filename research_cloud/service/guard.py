"""Assistant spend guard: the one paid egress path of the MLflow service, admitted against a PostgreSQL ledger.

MLflow 3.17.0's Gateway budget policies check incurred cost only, record cost after completion (skipped when
usage tracking is off), and can continue when recording fails (see research/gateway-budget-supervisor.md). They stay
on as supporting signals. This guard is the small application guard design.md allows:

* Egress: ``mlflow.gateway.providers.utils._aiohttp_post`` is the Gateway's single outbound choke point (send_request,
  send_stream_request, proxy/passthrough). It is wrapped so the only permitted upstream is the pinned Vertex AI Gemini
  model's generateContent / streamGenerateContent URL; anything else is refused. LiteLLM, which bypasses the choke
  point, is excluded by MLflow's own ``MLFLOW_GATEWAY_ALLOWED_PROVIDERS=vertex_ai`` (checked at install).
* Payload contract: only the research assistant's text/function-calling shape is admitted (text, functionCall,
  functionResponse parts; function declarations only; a fixed set of generationConfig keys). Inline/file data,
  cached content, grounding/search/code-execution tools and non-text modalities, which carry inputs or charges the
  text input rate does not cover, are refused. Only one candidate is admitted (an explicit candidateCount other
  than 1 is refused; none is injected, as the Gemini 3.8 guide asks not to send it), ``thinkingBudget`` is refused
  (3.8 uses ``thinkingLevel``) and maxOutputTokens, which bounds response plus reasoning, is clamped.
* Reservation (no token estimate): every call reserves the pinned model's whole accepted input context
  (``model_max_input_tokens``, from the model card) at the highest applicable text input rate, plus the clamped
  maxOutputTokens times ``output_reservation_factor`` at the output rate. Google documents that maxOutputTokens
  includes thinking tokens; the factor (>= 1) covers reported thinking overshoot and is an evidenced assumption, not a
  guarantee. CountTokens is not used: Google describes it as an estimate. Actual usage above a reservation is still
  settled at its actual cost.
* Admission: before every provider call (each step of a multi-step assistant answer is its own call) a reservation
  priced at the conservative upper bound is inserted under a transaction-scoped advisory lock. It is admitted only if
  this month's charged total (settled actual cost; open or uncertain reservations at max(reserved, observed)) plus
  the reservation stays within the allocation and in-flight calls stay under the concurrency limit.
* Settlement: from the provider's raw ``usageMetadata``, counting thoughtsTokenCount (which MLflow's chat usage
  leaves out of completion_tokens) and toolUsePromptTokenCount. Missing, malformed, negative or inconsistent usage, or
  a stream without a finish, leaves the row ``uncertain``, charged at max(reservation, observed cost). A crashed
  process leaves ``reserved`` rows that keep counting toward spend.
* Concurrency: a ``reserved`` row counts as in flight until ``request_timeout_s`` + ``settle_grace_s`` after it was
  created. The guard enforces that deadline on the call itself (stream reads and JSON reads), and install requires
  MLflow's own MLFLOW_GATEWAY_ROUTE_TIMEOUT_SECONDS (the aiohttp total timeout) to be no longer, so an expired row is
  a terminated call or a dead process; it still counts toward spend.
* Failure: missing configuration, pricing or ledger state, or any guard error, refuses the call (HTTP 503).

The month is the Pacific-time calendar month of Cloud Billing invoices. This bounds this service's provider calls
only; billing delay, SQL/storage/Cloud Run cost and calls outside this service are outside it.
"""
import asyncio
import contextlib
import datetime
import json
import logging
import math
import os
import re
from decimal import Decimal
from zoneinfo import ZoneInfo

_log = logging.getLogger("ipcch_assistant_guard")
LOCK_KEY = 0x1FCC_A551   # pg_advisory_xact_lock key for the ledger
BILLING_TZ = ZoneInfo("America/Los_Angeles")
TEXT_FIELDS = ("dsn_env", "project", "location", "model", "price_source")
POSITIVE_NUMBERS = ("input_usd_per_mtok", "output_usd_per_mtok", "monthly_allocation_usd", "output_reservation_factor")
POSITIVE_INTS = ("model_max_input_tokens", "max_output_tokens", "max_request_bytes", "max_in_flight", "request_timeout_s")
NONNEGATIVE_INTS = ("settle_grace_s",)
PART_KEYS = {"text", "functionCall", "functionResponse", "thoughtSignature", "thought"}
TOP_KEYS = {"contents", "system_instruction", "systemInstruction", "generationConfig", "tools", "toolConfig"}
TOOL_KEYS = {"functionDeclarations", "function_declarations"}
GENERATION_KEYS = {"temperature", "topP", "topK", "maxOutputTokens", "stopSequences", "candidateCount", "presencePenalty",
                   "frequencyPenalty", "seed", "responseMimeType", "responseJsonSchema", "responseSchema", "thinkingConfig"}
THINKING_KEYS = {"thinkingLevel", "includeThoughts"}   # Gemini 3.8 controls reasoning by level, not budget
SCHEMA = """
CREATE TABLE IF NOT EXISTS ipcch_assistant_ledger (
    id bigserial PRIMARY KEY,
    billing_month text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    settled_at timestamptz,
    status text NOT NULL CHECK (status IN ('reserved', 'settled', 'uncertain', 'rejected')),
    model text NOT NULL,
    reserved_usd numeric(14, 8) NOT NULL,
    actual_usd numeric(14, 8),
    prompt_tokens bigint, output_tokens bigint, thought_tokens bigint, tool_prompt_tokens bigint,
    detail text
);
CREATE INDEX IF NOT EXISTS ipcch_assistant_ledger_month ON ipcch_assistant_ledger (billing_month, status);
"""


class GuardRefusal(Exception):
    """A provider call the guard does not admit."""


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def load_config(path):
    cfg = json.load(open(path))
    bad = [k for k in TEXT_FIELDS if not (isinstance(cfg.get(k), str) and cfg[k].strip())]
    bad += [k for k in POSITIVE_NUMBERS if not (isinstance(cfg.get(k), (int, float)) and not isinstance(cfg[k], bool)
                                                 and math.isfinite(cfg[k]) and cfg[k] > 0)]
    bad += [k for k in POSITIVE_INTS if not (_is_int(cfg.get(k)) and cfg[k] > 0)]
    bad += [k for k in NONNEGATIVE_INTS if not (_is_int(cfg.get(k)) and cfg[k] >= 0)]
    if bad:
        raise GuardRefusal(f"guard config {path}: missing or invalid {bad}")
    if cfg["output_reservation_factor"] < 1:
        raise GuardRefusal("guard config output_reservation_factor must be >= 1")
    if not os.environ.get(cfg["dsn_env"]):
        raise GuardRefusal(f"guard ledger DSN variable {cfg['dsn_env']} is not set")
    return cfg


def billing_month(now=None):
    return (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(BILLING_TZ).strftime("%Y-%m")


def cost_usd(cfg, prompt_tokens, output_tokens):
    """Output tokens include thinking tokens, which Gemini bills at the output rate."""
    return (Decimal(str(prompt_tokens)) * Decimal(str(cfg["input_usd_per_mtok"]))
            + Decimal(str(output_tokens)) * Decimal(str(cfg["output_usd_per_mtok"]))) / Decimal(1_000_000)


def parse_usage(usage):
    """Token counts from raw usageMetadata, or None when they cannot be trusted for settlement.

    promptTokenCount, candidatesTokenCount and totalTokenCount are required; thoughts/tool-prompt counts may be absent.
    Every count must be a non-negative integer and totalTokenCount must equal prompt + candidates + thoughts +
    tool-use prompt exactly (Vertex usageMetadata semantics; cachedContentTokenCount is part of promptTokenCount and
    caching is refused by the contract). An absent optional count is read as zero only because the exact total
    confirms it; any unexplained difference leaves the call uncertain at its reservation."""
    if not isinstance(usage, dict):
        return None
    counts = {}
    for k, required in (("promptTokenCount", True), ("candidatesTokenCount", True),
                        ("thoughtsTokenCount", False), ("toolUsePromptTokenCount", False)):
        v = usage.get(k)
        if v is None and not required:
            v = 0
        if not (_is_int(v) and v >= 0):
            return None
        counts[k] = v
    total = usage.get("totalTokenCount")
    if not (_is_int(total) and total == sum(counts.values())):
        return None
    return counts


def usage_cost(cfg, counts):
    prompt = counts["promptTokenCount"] + counts["toolUsePromptTokenCount"]
    output = counts["candidatesTokenCount"] + counts["thoughtsTokenCount"]
    return cost_usd(cfg, prompt, output), prompt, output


def target_pattern(cfg):
    host = "aiplatform.googleapis.com" if cfg["location"] == "global" else f"{cfg['location']}-aiplatform.googleapis.com"
    return re.compile(rf"https://{re.escape(host)}/v1/projects/{re.escape(cfg['project'])}/locations/"
                      rf"{re.escape(cfg['location'])}/publishers/google/models/{re.escape(cfg['model'])}"
                      r":(generateContent|streamGenerateContent\?alt=sse)")


def check_contract(payload):
    """Refuse anything outside the text/function-calling payload contract."""
    if not isinstance(payload, dict) or set(payload) - TOP_KEYS:
        raise GuardRefusal(f"unsupported request fields {sorted(set(payload) - TOP_KEYS) if isinstance(payload, dict) else payload!r}")
    system = payload.get("system_instruction") or payload.get("systemInstruction") or {"parts": []}
    for content in list(payload.get("contents") or []) + [system]:
        for part in content.get("parts") or []:
            if not isinstance(part, dict) or not part or set(part) - PART_KEYS:
                raise GuardRefusal(f"unsupported content part {sorted(part) if isinstance(part, dict) else part!r}")
    for tool in payload.get("tools") or []:
        if not isinstance(tool, dict) or set(tool) - TOOL_KEYS:
            raise GuardRefusal(f"unsupported tool {sorted(tool) if isinstance(tool, dict) else tool!r}")
    gen = payload.get("generationConfig") or {}
    if set(gen) - GENERATION_KEYS or set(gen.get("thinkingConfig") or {}) - THINKING_KEYS:
        raise GuardRefusal(f"unsupported generationConfig {sorted(set(gen) - GENERATION_KEYS)}")
    if gen.get("responseMimeType") not in (None, "text/plain", "application/json"):
        raise GuardRefusal(f"unsupported responseMimeType {gen['responseMimeType']!r}")


def reservation(cfg, out_tokens):
    """Upper reservation for one call: the full accepted input context plus the factor-scaled output cap."""
    return cost_usd(cfg, cfg["model_max_input_tokens"], math.ceil(out_tokens * cfg["output_reservation_factor"]))


def bound_payload(cfg, payload):
    """Admit one candidate only and clamp maxOutputTokens (which includes thinking); return (payload, output cap)."""
    gen = dict(payload.get("generationConfig") or {})
    if gen.get("candidateCount", 1) != 1:
        raise GuardRefusal(f"candidateCount {gen['candidateCount']!r} is not admitted (one candidate only)")
    requested = gen.get("maxOutputTokens", cfg["max_output_tokens"])
    if not (_is_int(requested) and requested > 0):
        raise GuardRefusal(f"unsupported maxOutputTokens {requested!r}")
    gen["maxOutputTokens"] = min(requested, cfg["max_output_tokens"])
    return {**payload, "generationConfig": gen}, gen["maxOutputTokens"]


class Ledger:
    def __init__(self, cfg, connect=None):
        import psycopg2
        self.cfg = cfg
        self.connect = connect or (lambda: psycopg2.connect(os.environ[cfg["dsn_env"]]))

    def ensure_schema(self):
        with contextlib.closing(self.connect()) as c, c, c.cursor() as cur:
            cur.execute(SCHEMA)

    def charged(self, cur, month):
        cur.execute("""SELECT COALESCE(SUM(CASE WHEN status = 'settled' THEN actual_usd
                                                 ELSE GREATEST(reserved_usd, COALESCE(actual_usd, 0)) END), 0)
                       FROM ipcch_assistant_ledger WHERE billing_month = %s AND status <> 'rejected'""", (month,))
        return cur.fetchone()[0]

    def reserve(self, amount, detail):
        month = billing_month()
        with contextlib.closing(self.connect()) as c, c, c.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
            charged = self.charged(cur, month)
            cur.execute("""SELECT count(*) FROM ipcch_assistant_ledger WHERE status = 'reserved'
                           AND created_at > now() - make_interval(secs => %s)""",
                        (self.cfg["request_timeout_s"] + self.cfg["settle_grace_s"],))
            in_flight = cur.fetchone()[0]
            limit = Decimal(str(self.cfg["monthly_allocation_usd"]))
            reason = (f"monthly allocation: charged {charged} + reservation {amount} > {limit}" if charged + amount > limit
                      else f"concurrency: {in_flight} calls in flight" if in_flight >= self.cfg["max_in_flight"] else None)
            status = "rejected" if reason else "reserved"
            cur.execute("""INSERT INTO ipcch_assistant_ledger (billing_month, status, model, reserved_usd, detail)
                           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                        (month, status, self.cfg["model"], amount if not reason else 0, reason or detail))
            row_id = cur.fetchone()[0]
        if reason:
            raise GuardRefusal(f"assistant call refused by spend guard ({reason})")
        return row_id

    def settle(self, row_id, usage, complete):
        """Settle from usage only when the call finished and its usage parses; otherwise mark it uncertain."""
        counts = parse_usage(usage)
        with contextlib.closing(self.connect()) as c, c, c.cursor() as cur:
            if counts is None:
                note = "no usage readback" if usage is None else "malformed usage readback"
                cur.execute("UPDATE ipcch_assistant_ledger SET status = 'uncertain', settled_at = now(), "
                            "detail = detail || %s WHERE id = %s AND status = 'reserved'", ("; " + note, row_id))
                return
            actual, prompt, output = usage_cost(self.cfg, counts)
            cur.execute("""UPDATE ipcch_assistant_ledger SET status = %s, settled_at = now(), actual_usd = %s,
                             prompt_tokens = %s, output_tokens = %s, thought_tokens = %s, tool_prompt_tokens = %s
                           WHERE id = %s AND status = 'reserved'""",
                        ("settled" if complete else "uncertain", actual, prompt, output, counts["thoughtsTokenCount"],
                         counts["toolUsePromptTokenCount"], row_id))


class _UsageCapture:
    """Wraps the aiohttp response handed to send_request/send_stream_request and keeps the last usageMetadata."""

    def __init__(self, response, deadline):
        self._response, self.usage, self.complete, self._deadline = response, None, False, deadline

    def _remaining(self):
        left = self._deadline - asyncio.get_running_loop().time()
        if left <= 0:
            raise asyncio.TimeoutError("assistant provider call exceeded the guard's request timeout")
        return left

    def __getattr__(self, name):
        return getattr(self._response, name)

    async def json(self, *args, **kwargs):
        js = await asyncio.wait_for(self._response.json(*args, **kwargs), self._remaining())
        if isinstance(js, dict) and isinstance(js.get("usageMetadata"), dict):
            self.usage, self.complete = js["usageMetadata"], True
        return js

    @property
    def content(self):
        return self._lines()

    async def _lines(self):
        lines = self._response.content.__aiter__()
        while True:
            try:
                line = await asyncio.wait_for(lines.__anext__(), self._remaining())
            except StopAsyncIteration:
                return
            text = line.decode("utf-8", errors="ignore").strip()
            if text.startswith("data:"):
                try:
                    chunk = json.loads(text[5:].strip())
                except ValueError:
                    chunk = None
                if isinstance(chunk, dict) and isinstance(chunk.get("usageMetadata"), dict):
                    self.usage = chunk["usageMetadata"]   # cumulative; the final chunk carries the totals
                    self.complete = any(c.get("finishReason") for c in chunk.get("candidates") or [])
            yield line


def make_egress(original, cfg, ledger):
    """Return the guarded replacement for providers.utils._aiohttp_post."""
    from fastapi import HTTPException
    from mlflow.gateway.utils import append_to_uri_path

    pattern = target_pattern(cfg)

    @contextlib.asynccontextmanager
    async def guarded(headers, base_url, path, payload, *, ssrf_protect=True):
        url = append_to_uri_path(base_url, path)
        if not pattern.fullmatch(url):
            raise HTTPException(status_code=403, detail="upstream not permitted by the IPCCH assistant guard")
        try:
            check_contract(payload)
            body, out_tokens = bound_payload(cfg, payload)
            size = len(json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode())
            if size > cfg["max_request_bytes"]:   # a request-size limit, not a cost bound
                raise GuardRefusal(f"request of {size} bytes exceeds max_request_bytes")
            amount = reservation(cfg, out_tokens)
            row_id = await asyncio.to_thread(ledger.reserve, amount, f"{cfg['model']} {size}B out<={out_tokens}")
        except GuardRefusal as e:
            raise HTTPException(status_code=503, detail=str(e)) from None
        except Exception as e:   # unknown guard state never admits a paid call
            raise HTTPException(status_code=503, detail=f"assistant spend guard unavailable ({type(e).__name__})") from None
        capture = None
        deadline = asyncio.get_running_loop().time() + cfg["request_timeout_s"]
        try:
            async with original(headers, base_url, path, body, ssrf_protect=ssrf_protect) as response:
                capture = _UsageCapture(response, deadline)
                yield capture
        finally:
            usage = capture.usage if capture is not None else None
            complete = capture is not None and capture.complete
            # an uncertain row is charged at max(reservation, observed), so a partial readback never lowers it;
            # if settlement itself fails the row stays 'reserved' and keeps counting at its reservation
            try:
                await asyncio.to_thread(ledger.settle, row_id, usage, complete)
            except Exception:
                _log.exception("assistant ledger settlement failed for row %s; reservation retained", row_id)

    guarded._ipcch_guard = True
    return guarded


def deny_all():
    from fastapi import HTTPException

    @contextlib.asynccontextmanager
    async def denied(*args, **kwargs):
        raise HTTPException(status_code=503, detail="assistant provider calls are disabled on this server")
        yield  # pragma: no cover

    denied._ipcch_guard = True
    return denied


def install(config_path=None):
    """Install the egress guard into this process. Returns ``"armed"`` or ``"deny"``; raises if it cannot install."""
    from importlib.metadata import version

    import mlflow.gateway.providers.utils as utils
    from mlflow.utils.provider_filter import is_provider_allowed

    if version("mlflow") != "3.17.0":
        raise RuntimeError(f"guard is written against mlflow 3.17.0, found {version('mlflow')}")
    if getattr(utils._aiohttp_post, "_ipcch_guard", False):
        return getattr(utils, "_ipcch_guard_mode")
    original = utils._aiohttp_post
    mode = "deny"
    if config_path:
        from mlflow.environment_variables import MLFLOW_GATEWAY_ROUTE_TIMEOUT_SECONDS

        cfg = load_config(config_path)
        if is_provider_allowed("litellm") or not is_provider_allowed("vertex_ai"):
            raise GuardRefusal("MLFLOW_GATEWAY_ALLOWED_PROVIDERS must allow vertex_ai only")
        if MLFLOW_GATEWAY_ROUTE_TIMEOUT_SECONDS.get() > cfg["request_timeout_s"]:
            raise GuardRefusal("MLFLOW_GATEWAY_ROUTE_TIMEOUT_SECONDS must not exceed the guard's request_timeout_s")
        ledger = Ledger(cfg)
        ledger.ensure_schema()
        utils._aiohttp_post = make_egress(original, cfg, ledger)
        mode = "armed"
    else:
        if is_provider_allowed("litellm") or is_provider_allowed("bedrock"):
            raise GuardRefusal("MLFLOW_GATEWAY_ALLOWED_PROVIDERS must exclude SDK-client providers in deny mode too")
        utils._aiohttp_post = deny_all()
    utils._ipcch_guard_mode = mode
    return mode
