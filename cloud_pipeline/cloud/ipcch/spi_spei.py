"""SPI-3 / SPEI-3 numerics retained from the shared-folder ``monthly/spi_monthly.py`` (CELL 9-11, sha256 0e29ed35...;
task 10-29 R1/R34/R40). The arithmetic is kept operation for operation; only the module globals ``ALL_MONTHS`` and
``BASELINE_START_YEAR``/``BASELINE_END_YEAR`` become explicit arguments, and the Colab download/IO cells are replaced
by the operational provider. Inputs are admin x month matrices over a contiguous monthly axis that must contain the
complete 1991-2020 baseline (strict 30-year rule, no 29-year fallback).

* rolling_three_month_sum: all three months finite, else NaN.
* SPI: zero-corrected gamma per ending calendar month; parameters valid only with a complete baseline, >= 10 positive
  totals, finite alpha/beta and beta > 0; probability clipped to [1e-6, 1 - 1e-6] before the normal quantile.
* SPEI: P - ET0 (both finite), UB-PWM generalized log-logistic fit with plotting position (rank - 0.35)/n; parameters
  valid with a complete baseline, beta > 1, alpha > 0 and finite origin; a value only where current > fitted origin.
* ET0 PATCH32: patch values fill only missing ET0 cells, never overwrite existing values.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import special

SPI_METHOD = "SPI3_ZERO_CORRECTED_GAMMA_STRICT_1991_2020_NO_29_YEAR_FALLBACK"
SPEI_METHOD = "SPEI_UBPWM_GLO_STRICT_SUPPORT_V3"
ET0_METHOD = "ERA5LAND_FAO56_ET0_PATCH32_FILL_MISSING_ONLY"
BASELINE = (1991, 2020)


def month_axis(first: str, last: str) -> pd.DatetimeIndex:
    """Contiguous month-start axis ``first``..``last`` (YYYY-MM)."""
    return pd.date_range(f"{first}-01", f"{last}-01", freq="MS")


def _check(months: pd.DatetimeIndex, *matrices: np.ndarray) -> None:
    if not isinstance(months, pd.DatetimeIndex) or len(months) == 0:
        raise ValueError("months must be a non-empty DatetimeIndex")
    if not months.equals(pd.date_range(months[0], periods=len(months), freq="MS")):
        raise ValueError("months must be a contiguous month-start axis")
    for m in matrices:
        if m.ndim != 2 or m.shape[1] != len(months):
            raise ValueError(f"matrix shape {m.shape} does not match {len(months)} months")


def rolling_three_month_sum(values):
    values = np.asarray(values, dtype=np.float64)
    output = np.full_like(values, np.nan, dtype=np.float64)
    complete = np.isfinite(values[:, :-2]) & np.isfinite(values[:, 1:-1]) & np.isfinite(values[:, 2:])
    sums = values[:, :-2] + values[:, 1:-1] + values[:, 2:]
    output[:, 2:] = np.where(complete, sums, np.nan)
    return output


def normal_from_probability(probability):
    probability = np.clip(probability, 1e-6, 1 - 1e-6)
    return np.sqrt(2.0) * special.erfinv(2.0 * probability - 1.0)


def _baseline_mask(months, month, baseline):
    mask = (months.year >= baseline[0]) & (months.year <= baseline[1]) & (months.month == month)
    if mask.sum() != baseline[1] - baseline[0] + 1:
        raise ValueError(f"the month axis must contain the complete {baseline[0]}-{baseline[1]} baseline (strict)")
    return mask


def compute_spi03_monthly(prcp_matrix, months: pd.DatetimeIndex, baseline=BASELINE):
    prcp_matrix = np.asarray(prcp_matrix, dtype=np.float64)
    _check(months, prcp_matrix)
    n_years = float(baseline[1] - baseline[0] + 1)
    accumulated = rolling_three_month_sum(prcp_matrix)
    output = np.full(prcp_matrix.shape, np.nan, dtype=np.float64)
    for month in range(1, 13):
        baseline_values = accumulated[:, _baseline_mask(months, month, baseline)]
        sample_complete = np.isfinite(baseline_values).all(axis=1)
        positive_mask = np.isfinite(baseline_values) & (baseline_values > 0)
        positive_count = positive_mask.sum(axis=1)
        positive_sum = np.where(positive_mask, baseline_values, 0.0).sum(axis=1)
        positive_log_sum = np.where(positive_mask, np.log(np.where(positive_mask, baseline_values, 1.0)), 0.0).sum(axis=1)
        safe_count = np.maximum(positive_count, 1)
        mean = positive_sum / safe_count
        mean_log = positive_log_sum / safe_count
        with np.errstate(divide="ignore", invalid="ignore"):
            a_value = np.log(mean) - mean_log
        a_value = np.maximum(a_value, 1e-6)
        alpha = (1.0 + np.sqrt(1.0 + (4.0 / 3.0) * a_value)) / (4.0 * a_value)
        beta = mean / alpha
        q_zero = (n_years - positive_count) / n_years
        parameter_valid = (sample_complete & (positive_count >= 10) & np.isfinite(alpha) & np.isfinite(beta) & (beta > 0))
        positions = np.where(months.month == month)[0]
        current = accumulated[:, positions]
        with np.errstate(divide="ignore", invalid="ignore"):
            scaled = np.maximum(current / beta[:, None], 0.0)
            gamma_cdf = special.gammainc(alpha[:, None], scaled)
            probability = q_zero[:, None] + (1.0 - q_zero[:, None]) * gamma_cdf
            z_value = normal_from_probability(probability)
        valid = np.isfinite(current) & parameter_valid[:, None] & np.isfinite(z_value)
        output[:, positions] = np.where(valid, z_value, np.nan)
    return output


def compute_spei03_monthly(prcp_matrix, et0_matrix, months: pd.DatetimeIndex, baseline=BASELINE):
    prcp_matrix = np.asarray(prcp_matrix, dtype=np.float64)
    et0_matrix = np.asarray(et0_matrix, dtype=np.float64)
    _check(months, prcp_matrix, et0_matrix)
    balance = np.where(np.isfinite(prcp_matrix) & np.isfinite(et0_matrix), prcp_matrix - et0_matrix, np.nan)
    accumulated = rolling_three_month_sum(balance)
    output = np.full(prcp_matrix.shape, np.nan, dtype=np.float64)
    for month in range(1, 13):
        baseline_values = accumulated[:, _baseline_mask(months, month, baseline)]
        sample_complete = np.isfinite(baseline_values).all(axis=1)
        safe_baseline = np.where(np.isfinite(baseline_values), baseline_values, 0.0)
        sorted_values = np.sort(safe_baseline, axis=1)
        count = sorted_values.shape[1]
        rank = np.arange(1, count + 1, dtype=np.float64)
        plotting_position = (rank - 0.35) / count

        def pwm(power):
            weights = (1.0 - plotting_position) ** power
            return np.mean(sorted_values * weights[None, :], axis=1)

        pwm0, pwm1, pwm2 = pwm(0), pwm(1), pwm(2)
        numerator = 2.0 * pwm1 - pwm0
        denominator = 6.0 * pwm1 - pwm0 - 6.0 * pwm2
        with np.errstate(divide="ignore", invalid="ignore"):
            beta_raw = np.where(np.abs(denominator) > 1e-12, numerator / denominator, 1.0001)
        safe_beta = np.maximum(beta_raw, 1.0001)
        with np.errstate(over="ignore", invalid="ignore"):
            gamma1 = special.gamma(1.0 + 1.0 / safe_beta)
            gamma2 = special.gamma(1.0 - 1.0 / safe_beta)
            alpha = (pwm0 - 2.0 * pwm1) * safe_beta / (gamma1 * gamma2)
            gamma_origin = pwm0 - alpha * gamma1 * gamma2
        parameter_valid = (sample_complete & np.isfinite(beta_raw) & np.isfinite(alpha) & np.isfinite(gamma_origin)
                           & (beta_raw > 1.0) & (alpha > 0.0))
        positions = np.where(months.month == month)[0]
        current = accumulated[:, positions]
        distance = current - gamma_origin[:, None]
        safe_distance = np.maximum(distance, 1e-6)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            probability = 1.0 / (1.0 + (alpha[:, None] / safe_distance) ** beta_raw[:, None])
            z_value = normal_from_probability(probability)
        valid = np.isfinite(current) & parameter_valid[:, None] & (distance > 0.0) & np.isfinite(z_value)
        output[:, positions] = np.where(valid, z_value, np.nan)
    return output


def apply_et0_patch(et0: np.ndarray, patch: np.ndarray) -> tuple[np.ndarray, int]:
    """PATCH32 rule: fill missing ET0 cells from the patch; never overwrite an existing value."""
    et0 = np.asarray(et0, dtype=np.float64)
    patch = np.asarray(patch, dtype=np.float64)
    if et0.shape != patch.shape:
        raise ValueError("ET0 patch shape differs")
    fill = np.isnan(et0) & np.isfinite(patch)
    return np.where(fill, patch, et0), int(fill.sum())
