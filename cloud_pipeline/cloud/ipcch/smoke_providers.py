"""Runtime smoke providers for the v2 entrypoint (task 10-30; R48): the deployment's ``providers.smoke`` factory.

Self-contained (no test-suite or pytest import, installed in the image): smoke generation never builds the Earth
Engine transport, the table producer or the GCS/HTTP acquirers, and never reads a real input. Climate values are
deterministic fixture values published for the smoke store's roster (and each season window's own areas); GPP and
VIIRS report no published product. Together with the installed smoke fixture bundle (``smoke-fixture/bundle``,
manifest ``fixture: true``) this exercises the complete route - admission, locks, generation, assembly, inference,
smoke publication - with fixture data only.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from cloud.ipcch import climate as cl
from cloud.ipcch import climate_run


def climate_providers(codes) -> climate_run.ClimateProviders:
    codes = [str(c) for c in codes]

    def monthly(base):
        return lambda source, month: cl.SourceOutcome(source, "published", pd.DataFrame(
            {"admin_code": codes, "value": np.linspace(0.1, 0.4, len(codes))}))

    def seasonal(base):
        return lambda source, year, season, win: cl.SourceOutcome(source, "published", pd.DataFrame(
            {"admin_code": list(win["admin_code"].astype(str)), "value": 0.5}))
    return climate_run.ClimateProviders(monthly, seasonal)


class NoGpp:
    """GPP acquirer: no provider product is ever found (``_head`` 404), so nothing is acquired."""

    def _head(self, url):
        return 404


class NoNightlight:
    """VIIRS acquirer: no published month, no export."""

    def published_months(self, family, *, start_month, end_month):
        return {}

    def start_exports(self, family, months, *, prepare_id):
        pass


def entrypoint_providers(*, cfg, store, client, run_id, roster, **_) -> dict[str, Any]:
    """``providers.smoke`` factory (same signature as ``entrypoint_v2.real_providers``; the deadline, store root and
    execution month are accepted and unused - nothing here performs bounded cloud work)."""
    return {"climate_providers": lambda windows, origin: climate_providers(roster), "gpp_acquirer": NoGpp(),
            "nightlight_acquirer": NoNightlight()}
