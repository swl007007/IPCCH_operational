from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from cloud.common.object_store import GenerationConflict, ObjectStore
from cloud.common.reports import build_run_summary


class DuplicateRunError(RuntimeError):
    """Raised when a run prefix has already been acquired."""


@dataclass(frozen=True)
class RunState:
    feature_month: str
    run_id: str
    run_prefix_uri: str
    input_manifest_uri: str
    deployment: dict[str, Any]
    container_image_digest: str
    waivers: list[dict[str, Any]] | None = None


class RunStateManager:
    def __init__(
        self,
        store: ObjectStore,
        *,
        object_store_root_uri: str,
        run_root_uri: str | None = None,
    ):
        self.store = store
        self.object_store_root_uri = object_store_root_uri.rstrip("/")
        self.run_root_uri = run_root_uri

    def acquire_run(
        self,
        *,
        feature_month: str,
        run_id: str,
        input_manifest_uri: str,
        deployment: dict[str, Any],
        container_image_digest: str,
        waivers: list[dict[str, Any]] | None = None,
    ) -> RunState:
        state = RunState(
            feature_month=feature_month,
            run_id=run_id,
            run_prefix_uri=self._run_prefix_uri(deployment, run_id=run_id),
            input_manifest_uri=input_manifest_uri,
            deployment=deployment,
            container_image_digest=container_image_digest,
            waivers=waivers or [],
        )
        try:
            self.store.write_text(
                state.run_prefix_uri + "_RUN_PREFIX_ACQUIRED",
                f"{run_id}\n",
                if_generation_match=0,
            )
        except GenerationConflict as exc:
            raise DuplicateRunError(f"run_id already exists: {run_id}") from exc

        self._write_summary(state, status="running")
        return state

    def _run_prefix_uri(self, deployment: dict[str, Any], *, run_id: str) -> str:
        uri = (
            self.run_root_uri
            or deployment.get("run_root_uri")
            or f"{self.object_store_root_uri}/runs/{run_id}/"
        )
        return uri if uri.endswith("/") else uri + "/"

    def write_terminal_summary(
        self,
        state: RunState,
        *,
        status: str,
        hard_gates: list[dict[str, Any]] | None = None,
        **extra: Any,
    ) -> None:
        self._write_summary(state, status=status, hard_gates=hard_gates or [], **extra)

    def _write_summary(self, state: RunState, *, status: str, **extra: Any) -> None:
        artifact_paths = dict(extra.pop("artifact_paths", {}) or {})
        artifact_paths["run_prefix_uri"] = state.run_prefix_uri
        extra.setdefault("waivers", state.waivers or [])
        summary = build_run_summary(
            feature_month=state.feature_month,
            run_id=state.run_id,
            status=status,
            input_manifest_uri=state.input_manifest_uri,
            deployment=state.deployment,
            container_image_digest=state.container_image_digest,
            artifact_paths=artifact_paths,
            **extra,
        )
        self.store.write_text(
            state.run_prefix_uri + "run_summary.json",
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
        )
