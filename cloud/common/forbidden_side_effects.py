from __future__ import annotations

from dataclasses import dataclass


_FORBIDDEN_FAMILIES = (
    ("map", ("/maps/", "prediction_map", "_map.")),
    ("prediction_sheet", ("/prediction_sheets/", "prediction_sheet", ".xlsx")),
    ("delivery", ("/delivery/", "full_delivery")),
    ("training", ("/training/", "train_", "model.pkl")),
    ("non_evi_remote_sensing", ("FLDAS", "GOSIF", "VIIRS")),
)


@dataclass(frozen=True)
class ForbiddenSideEffect:
    uri: str
    family: str
    reason: str


def scan_forbidden_side_effects(
    *,
    observed_uris: list[str],
    allowed_prefixes: list[str],
    ignored_prefixes: list[str] | None = None,
) -> list[ForbiddenSideEffect]:
    ignored_prefixes = ignored_prefixes or []
    findings: list[ForbiddenSideEffect] = []
    for uri in observed_uris:
        if any(uri.startswith(prefix) for prefix in ignored_prefixes):
            continue
        if not any(uri.startswith(prefix) for prefix in allowed_prefixes):
            findings.append(
                ForbiddenSideEffect(
                    uri=uri,
                    family="outside_allowed_prefix",
                    reason="outside allowed output roots",
                )
            )
            continue
        family = _match_forbidden_family(uri)
        if family is not None:
            findings.append(
                ForbiddenSideEffect(
                    uri=uri, family=family, reason="forbidden output family"
                )
            )
    return findings


def _match_forbidden_family(uri: str) -> str | None:
    for family, tokens in _FORBIDDEN_FAMILIES:
        if any(token in uri for token in tokens):
            return family
    return None
