"""Task 10-29: the operational SPI-3/SPEI-3 port equals the shared-folder spi_monthly.py functions bit for bit."""

import importlib.util
import os

import numpy as np
import pandas as pd
import pytest

from cloud.ipcch import spi_spei as ss

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "..", "fixtures", "ipcch_climate")
SHARED = os.environ.get("IPCCH_SHARED_SPI", "/mnt/c/users/swl00/ifpri dropbox/weilun shi/IPCCH_shared_folder/monthly/spi_monthly.py")
MONTHS = pd.date_range("1990-11-01", "2026-08-01", freq="MS")


def _maker():
    spec = importlib.util.spec_from_file_location("make_golden", os.path.join(FIX, "make_spi_spei_golden.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_port_equals_golden_from_original_functions():
    g = np.load(os.path.join(FIX, "ipcch_spi_spei_golden.npz"))
    spi = ss.compute_spi03_monthly(g["prcp"], MONTHS)
    spei = ss.compute_spei03_monthly(g["prcp"], g["et0"], MONTHS)
    np.testing.assert_array_equal(spi, g["spi"])                  # NaN positions and values identical
    np.testing.assert_array_equal(spei, g["spei"])
    assert np.isfinite(spi).sum() > 4000 and np.isfinite(spei).sum() > 3000
    assert np.isnan(spi[2]).all()                                  # < 10 positive baseline totals: no parameters


@pytest.mark.skipif(not os.path.exists(SHARED), reason="shared-folder script not mounted; golden fixture still checked")
def test_port_equals_original_live_differential():
    mk = _maker()
    ns = mk.original(SHARED, MONTHS)
    for seed in (1, 2, 3):
        months, prcp, et0 = mk.inputs(seed=seed, admins=8)
        np.testing.assert_array_equal(ss.compute_spi03_monthly(prcp, months), ns["compute_spi03_monthly"](prcp))
        np.testing.assert_array_equal(ss.compute_spei03_monthly(prcp, et0, months), ns["compute_spei03_monthly"](prcp, et0))


def test_strict_baseline_and_axis():
    with pytest.raises(ValueError, match="complete 1991-2020 baseline"):
        ss.compute_spi03_monthly(np.ones((1, 24)), pd.date_range("2000-01-01", periods=24, freq="MS"))
    with pytest.raises(ValueError, match="contiguous"):
        ss.compute_spi03_monthly(np.ones((1, 2)), pd.DatetimeIndex(["2000-01-01", "2000-03-01"]))
    assert ss.month_axis("1990-11", "2026-08").equals(MONTHS)


def test_et0_patch_fills_missing_only():
    et0 = np.array([[1.0, np.nan, 3.0]])
    out, filled = ss.apply_et0_patch(et0, np.array([[9.0, 2.0, np.nan]]))
    assert out.tolist() == [[1.0, 2.0, 3.0]] and filled == 1
