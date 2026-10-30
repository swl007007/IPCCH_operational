"""Four-operation delivery request contract v2 (task 10-29; prd.md R5, R17, R19, R23, R36-R39, R50, R60, R66 and the
final convergence corrections).

A v2 request selects any of four operations - IPCCH feature generation, IPCCH inference, FEWS NET feature
generation, FEWS NET inference - under an explicit ``mode`` (``smoke`` | ``real``; no default). Validation is
all-or-nothing and happens before any collection, retained-store mutation or inference (R17): an invalid request
executes nothing. The order is the design.md order:

1. structure (exact keys, references are immutable ``{uri, generation, sha256}``);
2. mode rules: smoke selects IPCCH operations only (R38) and publishes only into the smoke namespace (R36/R48);
3. operation conflicts: generation + inference of IPCCH never names a batch; IPCCH inference-only names exactly one
   feature batch and selects no IPCCH input refresh (ACLED, research_inputs, history_snapshot, WFP: R19/FCC1);
   FEWS NET inference-only names a prepared snapshot, generation + inference consumes this run's prepare (R60);
4. derived dates from the single execution month M (R23): feature origin O = M - 2, public targets M, M+6, M+12 for
   model horizons H2/H8/H14; and the month rules (R39, UTC): real requests never name a future M, and a real IPCCH
   inference published to current never names an M earlier than the IPCCH month of the current release (candidate is
   exempt from that comparison, FCC6; generation-only is unconstrained). Smoke performs no wall-clock or current check.
   These month rules and the M - 2 derivation apply to IPCCH operations only; FEWS NET month handling is unchanged.

Reference identities (``verify_reference_identities``), the per-system lock (R50) and admission are later steps; the
current-release comparison is repeated at publication time by the publisher (R39). Legacy v1 requests keep the
``delivery_manifest`` validator.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import date, datetime, timezone
from typing import Any

from cloud.orchestrator.delivery_manifest import (
    _GENERATION_RE,
    _REQUEST_PATH_RE,
    _RUN_ID_RE,
    DeliveryManifestError,
    ReferenceIdentityError,
    _exact_keys,
    _month,
    _ref,
    _release,
    _runtime,
    _source_choice,
    _text,
    _timestamp,
)
from cloud.common.object_refs import normalize_gcs_ref

SCHEMA_VERSION = "fewsnet-ipcch-delivery-request-v2"
MODES = ("smoke", "real")
OPERATIONS = ("ipcch_generation", "ipcch_inference", "fewsnet_generation", "fewsnet_inference")
PUBLICATIONS = ("candidate", "current")
MODEL_HORIZONS = (2, 8, 14)
PUBLIC_LEADS = {2: 0, 8: 6, 14: 12}
FEATURE_ORIGIN_OFFSET = -2
RESEARCH_FAMILIES = ("nino34_anom", "bbg_staple_food", "bbg_oilgas", "bbg_soybean_oil", "bbg_global_food",
                     "food_price_index_WB", "idp_national", "idp_local")
TOP_LEVEL_FIELDS = ("schema_version", "run_id", "mode", "execution_month", "operations", "ipcch", "fewsnet",
                    "publication", "runtime", "release", "operator", "prepared_at")
IPCCH_REFRESH_INPUTS = ("acled", "research_inputs", "history_snapshot", "wfp")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DeliveryRequestV2Error(DeliveryManifestError):
    """A v2 request failed validation; nothing was executed."""


def is_v2(data: Any) -> bool:
    return isinstance(data, Mapping) and data.get("schema_version") == SCHEMA_VERSION


def validate_request_v2(
    data: Mapping[str, Any],
    *,
    request_uri: str,
    request_generation: str,
    now_utc: datetime,
    production_namespace: str,
    smoke_namespace: str,
    current_ipcch_execution_month: str | None,
) -> dict[str, Any]:
    """Validate one v2 request (steps 1-4 of the module docstring) and return it with derived dates.

    ``current_ipcch_execution_month`` is the IPCCH execution month recorded by the current release (for a legacy-era
    release its ``origin_month``), or ``None`` when no IPCCH member is current."""
    try:
        return _validate(data, request_uri, request_generation, now_utc, production_namespace, smoke_namespace,
                         current_ipcch_execution_month)
    except DeliveryRequestV2Error:
        raise
    except DeliveryManifestError as exc:      # shared v1 helpers raise the base class
        raise DeliveryRequestV2Error(str(exc)) from exc


def _validate(data, request_uri, request_generation, now_utc, production_namespace, smoke_namespace, current_month):
    if not isinstance(data, Mapping):
        raise DeliveryRequestV2Error("request must be a JSON object")
    _exact_keys(data, TOP_LEVEL_FIELDS, "request")
    if data["schema_version"] != SCHEMA_VERSION:
        raise DeliveryRequestV2Error(f"schema_version must be {SCHEMA_VERSION}")
    run_id = data["run_id"]
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise DeliveryRequestV2Error("run_id must be 3-63 lowercase [a-z0-9._-] characters")
    path = _REQUEST_PATH_RE.fullmatch(request_uri or "")
    if path is None or path.group(1) != run_id:
        raise DeliveryRequestV2Error("request_uri must be gs://<bucket>/requests/<run_id>/run_manifest.json for this run_id")
    if not isinstance(request_generation, str) or _GENERATION_RE.fullmatch(request_generation) is None:
        raise DeliveryRequestV2Error("request_generation must be a positive integer string")

    # --- 1. structure
    mode = data["mode"]
    if mode not in MODES:
        raise DeliveryRequestV2Error(f"mode must be one of {MODES} (no default)")
    month = _month(data["execution_month"], "execution_month")
    ops = data["operations"]
    _exact_keys(ops, OPERATIONS, "operations")
    if any(type(ops[k]) is not bool for k in OPERATIONS):
        raise DeliveryRequestV2Error("operations values must be booleans")
    if not any(ops.values()):
        raise DeliveryRequestV2Error("operations select no step")
    ipcch_selected = ops["ipcch_generation"] or ops["ipcch_inference"]
    fews_selected = ops["fewsnet_generation"] or ops["fewsnet_inference"]
    if (data["ipcch"] is None) == ipcch_selected:
        raise DeliveryRequestV2Error("ipcch must be an object exactly when an IPCCH operation is selected (else null)")
    if (data["fewsnet"] is None) == fews_selected:
        raise DeliveryRequestV2Error("fewsnet must be an object exactly when a FEWS NET operation is selected (else null)")
    if data["publication"] not in PUBLICATIONS:
        raise DeliveryRequestV2Error(f"publication must be one of {PUBLICATIONS}")
    _runtime(data["runtime"])
    _text(data["operator"], "operator")
    _timestamp(data["prepared_at"], "prepared_at")

    # --- 2. mode rules
    if mode == "smoke" and fews_selected:
        raise DeliveryRequestV2Error("a smoke request may select IPCCH operations only (R38)")
    namespace = smoke_namespace if mode == "smoke" else production_namespace
    if smoke_namespace == production_namespace:
        raise DeliveryRequestV2Error("the smoke namespace must differ from the production namespace")
    _release(data["release"], namespace)

    # --- 3. operation conflicts and per-system blocks
    ipcch = _ipcch(data["ipcch"], ops) if ipcch_selected else None
    fewsnet = _fewsnet(data["fewsnet"], ops) if fews_selected else None

    # --- 4. derived dates and month rules (R23/R39 apply to the IPCCH operations only; FEWS NET month handling is
    # unchanged: its origin is the named prepared snapshot's (inference-only) or, as in the legacy CLI, the run month)
    derived = derived_months(month) if ipcch_selected else {"execution_month": month}
    if fews_selected:
        derived["fewsnet_origin_month"] = (fewsnet["prepared_snapshot"]["origin_month"] if "prepared_snapshot" in fewsnet
                                           else month)
    if mode == "real" and ipcch_selected:
        now = now_utc.astimezone(timezone.utc) if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc)
        if month > f"{now.year:04d}-{now.month:02d}":
            raise DeliveryRequestV2Error(f"execution_month {month} is later than the current UTC month (R39)")
        if (ops["ipcch_inference"] and data["publication"] == "current" and current_month is not None
                and month < _month(current_month, "current IPCCH execution month")):
            raise DeliveryRequestV2Error(
                f"execution_month {month} is earlier than the current IPCCH release month {current_month} (R39); "
                "an earlier month may only be published as a candidate")

    validated = dict(data)
    validated["ipcch"], validated["fewsnet"] = ipcch, fewsnet
    validated["derived"] = derived
    validated["request"] = normalize_gcs_ref(request_uri, generation=request_generation)
    validated["validation_level"] = "structural"
    return validated


def derived_months(execution_month: str) -> dict[str, Any]:
    """O = M - 2; public targets M, M+6, M+12 for model horizons H2/H8/H14 (R23)."""
    m = _ord(execution_month)
    return {"execution_month": execution_month, "feature_origin": _label(m + FEATURE_ORIGIN_OFFSET),
            "horizons": [{"model_horizon_months": h, "public_lead_months": PUBLIC_LEADS[h],
                          "target_month": _label(m + PUBLIC_LEADS[h])} for h in MODEL_HORIZONS]}


def _ipcch(value: Any, ops: Mapping[str, bool]) -> dict[str, Any]:
    gen, inf = ops["ipcch_generation"], ops["ipcch_inference"]
    allowed = ("model_combination", "feature_batch", "country_reference", *IPCCH_REFRESH_INPUTS)
    if not isinstance(value, Mapping) or set(value) - set(allowed) or "model_combination" not in value:
        raise DeliveryRequestV2Error(f"ipcch must hold model_combination and only {list(allowed)}")
    # The versioned combination envelope is authoritative (it binds the package, feature order, handoff bundle and
    # acceptance status); the runner verifies these pinned bytes against the installed envelope and package.
    out = {"model_combination": _object_with_ref(value["model_combination"], "combination_id", "envelope",
                                                 "ipcch.model_combination")}
    if inf and not gen:
        if "feature_batch" not in value:
            raise DeliveryRequestV2Error("IPCCH inference-only must name an existing feature batch (R19)")
        out["feature_batch"] = _object_with_ref(value["feature_batch"], "batch_id", "manifest", "ipcch.feature_batch")
        refreshing = [k for k in IPCCH_REFRESH_INPUTS if k in value and _is_refresh(value[k], k)]
        if refreshing:
            raise DeliveryRequestV2Error(f"IPCCH inference-only cannot refresh inputs {refreshing}; refresh requires "
                                         "IPCCH feature generation (R19/FCC1)")
    elif "feature_batch" in value:
        raise DeliveryRequestV2Error("feature_batch is only for IPCCH inference-only; generation + inference consumes "
                                     "this run's batch and never an implicit or named older one (R5/R19)")
    # The IPCCH country reference (existing delivery country-reference/report fields only) is an inference input:
    # required whenever IPCCH inference is selected, absent for generation-only (Supervisor ruling 2026-10-30).
    if inf:
        if "country_reference" not in value:
            raise DeliveryRequestV2Error("IPCCH inference needs ipcch.country_reference (pinned country reference)")
        out["country_reference"] = _ref(value["country_reference"], "ipcch.country_reference")
    elif "country_reference" in value:
        raise DeliveryRequestV2Error("ipcch.country_reference is an inference input; generation-only omits it")
    if gen:
        missing = [k for k in IPCCH_REFRESH_INPUTS if k not in value]
        if missing:
            raise DeliveryRequestV2Error(f"IPCCH generation declares keep or refresh for every input; missing {missing}")
    for key in IPCCH_REFRESH_INPUTS:
        if key in value:
            out[key] = {"acled": _acled, "research_inputs": _research_inputs, "history_snapshot": _history_snapshot,
                        "wfp": _ipcch_wfp}[key](value[key])
    return out


def _fewsnet(value: Any, ops: Mapping[str, bool]) -> dict[str, Any]:
    gen, inf = ops["fewsnet_generation"], ops["fewsnet_inference"]
    fields = (("acled", "wfp") if gen else ()) + (("prepared_snapshot",) if inf and not gen else ()) + (
        ("delivery",) if inf else ())
    _exact_keys(value, fields, "fewsnet")
    out: dict[str, Any] = {}
    if gen:
        for source in ("acled", "wfp"):
            _source_choice(value[source], f"fewsnet.{source}")
            out[source] = dict(value[source])
    if inf and not gen:
        prepared = value["prepared_snapshot"]
        _exact_keys(prepared, ("prepare_id", "origin_month", "manifest"), "fewsnet.prepared_snapshot")
        _text(prepared["prepare_id"], "fewsnet.prepared_snapshot.prepare_id")
        _month(prepared["origin_month"], "fewsnet.prepared_snapshot.origin_month")
        _ref(prepared["manifest"], "fewsnet.prepared_snapshot.manifest")
        out["prepared_snapshot"] = dict(prepared)
    if inf:
        # The existing FEWS NET delivery inputs - the v1 models/assets/diagnostics/contracts rules restricted to FEWS NET
        # (shared validators, systems=("fewsnet",)) - are validated here, in full, before anything executes (R17).
        out["delivery"] = _fews_delivery(value["delivery"])
    return out


FEWS_DELIVERY_FIELDS = ("models", "assets", "diagnostics", "contracts")


def _fews_delivery(value: Any) -> dict[str, Any]:
    from cloud.orchestrator import delivery_manifest as dm

    _exact_keys(value, FEWS_DELIVERY_FIELDS, "fewsnet.delivery")
    models = dm._models(value["models"], systems=("fewsnet",))
    dm._assets(value["assets"], systems=("fewsnet",))
    dm._diagnostics(value["diagnostics"], models, systems=("fewsnet",))
    dm._contracts(value["contracts"])
    return dict(value)


def _acled(value: Any) -> dict[str, Any]:
    if _choice(value, "ipcch.acled") == "keep":
        return {"action": "keep"}
    _exact_keys(value, ("action", "file", "start", "end", "regions"), "ipcch.acled")
    _ref(value["file"], "ipcch.acled.file")
    start, end = _day(value["start"], "ipcch.acled.start"), _day(value["end"], "ipcch.acled.end")
    # ACLED export weeks are Saturday-Friday, labelled by their Saturday start (R26/R55): the declared interval is
    # whole weeks, from a Saturday to a Friday.
    if start.weekday() != 5 or end.weekday() != 4 or end < start:
        raise DeliveryRequestV2Error("ipcch.acled interval must run from a Saturday start to a later Friday end")
    regions = value["regions"]
    if (not isinstance(regions, list) or not regions or len(set(regions)) != len(regions)
            or any(not isinstance(r, str) or not r.strip() for r in regions)):
        raise DeliveryRequestV2Error("ipcch.acled.regions must be a non-empty list of unique region names")
    return dict(value)


def _research_inputs(value: Any) -> dict[str, Any]:
    _exact_keys(value, RESEARCH_FAMILIES, "ipcch.research_inputs")
    out = {}
    for family in RESEARCH_FAMILIES:
        label = f"ipcch.research_inputs.{family}"
        entry = value[family]
        if _choice(entry, label) == "keep":
            out[family] = {"action": "keep"}
            continue
        _exact_keys(entry, ("action", "file", "start", "end"), label)
        _ref(entry["file"], f"{label}.file")
        if _month(entry["start"], f"{label}.start") > _month(entry["end"], f"{label}.end"):
            raise DeliveryRequestV2Error(f"{label} declared interval is reversed")
        out[family] = dict(entry)
    return out


def _history_snapshot(value: Any) -> dict[str, Any]:
    # A complete snapshot through its own preparation cutoff, replaced atomically (R62/FCC8): no interval fields.
    if _choice(value, "ipcch.history_snapshot") == "keep":
        return {"action": "keep"}
    _exact_keys(value, ("action", "file"), "ipcch.history_snapshot")
    _ref(value["file"], "ipcch.history_snapshot.file")
    return dict(value)


def _ipcch_wfp(value: Any) -> dict[str, Any]:
    # Supervisor contract correction (2026-10-30, research/cp3/wfp-price-provenance.md): the trained WFP_Price is the
    # research HDX local-currency staple YoY nearest-market (<100 km) series, not the WFP Trend country mean. A refresh
    # is therefore a research-prepared processed file (admin_code, month, value from build_wfp_hdx) over a declared
    # month interval (R59 semantics); the old raw_upload/converter shape is rejected for IPCCH (FEWS NET unchanged).
    if _choice(value, "ipcch.wfp") == "keep":
        return {"action": "keep"}
    if "raw_upload" in value or "converter_contract" in value:
        raise DeliveryRequestV2Error("ipcch.wfp refresh takes a research-prepared processed file "
                                     "{action, file, start, end}; the raw_upload/converter shape is FEWS NET only")
    _exact_keys(value, ("action", "file", "start", "end"), "ipcch.wfp")
    _ref(value["file"], "ipcch.wfp.file")
    if _month(value["start"], "ipcch.wfp.start") > _month(value["end"], "ipcch.wfp.end"):
        raise DeliveryRequestV2Error("ipcch.wfp declared interval is reversed")
    return dict(value)


def _choice(value: Any, label: str) -> str:
    if not isinstance(value, Mapping) or value.get("action") not in ("keep", "refresh"):
        raise DeliveryRequestV2Error(f"{label}.action must be keep or refresh")
    if value["action"] == "keep" and set(value) != {"action"}:
        raise DeliveryRequestV2Error(f"{label} keep carries no other field (it uses the last saved real history)")
    return value["action"]


def _is_refresh(value: Any, key: str) -> bool:
    if key == "research_inputs":
        return isinstance(value, Mapping) and any(isinstance(v, Mapping) and v.get("action") == "refresh"
                                                  for v in value.values())
    return isinstance(value, Mapping) and value.get("action") == "refresh"


def _object_with_ref(value: Any, id_field: str, ref_field: str, label: str) -> dict[str, Any]:
    _exact_keys(value, (id_field, ref_field), label)
    _text(value[id_field], f"{label}.{id_field}")
    _ref(value[ref_field], f"{label}.{ref_field}")
    return dict(value)


def iter_object_refs(request: Mapping[str, Any]) -> list[tuple[str, Mapping[str, str]]]:
    """Every pinned object reference of a structurally valid v2 request, with its field path."""
    refs: list[tuple[str, Mapping[str, str]]] = [("runtime.environment_manifest", request["runtime"]["environment_manifest"])]
    ipcch = request.get("ipcch")
    if ipcch:
        refs.append(("ipcch.model_combination.envelope", ipcch["model_combination"]["envelope"]))
        if "feature_batch" in ipcch:
            refs.append(("ipcch.feature_batch.manifest", ipcch["feature_batch"]["manifest"]))
        if "country_reference" in ipcch:
            refs.append(("ipcch.country_reference", ipcch["country_reference"]))
        for key in ("acled", "history_snapshot"):
            if ipcch.get(key, {}).get("action") == "refresh":
                refs.append((f"ipcch.{key}.file", ipcch[key]["file"]))
        for family, entry in (ipcch.get("research_inputs") or {}).items():
            if entry["action"] == "refresh":
                refs.append((f"ipcch.research_inputs.{family}.file", entry["file"]))
        if ipcch.get("wfp", {}).get("action") == "refresh":
            refs.append(("ipcch.wfp.file", ipcch["wfp"]["file"]))
    fews = request.get("fewsnet")
    if fews:
        if "prepared_snapshot" in fews:
            refs.append(("fewsnet.prepared_snapshot.manifest", fews["prepared_snapshot"]["manifest"]))
        for source in ("acled", "wfp"):
            if source in fews:
                field = "retained_snapshot" if fews[source]["action"] == "keep" else "raw_upload"
                refs.append((f"fewsnet.{source}.{field}", fews[source][field]))
        delivery = fews.get("delivery")
        if delivery:                                    # every nested FEWS delivery reference (R17)
            for model in delivery["models"]:
                label = f"fewsnet.delivery.models[{model['horizon_months']}m]"
                refs.append((f"{label}.package_manifest", model["package_manifest"]))
                refs.append((f"{label}.acceptance_report", model["acceptance_report"]))
            for kind, ref in delivery["assets"]["fewsnet"].items():
                refs.append((f"fewsnet.delivery.assets.{kind}", ref))
            for entry in delivery["diagnostics"]:
                label = f"fewsnet.delivery.diagnostics[{entry['horizon_months']}m/{entry['family']}]"
                if entry["status"] in ("available", "frozen_output"):
                    refs.append((f"{label}.evidence", entry["evidence"]))
                if entry["status"] == "frozen_output":
                    for part in ("source_availability", "source_evidence", "source_declarations"):
                        refs.append((f"{label}.{part}", entry[part]))
    return refs


# References a smoke and a real request may share (the explicit allowlist): the model-combination envelope (the only
# shared input, R48) and the runtime environment manifest. Everything else must lie in the request mode's namespace.
SHARED_REF_FIELDS = ("ipcch.model_combination.envelope", "runtime.environment_manifest")


def admit_namespaces(request: Mapping[str, Any], trusted_prefixes: Mapping[str, Any],
                     batch_roots: Mapping[str, str]) -> None:
    """R48: decided lexically on the URIs, BEFORE any reference is resolved or read. Every non-shared reference must lie
    under one of the request mode's trusted prefixes; a named feature batch manifest must lie under that mode's batch
    root ``<root>/feature_batches/``. A misrouted (e.g. real) reference in a smoke request is never touched."""
    mode = request["mode"]
    prefixes = tuple(p if p.endswith("/") else p + "/" for p in trusted_prefixes.get(mode, ()))
    if not prefixes or mode not in batch_roots:
        raise DeliveryRequestV2Error(f"no trusted {mode} namespace configured; nothing is resolved (R48)")
    batches = batch_roots[mode].rstrip("/") + "/feature_batches/"
    for field, ref in iter_object_refs(request):
        uri = ref["uri"]
        if "/../" in uri or uri.endswith("/.."):
            raise DeliveryRequestV2Error(f"{field} {uri} is not a canonical object URI (R48)")
        if field == "ipcch.feature_batch.manifest":
            if not uri.startswith(batches):
                raise DeliveryRequestV2Error(f"{field} {uri} is outside the {mode} batch namespace {batches}; "
                                             "not resolved (R48)")
            continue
        if field in SHARED_REF_FIELDS:
            continue
        if not uri.startswith(prefixes):
            raise DeliveryRequestV2Error(f"{field} {uri} is outside the trusted {mode} namespace; not resolved (R48)")


def admit(data: Mapping[str, Any], *, request_uri: str, request_generation: str, now_utc: datetime,
          production_namespace: str, smoke_namespace: str, current_ipcch_execution_month: str | None,
          resolve: Callable[[str, str], str | None], trusted_prefixes: Mapping[str, Any],
          batch_roots: Mapping[str, str]) -> dict[str, Any]:
    """Integrated preflight: the whole request (incl. the complete FEWS NET delivery) is validated, every reference is
    admitted to the request mode's trusted namespace LEXICALLY (R48), and only then is EVERY pinned reference (IPCCH,
    FEWS NET, nested delivery models/assets/diagnostics, runtime) verified at its generation and sha256 - all before
    any lock, collection, retained-store mutation or inference. An invalid request executes nothing (R17)."""
    request = validate_request_v2(data, request_uri=request_uri, request_generation=request_generation, now_utc=now_utc,
                                  production_namespace=production_namespace, smoke_namespace=smoke_namespace,
                                  current_ipcch_execution_month=current_ipcch_execution_month)
    admit_namespaces(request, trusted_prefixes, batch_roots)
    request["verified_references"] = verify_reference_identities(request, resolve)
    request["validation_level"] = "admitted"
    return request


def verify_reference_identities(request: Mapping[str, Any], resolve: Callable[[str, str], str | None]) -> list[dict[str, str]]:
    """Each reference's actual SHA-256 at its pinned generation (``resolve(uri, generation)``; ``None`` = absent)."""
    if request.get("validation_level") != "structural" or not is_v2(request):
        raise ReferenceIdentityError("a v2 request must pass structural validation first")
    verified = []
    for field, ref in iter_object_refs(request):
        actual = resolve(ref["uri"], ref["generation"])
        if actual is None:
            raise ReferenceIdentityError(f"{field} object/generation not found: {ref['uri']}#{ref['generation']}")
        if actual != ref["sha256"]:
            raise ReferenceIdentityError(f"{field} sha256 mismatch for {ref['uri']}#{ref['generation']}")
        verified.append({"field": field, **ref})
    return verified


def _day(value: Any, field: str) -> date:
    if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
        raise DeliveryRequestV2Error(f"{field} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DeliveryRequestV2Error(f"{field} must be a valid date") from exc


def _ord(month: str) -> int:
    y, m = (int(x) for x in month.split("-"))
    return y * 12 + m - 1


def _label(ordinal: int) -> str:
    return f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}"
