"""FEWS NET member of a v2 release (task 10-29; R60 and the Supervisor D1-D3 rulings, design.md "R60 FEWS adapter").

The member is written by the EXISTING ``deliver(system="fewsnet")`` (through the injected ``score`` - in production the
per-system subprocess ``delivery_job run_system``), so FEWS NET scientific outputs are unchanged; the exact scored
packages are copied to ``fewsnet/model_package/{h}m/`` (the inherited-package prefix) and the existing per-system
structural checks apply (every scope table for leads 0/6/12, its own origin and targets). It is published by
``release_v2.publish_member_run(system="fewsnet")``: the IPCCH member is inherited from the snapshot bound to the
expected pointer generation and activation is carried forward. Shared by the v2 FEWS adapter and the post-activation
legacy v1 FEWS NET-only route.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

FEWS_CONTRACT = "fewsnet-legacy-scoring"
LEADS = (0, 6, 12)


class FewsMemberError(RuntimeError):
    """The FEWS NET member is incomplete or not its own origin's targets; nothing is published."""


def _target(origin: str, lead: int) -> str:
    y, m = (int(x) for x in origin.split("-"))
    o = y * 12 + m - 1 + lead
    return f"{o // 12:04d}-{o % 12 + 1:02d}"


def check_member(out: Path, origin: str) -> None:
    from cloud.orchestrator.delivery_bundle import SCOPE_TABLES

    out = Path(out)
    missing = [f"scopes/{h}m/fewsnet/{t}.csv" for h in LEADS for t in SCOPE_TABLES["fewsnet"]
               if not (out / f"scopes/{h}m/fewsnet/{t}.csv").is_file()]
    missing += [p for p in ("fewsnet/polygons.geojson", "fewsnet/country_population_reference.csv",
                            "reports/fewsnet_diagnostic_availability.csv", "reports/fewsnet_feature_fill_audit.csv")
                if not (out / p).is_file()]
    if missing:
        raise FewsMemberError(f"FEWS NET member lacks {missing[:4]}")
    for lead in LEADS:
        f = pd.read_csv(out / f"scopes/{lead}m/fewsnet/polygon_predictions.csv", dtype=str, keep_default_na=False)
        if set(f["feature_month"]) != {origin} or set(f["target_month"]) != {_target(origin, lead)}:
            raise FewsMemberError(f"FEWS NET lead {lead} is not {origin}->{_target(origin, lead)}")


def write_member(out: Path, *, score: Callable[[Path, str, Path], None], spec_path: Path, origin: str,
                 packages: Mapping[Any, str], mode: str, source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Score FEWS NET into ``out`` with the existing deliver path, install its exact packages, check, and return the
    member record (own origin, mode and package identity)."""
    from cloud.orchestrator.delivery_bundle import _directory_inventory

    out = Path(out)
    score(Path(spec_path), "fewsnet", out)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    package = {}
    for h in sorted(packages, key=int):
        target = out / f"fewsnet/model_package/{int(h)}m"
        shutil.copytree(packages[h], target, ignore=ignore)
        package.update({f"{int(h)}m/{p}": d for p, d in _directory_inventory(Path(packages[h])).items()})
    check_member(out, origin)
    return {"contract": FEWS_CONTRACT, "origin_month": origin, "mode": mode, "model_horizons": list(LEADS),
            "model_package": package, **({"source": dict(source)} if source else {})}
