"""Regenerate ipcch_seasonal_golden.npz/.csv from the ORIGINAL seasonal/spi&spei.py (run once; outputs committed):
the original compute_spi03/compute_spei03 and aggregate_gs, and the original module-level exact season plan loop, on
synthetic admins with the original month axes (1990-01..2021-12, index 2014-01..2021-12, output years 2015-2021).
  python tests/fixtures/ipcch_climate/make_seasonal_golden.py "<IPCCH_shared_folder>/seasonal/spi&spei.py" """
import ast, calendar as pycalendar, hashlib, json, os, sys
import numpy as np, pandas as pd
from scipy import special

SHA = "fbc559792896f5dc251aceb1ad83926c0cbdf2107c713aeb14701359dea690a7"
FUNCS = ("rolling_three_month_sum", "normal_from_probability", "compute_spi03", "fit_glo_ubpwm", "glo_probability_strict",
         "compute_spei03", "truthy", "int_or_none", "exact_date", "aggregate_gs")
HERE = os.path.dirname(os.path.abspath(__file__))
ALL_MONTHS = pd.date_range("1990-01-01", "2021-12-01", freq="MS")
INDEX_MONTHS = pd.date_range("2014-01-01", "2021-12-01", freq="MS")
OUTPUT_YEARS = list(range(2015, 2022))


def calendar_fixture():
    base = {"admin_idx": 0, "group_id": 0, "s1_calendar_quality": "q", "s2_calendar_quality": "q", "s1_sos": "", "s1_eos": "",
            "s2_sos": "", "s2_eos": "", "s1_duration_days": 120, "s2_duration_days": 90}
    rows = [
        {"admin_code": "11", "s1_calendar_valid": "1", "s1_cross_year": "0", "s1_sos_month": 3, "s1_sos_day": 15, "s1_eos_month": 7, "s1_eos_day": 10,
         "s2_calendar_valid": "1", "s2_cross_year": "1", "s2_sos_month": 11, "s2_sos_day": 1, "s2_eos_month": 2, "s2_eos_day": 20},
        {"admin_code": "12", "s1_calendar_valid": "1", "s1_cross_year": "0", "s1_sos_month": 2, "s1_sos_day": 29, "s1_eos_month": 6, "s1_eos_day": 30,
         "s2_calendar_valid": "0", "s2_cross_year": "0", "s2_sos_month": 8, "s2_sos_day": 1, "s2_eos_month": 10, "s2_eos_day": 31},
        {"admin_code": "13", "s1_calendar_valid": "1", "s1_cross_year": "0", "s1_sos_month": 4, "s1_sos_day": 31, "s1_eos_month": 8, "s1_eos_day": 1,
         "s2_calendar_valid": "1", "s2_cross_year": "0", "s2_sos_month": 9, "s2_sos_day": 1, "s2_eos_month": 12, "s2_eos_day": 31},
        {"admin_code": "14", "s1_calendar_valid": "1", "s1_cross_year": "1", "s1_sos_month": 10, "s1_sos_day": 1, "s1_eos_month": 3, "s1_eos_day": 31,
         "s2_calendar_valid": "1", "s2_cross_year": "0", "s2_sos_month": 5, "s2_sos_day": 1, "s2_eos_month": 9, "s2_eos_day": 30},
    ]
    return pd.DataFrame([{**base, "admin_idx": i, **r} for i, r in enumerate(rows)])


def inputs(seed, n):
    rng = np.random.default_rng(seed)
    prcp = rng.gamma(rng.uniform(0.6, 3.0, size=(n, 1)), 45.0, size=(n, len(ALL_MONTHS)))
    prcp[rng.random(prcp.shape) < 0.12] = 0.0
    et0 = rng.uniform(50.0, 190.0, size=prcp.shape)
    if n > 3:
        gaps = rng.random(prcp.shape) < 0.01
        prcp[3][gaps[3]] = np.nan                                     # one admin with scattered missing months
    return prcp, et0


def original(path, n_admins, static_admins):
    raw = open(path, "rb").read()
    assert hashlib.sha256(raw).hexdigest() == SHA
    src = raw.decode(); lines = src.splitlines(keepends=True)
    tree = ast.parse(src)
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCS]
    ns = {"np": np, "pd": pd, "special": special, "pycalendar": pycalendar, "ALL_MONTHS": ALL_MONTHS, "INDEX_MONTHS": INDEX_MONTHS,
          "INDEX_GLOBAL_POSITIONS": np.where((ALL_MONTHS >= pd.Timestamp("2014-01-01")) & (ALL_MONTHS <= pd.Timestamp("2021-12-01")))[0],
          "N_ADMINS": n_admins, "BASELINE_START_YEAR": 1991, "BASELINE_END_YEAR": 2020, "NORMAL_PROB_EPS": 1e-6,
          "FULL_COVERAGE_TOLERANCE": 0.999999, "REASON_VALID": 0, "REASON_INPUT_MISSING": 1, "REASON_FIT_INVALID": 2,
          "REASON_OUTSIDE_SUPPORT": 3, "REASON_NUMERICAL": 4, "OUTPUT_YEARS": OUTPUT_YEARS, "SEASONS": ["s1", "s2"],
          "ADMIN_ID": "admin_code", "static_admins": static_admins}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), path, "exec"), ns)
    start = next(i for i, l in enumerate(lines) if l.startswith("month_lookup = {"))
    stop = next(i for i, l in enumerate(lines) if l.startswith("season_plan = pd.DataFrame("))
    plan_src = "".join(lines[start:stop + 3])                        # through "season_rows\n)"
    exec(compile(plan_src, path, "exec"), ns)                          # the original module-level plan loop
    return ns


if __name__ == "__main__":
    cal = calendar_fixture()
    prcp, et0 = inputs(41, len(cal))
    ns = original(sys.argv[1], len(cal), cal)
    spi, spi_r, _ = ns["compute_spi03"](prcp, "chirps")
    spei, spei_r, _ = ns["compute_spei03"](prcp, et0, "chirps")
    plan = ns["season_plan"]
    agg = pd.concat([ns["aggregate_gs"](spi, spi_r, "spi03_gs_chirps"), ns["aggregate_gs"](spei, spei_r, "spei03_gs_chirps")], axis=1)
    np.savez_compressed(os.path.join(HERE, "ipcch_seasonal_golden.npz"), prcp=prcp, et0=et0, spi=spi, spi_reason=spi_r, spei=spei, spei_reason=spei_r)
    keep = ["admin_code", "season_year", "season", "gs_calendar_valid", "gs_start_date", "gs_end_date_exclusive",
            "gs_duration_recalculated_days", "_admin_position", "_month_positions", "_overlap_days"]
    p = plan[keep].copy(); p["_month_positions"] = p["_month_positions"].map(json.dumps); p["_overlap_days"] = p["_overlap_days"].map(json.dumps)
    pd.concat([p, agg], axis=1).to_csv(os.path.join(HERE, "ipcch_seasonal_golden.csv"), index=False, float_format="%.17g")
    cal.to_csv(os.path.join(HERE, "ipcch_seasonal_calendar_fixture.csv"), index=False)
    print("plan rows", len(plan), "valid", int(plan.gs_calendar_valid.sum()), "spi finite", int(np.isfinite(spi).sum()),
          "spei finite", int(np.isfinite(spei).sum()), "gs spi complete", int((agg["spi03_gs_chirps_status"] == "COMPLETE").sum()),
          "gs spei complete", int((agg["spei03_gs_chirps_status"] == "COMPLETE").sum()))
