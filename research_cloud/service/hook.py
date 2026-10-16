"""Per-interpreter service hook, imported from ``ipcch_service_hook.pth`` when ``IPCCH_SERVICE_HOOK=1``.

``mlflow server`` runs the app in a uvicorn subprocess, so the guard and assistant patch must load in every
interpreter of the service rather than only in the launcher. A failure here ends the interpreter (exit 78): a
worker without the egress guard must not serve. ``start.py`` checks in a fresh interpreter that this module
loaded with the expected mode before starting the server, because ``site`` ignores a ``.pth`` line that fails.
"""
import os
import sys

STATE = {}


def _run():
    from research_cloud.service import guard

    mode = os.environ.get("IPCCH_ASSISTANT_MODE", "deny")
    if mode not in ("armed", "deny"):
        raise RuntimeError(f"IPCCH_ASSISTANT_MODE={mode!r}")
    if os.environ.get("IPCCH_REHEARSAL_FAKE_VERTEX") == "1":   # local rehearsal only; refuses under Cloud Run
        from research_cloud.service import rehearsal_upstream

        rehearsal_upstream.install()
    installed = guard.install(os.environ["IPCCH_ASSISTANT_GUARD_CONFIG"] if mode == "armed" else None)
    markers = {}
    if installed == "armed":
        from research_cloud.service import assistant_patch

        assistant_patch.apply(os.environ["IPCCH_ASSISTANT_SELF_URL"].rstrip("/"))
        markers = assistant_patch.patch_markers()
        if not all(markers.values()):
            raise RuntimeError(f"assistant patch incomplete: {markers}")
    STATE.update(mode=installed, markers=markers)


try:
    _run()
except BaseException as e:   # noqa: BLE001 - any failure must stop this interpreter
    sys.stderr.write(f"ipcch service hook failed; refusing to run: {type(e).__name__}: {e}\n")
    sys.stderr.flush()
    os._exit(78)
