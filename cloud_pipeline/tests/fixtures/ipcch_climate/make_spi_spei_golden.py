"""Regenerate ipcch_spi_spei_golden.npz from the ORIGINAL shared-folder functions (run once; output committed).
  python tests/fixtures/ipcch_climate/make_spi_spei_golden.py <path to IPCCH_shared_folder/monthly/spi_monthly.py>"""
import ast, hashlib, os, sys
import numpy as np, pandas as pd
from scipy import special

FUNCS = ("rolling_three_month_sum", "normal_from_probability", "compute_spi03_monthly", "compute_spei03_monthly")
SHA = "0e29ed359915840825d5d35a0ecf962639d2218c27744af012e367a8b7d854c5"


def original(path, months):
    src = open(path, "rb").read()
    assert hashlib.sha256(src).hexdigest() == SHA, "shared spi_monthly.py differs from the ported version"
    tree = ast.parse(src.decode())
    mod = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCS], type_ignores=[])
    ns = {"np": np, "special": special, "ALL_MONTHS": months, "BASELINE_START_YEAR": 1991, "BASELINE_END_YEAR": 2020}
    exec(compile(mod, path, "exec"), ns)
    return ns


def inputs(seed=20261030, admins=12):
    months = pd.date_range("1990-11-01", "2026-08-01", freq="MS")
    rng = np.random.default_rng(seed)
    shape = rng.uniform(0.5, 3.0, size=(admins, 1))
    prcp = rng.gamma(shape, 40.0, size=(admins, len(months)))
    prcp[rng.random(prcp.shape) < 0.15] = 0.0                       # dry months (zero-corrected gamma)
    prcp[2, :] = 0.0; prcp[2, [50, 200, 300]] = 5.0                 # dry admin: < 10 positive baseline totals
    gaps = rng.random(prcp.shape) < 0.01
    prcp[4:6][gaps[4:6]] = np.nan                                    # scattered missing months on two admins
    prcp[3, 100] = np.nan                                            # breaks one baseline year -> strict baseline
    et0 = rng.uniform(60.0, 180.0, size=prcp.shape)
    et0[5, rng.random(et0.shape[1]) < 0.02] = np.nan
    return months, prcp, et0


if __name__ == "__main__":
    months, prcp, et0 = inputs()
    ns = original(sys.argv[1], months)
    spi = ns["compute_spi03_monthly"](prcp)
    spei = ns["compute_spei03_monthly"](prcp, et0)
    np.savez_compressed(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipcch_spi_spei_golden.npz"),
                        prcp=prcp, et0=et0, spi=spi, spei=spei)
    print("spi finite", int(np.isfinite(spi).sum()), "spei finite", int(np.isfinite(spei).sum()), "shape", spi.shape)
