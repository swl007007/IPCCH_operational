"""FEWS NET member of a v2 release (task 10-29; R60 and the Supervisor D1-D3 rulings, design.md "R60 FEWS adapter").

The member is written by the EXISTING ``deliver(system="fewsnet")`` (through the injected ``score`` - in production the
per-system subprocess ``delivery_job run_system``), so FEWS NET scientific outputs are unchanged; the exact scored
packages are copied to ``fewsnet/model_package/{h}m/`` (the inherited-package prefix) and the existing FEWS NET-scoped
delivery checks apply (``delivery_bundle.validate_member``; re-run by the publication verifier). It is published by
``release_v2.publish_member_run(system="fewsnet")``: the IPCCH member is inherited from the snapshot bound to the
expected pointer generation and activation is carried forward. Shared by the v2 FEWS adapter and the post-activation
legacy v1 FEWS NET-only route.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable, Mapping

FEWS_CONTRACT = "fewsnet-legacy-scoring"
IPCCH_LEGACY_CONTRACT = "ipcch-legacy-scoring"     # = publication.LEGACY_IPCCH_MEMBER (pre-activation v1 IPCCH)
CONTRACTS = {"fewsnet": FEWS_CONTRACT, "ipcch": IPCCH_LEGACY_CONTRACT}
LEADS = (0, 6, 12)


class FewsMemberError(RuntimeError):
    """The legacy-format member is incomplete or does not verify; nothing is published."""


def check_member(out: Path, origin: str, package_inventory: Mapping[str, str], system: str = "fewsnet") -> dict[str, Any]:
    """The existing system-scoped delivery checks (delivery_bundle.validate_member): frozen headers, native keys,
    roster, predictions, country tables, diagnostics/availability, frozen scoring inputs and the exact package
    identities."""
    from cloud.orchestrator.delivery_bundle import validate_member

    try:
        return validate_member(Path(out), system, origin=origin, package_inventory=package_inventory)
    except ValueError as exc:
        raise FewsMemberError(str(exc)) from None


def write_member(out: Path, *, score: Callable[[Path, str, Path], None], spec_path: Path, origin: str,
                 packages: Any, mode: str, source: Mapping[str, Any] | None = None,
                 system: str = "fewsnet") -> dict[str, Any]:
    """Score ``system`` into ``out`` with the existing deliver path, install its exact packages (FEWS NET: the 0/6/12
    package directories ``{h: dir}``; legacy IPCCH: the one package directory), check, and return the member record
    (own origin, mode and package identity)."""
    from cloud.orchestrator.delivery_bundle import _directory_inventory

    out = Path(out)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    if system == "fewsnet":
        if not isinstance(packages, Mapping) or sorted(int(h) for h in packages) != list(LEADS):
            raise FewsMemberError(f"FEWS NET member needs exactly the {list(LEADS)} packages, got {sorted(packages or {})}")
    elif system != "ipcch" or not packages:
        raise FewsMemberError(f"{system} member needs its package directory")
    score(Path(spec_path), system, out)
    package = {}
    if system == "fewsnet":
        for h in sorted(packages, key=int):
            shutil.copytree(packages[h], out / f"fewsnet/model_package/{int(h)}m", ignore=ignore)
            package.update({f"{int(h)}m/{p}": d for p, d in _directory_inventory(Path(packages[h])).items()})
    else:
        shutil.copytree(packages, out / "ipcch/model_package", ignore=ignore)
        package = _directory_inventory(Path(packages))
    check_member(out, origin, package, system)
    return {"contract": CONTRACTS[system], "origin_month": origin, "mode": mode, "model_horizons": list(LEADS),
            "model_package": package, **({"source": dict(source)} if source else {})}
