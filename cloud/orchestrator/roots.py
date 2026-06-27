from __future__ import annotations


def resolve_deployment_roots(
    deployment: dict, *, run_id: str, feature_month: str
) -> dict[str, str]:
    object_root = deployment["object_store_root_uri"].rstrip("/")
    yyyymm = feature_month.replace("-", "")
    run_root = _ensure_trailing_slash(
        deployment.get("run_root_uri") or f"{object_root}/runs/{run_id}/"
    )
    return {
        "run_root_uri": run_root,
        "staging_root_uri": _ensure_trailing_slash(
            deployment.get("staging_root_uri") or f"{object_root}/staging/{run_id}/"
        ),
        "release_root_uri": _ensure_trailing_slash(
            deployment.get("release_root_uri") or f"{object_root}/released/{yyyymm}/"
        ),
        "gee_export_root_uri": _ensure_trailing_slash(
            deployment.get("gee_export_root_uri") or run_root + "gee_exports/"
        ),
        "evi_output_root_uri": _ensure_trailing_slash(
            deployment.get("evi_output_root_uri") or run_root + "evi/"
        ),
        "logs_root_uri": _ensure_trailing_slash(
            deployment.get("logs_root_uri") or run_root + "logs/"
        ),
        "assembly_root_uri": run_root + "assembly/",
        "batch_root_uri": run_root + "batch/",
        "qa_root_uri": run_root + "qa/",
        "inference_root_uri": run_root + "inference/",
    }


def _ensure_trailing_slash(uri: str) -> str:
    return uri if uri.endswith("/") else uri + "/"
