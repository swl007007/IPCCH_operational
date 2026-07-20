import json
from importlib.resources import files

from jsonschema import Draft202012Validator


def load_schema(name: str) -> dict:
    resource = files(__package__).joinpath(f"{name}.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_payload(name: str, payload: dict) -> None:
    errors = sorted(
        Draft202012Validator(load_schema(name)).iter_errors(payload),
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
