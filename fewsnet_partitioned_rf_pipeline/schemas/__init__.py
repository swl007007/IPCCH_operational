import json
import re
from datetime import datetime
from importlib.resources import files

from jsonschema import Draft202012Validator, FormatChecker


DATE_TIME_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt]"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?"
    r"(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$"
)
FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time", raises=ValueError)
def _is_rfc3339_date_time(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if DATE_TIME_PATTERN.fullmatch(value) is None:
        return False
    normalized = value[:10] + "T" + value[11:]
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    datetime.fromisoformat(normalized)
    return True


def load_schema(name: str) -> dict:
    resource = files(__package__).joinpath(f"{name}.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_payload(name: str, payload: dict) -> None:
    validator = Draft202012Validator(
        load_schema(name),
        format_checker=FORMAT_CHECKER,
    )
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path) or "<root>"
        raise ValueError(f"{name} contract failed at {path}: {first.message}")


def validate_deployment(payload: dict) -> None:
    validate_payload("deployment", payload)
    digest = payload["container_image_digest"]
    if not payload["container_image_uri"].endswith(f"@{digest}"):
        raise ValueError(
            "container_image_digest must equal the digest suffix of container_image_uri"
        )
