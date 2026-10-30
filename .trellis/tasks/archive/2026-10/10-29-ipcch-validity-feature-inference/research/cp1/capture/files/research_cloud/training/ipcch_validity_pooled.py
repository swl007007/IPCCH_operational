"""IPCCH validity-augmented pooled XGBoost quartet + B2 shared calibration (task 10-16-ipcch-validity-augmented-pooled).

One job = one arm (``original`` | ``validity_augmented``) x one horizon H in {0, 6, 12} (prd.md R1-R6, design.md
sections 5-8). Stage 1 builds the dataset from pinned base inputs (``ipcch_validity_features.build_dataset``).
Stage 2 runs every annual scoring context E (main years + 2026-01..04 supplement), each with:

* scheduled anchor T0 = first scheduled target; supervised cutoff C = T0 - 1 at H0, else T0 - H;
* S_E = the source-round families of E's scored rows, excluded from the backbone's fitting labels and from every
  original-report history used by its fitting and scoring rows;
* honest historical out-of-time (OOT) providers: provider blocks P (annual, first targets 2018-02 / 2018-07 /
  2019-01 for H0 / 6 / 12, split at the main-window boundary) whose first target is <= C_E. P predicts its window
  rows with target and source availability <= C_E outside S_E; S_P = their families; P fits at C_P on rows outside
  S_E union S_P with histories excluding the same union. No provider is reused across contexts;
* B2: shared eight-slot residual ridge (penalty 0.01, intercept unpenalized) on the provider predictions with
  weights 2**(-(C_E - U)/24); an empty pool is the explicit uncalibrated identity;
* scoring: backbone raw quartet -> B2 correction -> bounded decreasing projection -> inclusive 0.20 decoding.

Fixed quartet (no tuning, no early stopping): reg:squarederror, CPU hist, seed 42, 200 trees, learning rate 0.1,
min_child_weight 0, reg_alpha 0, reg_lambda 1, 16 threads; q3 depth 9 / subsample 0.5 / colsample 0.7 / gamma 0.1;
q2/q4/q5 depth 11 / subsample 1 / colsample 0.5 / gamma 0. Fitting weights 2**(-(C - U)/24) on every eligible
monthly row (originals and copies alike); scoring is unweighted.

Refresh arms (task 10-19-ipcch-202610-merge-retrain): the recipe declares a ``calendar`` (main window, supplement and
its report blocks, or named hindcast scoring contexts served by one shared backbone) and a ``training`` scheme
(expanding | fixed_window | rolling_months; halving24 | flat weights; b2 | identity calibration; providers on/off),
and pins self-consistency digests (``baseline.kind = self_consistency``) computed from a reviewed local no-fit build
of the same inputs. Recipes without these keys keep the module constants and every output unchanged.

  python -m research_cloud.training.ipcch_validity_pooled --manifest M.json --config C.json --output DIR|gs://...
  python -m research_cloud.training.ipcch_validity_pooled plan --dataset DIR --arm A --horizon H --out DIR
  python -m research_cloud.training.ipcch_validity_pooled plan --dataset DIR --config RECIPE --out DIR [--digests] [--check]
  python -m research_cloud.training.ipcch_validity_pooled gate --manifest M.json --config RECIPE --out NEW_DIR   # no fit
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from research_cloud.training import ipcch_validity_features as vf

FAMILY = "ipcch_validity_pooled"
IDP_ARM = "validity_augmented_idp"     # task 10-17: validity_augmented labels + three local-IDP suffix columns
HSTACK_ARM = "validity_augmented_idp_hstack"   # task 10-17 hstack: idp features + longer-horizon origin blocks
STACK = {0: (6, 12), 6: (12,)}                  # horizon -> stacked longer horizons (H0 >= H6 >= H12)
HSTACK_FEATURES = {0: 937, 6: 694}
# Task 10-19 (2026-10 refresh): the idp feature set on new inputs; arm -> (model_card.arm_role, training scheme).
# Task 10-20 (aggregated ACLED): the production configuration with the 14 compact conflict columns replaced by 114 lag-1
# aggregated-ACLED columns (527/539/539), fitted uncalibrated (identity, no providers) and paired with the retained
# production run's uncalibrated predictions. ``candidate`` is descriptive; ``check_acled_arm`` holds the contract.
ACLED_ARM = "validity_augmented_idp_202610_acledagg_lag1_uncal"
REFRESH_ARMS = {
    "validity_augmented_idp_202610": ("production", "expanding"),
    "validity_augmented_idp_202610_hindcast2325": ("hindcast", "fixed_window"),
    "validity_augmented_idp_202610_rolling36": ("control", "rolling_months"),
    ACLED_ARM: ("candidate", "expanding"),
}
ACLED_ARMS = (ACLED_ARM,)
# Task 10-21 (Vertex HPT of the aggregated-ACLED arm): the ACLED arm's inputs, 527/539/539 features, production calendar
# and identity calibration with tuned quartet parameters. ``mode=tuning`` (``candidate_role`` search = one HPT trial,
# reference = the fixed quartet in one CustomJob) fits the main years on the D7 selection cohorts and keeps four pooled
# metrics (tracking-only, no package); ``mode=formal`` refits every annual context with parameters frozen after all three
# horizons' searches and compares six metrics with the selected ACLED baseline's retained predictions.
HPT_ARM = "validity_augmented_idp_202610_acledagg_lag1_uncal_hpt"
ACLED_FEATURE_ARMS = (ACLED_ARM, HPT_ARM)        # the 114 aggregated-ACLED columns and identity calibration (no B2 inputs)
IDP_ARMS = (IDP_ARM, *REFRESH_ARMS)              # arms with the three local-IDP suffix columns (427/439/439; 527/539/539)
ARMS = ("original", "validity_augmented", IDP_ARM, HSTACK_ARM, *REFRESH_ARMS, HPT_ARM)
FROZEN_BASELINE, SELF_CONSISTENCY = "frozen_baseline", "self_consistency"
SCHEMES = ("expanding", "fixed_window", "rolling_months")
# Regional (local) variant (task 10-17 SA-local): the same arms restricted to one region's countries at dataset entry.
# Southern Africa = region 3 of IPCCH/data/reference/area_id_country_region_mapping.csv (no country spans two regions).
REGIONS = {"SA": {"code": 3, "iso2": ("AO", "LS", "MG", "MW", "MZ", "NA", "SZ", "ZA", "ZM", "ZW")}}
REGION_ARMS = (IDP_ARM, HSTACK_ARM)
REGION_EQUIVALENCE_KEYS = ("rows", "arm_rows_csv_sha256", "targets_sha256", "phase_sha256", "feature_order_sha256",
                           "feature_X_sha256", "feature_nan_mask_sha256")
HORIZONS = (0, 6, 12)
TARGETS = ("q2", "q3", "q4", "q5")
MAIN_FIRST = {0: "2023-01", 6: "2023-07", 12: "2024-01"}
MAIN_LAST = "2025-12"
SUPPLEMENT = ("2026-01", "2026-04")
PROVIDER_FIRST = {0: "2018-02", 6: "2018-07", 12: "2019-01"}
EARLIEST_CUTOFF = "2018-01"
HALF_LIFE = 24
RIDGE = 0.01
SOLVER_TOL = 1e-9
N_THREADS = 16
OBJECTIVE = "primary.all_scored.binary.f1"
CORE_INPUTS = ("prcp_anom_month_ensmean__ma3_at_origin", "tmean_anom_month_ensmean__ma3_at_origin",
               "event_count_violence__ma3_at_origin")
_COMMON = {"n_estimators": 200, "learning_rate": 0.1, "min_child_weight": 0.0, "reg_alpha": 0.0, "reg_lambda": 1.0}
QUARTET = {
    "q2": {"max_depth": 11, "subsample": 1.0, "colsample_bytree": 0.5, "gamma": 0.0, **_COMMON},
    "q3": {"max_depth": 9, "subsample": 0.5, "colsample_bytree": 0.7, "gamma": 0.1, **_COMMON},
    "q4": {"max_depth": 11, "subsample": 1.0, "colsample_bytree": 0.5, "gamma": 0.0, **_COMMON},
    "q5": {"max_depth": 11, "subsample": 1.0, "colsample_bytree": 0.5, "gamma": 0.0, **_COMMON},
}
XGB_FIXED = {"objective": "reg:squarederror", "tree_method": "hist", "device": "cpu", "booster": "gbtree",
             "random_state": 42, "n_jobs": N_THREADS, "scale_pos_weight": 1.0}
# Recipe ``fixed`` must equal this exactly; the trial refuses any other numerical setting.
FIXED = {"seed": 42, "n_threads": N_THREADS, "half_life_months": HALF_LIFE, "b2_ridge_penalty": RIDGE,
         "quartet": json.dumps(QUARTET, sort_keys=True), "xgb_fixed": json.dumps(XGB_FIXED, sort_keys=True),
         "early_stopping": "none", "calibration": "B2 shared residual ridge, eight slots, honest annual OOT providers"}
# The uncalibrated aggregated-ACLED arm: every numerical setting of FIXED; only the calibration description differs.
FIXED_UNCALIBRATED = {**FIXED, "calibration": "none (identity): no B2 or provider fits by design; the backbone quartet is "
                                              "projected (bounded, decreasing) and decoded with inclusive q_k >= 0.20"}
ACLED_SUPPLEMENT = ("2026-01", "2026-10")
ACLED_SUPPLEMENT_BLOCKS = (("2026-01", "2026-04"), ("2026-05", "2026-10"))
COMPARISON_ROLES = ("acled_baseline_reference", "baseline_predictions", "region_mapping")
ACLED_BASELINE_ARM = "validity_augmented_idp_202610"
# Exclusive regions of the compact-climate reference (sources/IPCCH/IPCCHMLflow/naming.py); scored slices of the global
# model, joined by area_id with the frozen IPCCH/data/reference/area_id_country_region_mapping.csv.
REGION_MAPPING_SHA256 = "18ab5099ce2d1154fb5686183ee399124e18427cc1594923f7abe2769da1611d"
REGION_NAMES = {0: "Asia", 1: "East Africa", 2: "West Africa", 3: "Southern Africa", 4: "Central Africa",
                5: "Latin America", 6: "Mali", 7: "Somalia", 8: "Palestine"}
# Task 10-21 search (D3, D8): q3 has its own group, q2/q4/q5 share one; each group searches the same six axes (12
# dimensions, inclusive bounds). gamma/reg_alpha/reg_lambda stay at the fixed quartet's values per group; every
# XGB_FIXED setting (seed 42, CPU hist, 16 threads, squared error) is unchanged and there is no early stopping.
HPT_GROUPS = {"q3": ("q3",), "other": ("q2", "q4", "q5")}
HPT_AXES = {"n_estimators": ("int", 100, 600, "linear"), "learning_rate": ("float", 0.02, 0.20, "log"),
            "max_depth": ("int", 4, 12, "linear"), "min_child_weight": ("float", 0.0, 32.0, "linear"),
            "subsample": ("float", 0.5, 1.0, "linear"), "colsample_bytree": ("float", 0.4, 1.0, "linear")}
HPT_SPACE = {f"{g}_{a}": {"type": t, "min": lo, "max": hi, "scale": s} for g in HPT_GROUPS for a, (t, lo, hi, s) in HPT_AXES.items()}
HPT_UNTUNED = {"q3": {"gamma": 0.1, "reg_alpha": 0.0, "reg_lambda": 1.0}, "other": {"gamma": 0.0, "reg_alpha": 0.0, "reg_lambda": 1.0}}
HPT_REFERENCE = {f"{g}_{a}": QUARTET[qs[0]][a] for g, qs in HPT_GROUPS.items() for a in HPT_AXES}   # the fixed quartet
HPT_FIXED = {**{k: v for k, v in FIXED_UNCALIBRATED.items() if k != "quartet"},
             "untuned": json.dumps(HPT_UNTUNED, sort_keys=True), "parameter_groups": json.dumps(HPT_GROUPS, sort_keys=True)}
HPT_OBJECTIVE = "selection.binary_f1"                 # the Vertex search objective (D2); ranking uses SELECTION_METRICS
HPT_FORMAL_OBJECTIVE = "historical_pooled.binary_f1"
HPT_MODES, HPT_ROLES = ("tuning", "formal"), ("search", "reference")
SELECTION_METRICS = ("binary_f1", "phase3plus_r2", "macro_f1", "binary_f2")    # strict lexicographic order, descending
FORMAL_METRICS = (*SELECTION_METRICS, "binary_precision", "binary_recall")
METRIC_DEFINITIONS = {
    "binary_f1": "F1 of crisis = phase >= 3 (decoded projected uncalibrated quartet vs phase_truth)",
    "binary_f2": "F2 (recall-weighted, beta 2) of crisis = phase >= 3",
    "binary_precision": "precision of crisis = phase >= 3", "binary_recall": "recall of crisis = phase >= 3",
    "phase3plus_r2": "R2 of the continuous q3 share (p3+p4+p5)/sum(p1..p5) against the projected uncalibrated q3; "
                     "negative values kept",
    "macro_f1": "four-class macro F1 on the fixed axis 1, 2, 3, 4-5",
    "n_rows": "augmented rows (originals and validity copies), each weighted equally; no training decay weights"}
# D7: report families whose originals/copies cross the selection and 2026 windows; (iso2, original month, frozen id).
SELECTION_EXCLUDED = (("CF", "2025-09", 7364340), ("MZ", "2025-10", 31481589))
SELECTION_ROWS = {0: 31212, 6: 25890, 12: 20238}
FINAL_ROWS = {0: 48755, 6: 43433, 12: 37781}
HOLDOUT_ROWS = 14742
ACLED_BASELINE_RUNS = {0: "a13398698cec4fc393136efc535dcb63", 6: "5d6f32fdaaa344d389286324d0d0f778",
                       12: "428aad3660a94b9396c454e002d8ad56"}
FREEZE_KIND, FREEZE_INDEX_KIND = "ipcch_acledagg_hpt_freeze", "ipcch_acledagg_hpt_freeze_index"
FROZEN_KEYS = ("freeze_sha256", "freeze_index_sha256", "winner_role", "winner_trial_id", "params_sha256")
FORMAL_ROLES = ("baseline_predictions", "region_mapping", "freeze", "freeze_index")


def fixed_settings(arm):
    return FIXED_UNCALIBRATED if arm in ACLED_ARMS else FIXED


def core_inputs(arm):
    """B2 calibration dynamics of an arm; the uncalibrated aggregated-ACLED arms have none (no old ACLED placeholder)."""
    return () if arm in ACLED_FEATURE_ARMS else CORE_INPUTS


class ValidityError(RuntimeError):
    """A temporal/report-isolation, numerical or contract violation; the job stops (never a fallback)."""


def parse_month(label):
    y, m = (int(x) for x in str(label).split("-"))
    return y * 12 + m - 1


label = vf.month_label


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def array_digest(a):
    a = np.ascontiguousarray(a)
    return hashlib.sha256(str(a.dtype).encode() + str(a.shape).encode() + a.tobytes()).hexdigest()


def ae(name):
    vf.ae_modules()
    return importlib.import_module(f"ipcch_alphaearth.{name}")


# --------------------------------------------------------------------------- calendar (design section 5)


@dataclass(frozen=True)
class Block:
    block_id: str
    role: str          # main | supplement | provider
    target_lo: int
    target_hi: int
    cutoff: int

    def record(self):
        return {**asdict(self), "target_lo_month": label(self.target_lo), "target_hi_month": label(self.target_hi),
                "cutoff_month": label(self.cutoff)}


def fit_cutoff(first_target, horizon):
    """Supervised cutoff of a block anchored at its first scheduled target (never the first observed label)."""
    return int(first_target) - 1 if int(horizon) == 0 else int(first_target) - int(horizon)


@dataclass(frozen=True)
class Schedule:
    """Calendar and training scheme of one arm/H (task 10-19). The default equals the module constants, so every
    existing recipe plans, fits and reports exactly as before. Only refresh-arm recipes declare one (``calendar`` /
    ``training``); ``declared`` also switches on their extended outputs (per-year / per-block metrics, uncalibrated
    backbone metrics, plan assertions and scored NaN tables)."""
    main_first: tuple = tuple(sorted(MAIN_FIRST.items()))   # ((horizon, first main target), ...)
    main_last: str = MAIN_LAST
    supplement: tuple = SUPPLEMENT                          # (from, to) or None (no supplement context)
    supplement_blocks: tuple = ()                           # report blocks ((from, to), ...) inside the supplement
    scoring_contexts: tuple = ()                            # hindcast: ((block_id, from, to), ...) replace main + supplement
    shared_cutoff: str = None                               # hindcast: one backbone at this cutoff serves every context
    scheme: str = "expanding"                               # expanding | fixed_window | rolling_months
    window: tuple = None                                    # fixed_window: inclusive fitting-target (from, to)
    months: int = None                                      # rolling_months: fitting targets in (C - months, C]
    sample_weights: str = "halving24"                       # halving24 (2**(-(C-U)/24)) | flat
    calibration: str = "b2"                                 # b2 | identity (the existing identity_no_support path)
    providers: bool = True
    declared: bool = False

    def first(self, horizon):
        return dict(self.main_first)[int(horizon)]

    def record(self):
        return {**asdict(self), "main_first": {str(h): m for h, m in self.main_first}}


DEFAULT_SCHEDULE = Schedule()
CALENDAR_KEYS = ("main_first", "main_last", "supplement", "supplement_blocks", "scoring_contexts", "shared_backbone")
TRAINING_KEYS = ("scheme", "window", "months", "sample_weights", "calibration", "providers")


def _month(text, what):
    try:
        y, m = (int(x) for x in str(text).split("-"))
    except (TypeError, ValueError) as e:
        raise ValidityError(f"{what}: {text!r} is not a YYYY-MM month") from e
    if not 1 <= m <= 12 or f"{y:04d}-{m:02d}" != str(text):
        raise ValidityError(f"{what}: {text!r} is not a YYYY-MM month")
    return parse_month(text)


def _window(pair, what):
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        raise ValidityError(f"{what} must be [from, to]")
    lo, hi = (_month(m, what) for m in pair)
    if lo > hi:
        raise ValidityError(f"{what} is reversed: {list(pair)}")
    return lo, hi


def schedule_from_config(config, horizon):
    """The validated Schedule of a recipe; recipes without ``calendar``/``training`` get DEFAULT_SCHEDULE."""
    cal, tr = config.get("calendar"), config.get("training")
    if cal is None and tr is None:
        return DEFAULT_SCHEDULE
    if not isinstance(cal, dict) or not isinstance(tr, dict):
        raise ValidityError("a declared schedule needs both a calendar and a training object")
    unknown = sorted(set(cal) - set(CALENDAR_KEYS)) + sorted(set(tr) - set(TRAINING_KEYS))
    if unknown:
        raise ValidityError(f"unknown calendar/training keys {unknown}")
    h = int(horizon)
    first = {int(k): v for k, v in (cal.get("main_first") or {str(k): v for k, v in MAIN_FIRST.items()}).items()}
    if set(first) != set(HORIZONS):
        raise ValidityError(f"calendar main_first needs every horizon {HORIZONS}")
    for k, v in first.items():
        _month(v, f"main_first[{k}]")
    main_last = cal.get("main_last", MAIN_LAST)
    _month(main_last, "main_last")
    supplement = cal.get("supplement", list(SUPPLEMENT))
    blocks = tuple(tuple(b) for b in cal.get("supplement_blocks") or ())
    contexts = cal.get("scoring_contexts") or []
    shared = cal.get("shared_backbone")
    scheme = tr.get("scheme", "expanding")
    weights, calibration, providers = tr.get("sample_weights", "halving24"), tr.get("calibration", "b2"), tr.get("providers", True)
    if scheme not in SCHEMES or weights not in ("halving24", "flat") or calibration not in ("b2", "identity") \
            or not isinstance(providers, bool):
        raise ValidityError(f"unsupported training {tr}")
    if (calibration == "identity") == providers:
        raise ValidityError("identity calibration means no providers, and B2 calibration needs providers")
    if scheme != "expanding" and calibration != "identity":
        raise ValidityError("fixed_window / rolling_months backbones are uncalibrated (identity, no providers)")
    window = months = None
    if scheme == "fixed_window":
        window = tuple(tr.get("window") or ())
        _window(window, "training.window")
    elif "window" in tr:
        raise ValidityError("training.window applies only to fixed_window")
    if scheme == "rolling_months":
        months = tr.get("months")
        if isinstance(months, bool) or not isinstance(months, int) or months < 1:
            raise ValidityError("rolling_months needs a positive integer training.months")
    elif "months" in tr:
        raise ValidityError("training.months applies only to rolling_months")
    named = ()
    if contexts:      # hindcast: named contexts replace the main window and the supplement; one shared backbone
        if "main_first" in cal or "main_last" in cal or cal.get("supplement") is not None or blocks:
            raise ValidityError("scoring_contexts replace the main window and the supplement (set supplement null)")
        if not isinstance(shared, dict) or set(shared) != {"cutoff"}:
            raise ValidityError("scoring_contexts need shared_backbone = {cutoff}")
        C = _month(shared["cutoff"], "shared_backbone.cutoff")
        if scheme != "fixed_window":
            raise ValidityError("scoring_contexts are served by a fixed_window backbone")
        seen, spans = set(), []
        for c in contexts:
            if not isinstance(c, dict) or set(c) != {"name", "target_from", "target_to"}:
                raise ValidityError("each scoring context is {name, target_from, target_to}")
            name = str(c["name"])
            if not name.startswith(f"h{h:02d}_") or name in seen or any(ch in name for ch in "|/\\ '\""):
                raise ValidityError(f"scoring context name {name!r} must be unique and start with h{h:02d}_")
            seen.add(name)
            spans.append((*_window((c["target_from"], c["target_to"]), name), name))
        spans.sort()
        if any(a[1] >= b[0] for a, b in zip(spans, spans[1:])):
            raise ValidityError("scoring contexts overlap")
        lo, hi = _window(window, "training.window")
        if lo > C or any(not (b < lo or a > min(hi, C)) for a, b, _ in spans):
            raise ValidityError("the fitting window (clipped at the shared cutoff) must be nonempty and exclude every scored window")
        named = tuple((n, label(a), label(b)) for a, b, n in spans)
        supplement = None
    else:
        if shared is not None:
            raise ValidityError("shared_backbone applies only to scoring_contexts")
        if supplement is not None:
            s0, s1 = _window(supplement, "calendar.supplement")
            if s0 <= _month(main_last, "main_last"):
                raise ValidityError("the supplement starts after the main window")
            for b in blocks:
                b0, b1 = _window(b, "calendar.supplement_blocks")
                if b0 < s0 or b1 > s1:
                    raise ValidityError(f"supplement block {list(b)} lies outside the supplement")
            supplement = tuple(supplement)
        elif blocks:
            raise ValidityError("supplement_blocks need a supplement")
        if _month(first[h], "main_first") > _month(main_last, "main_last"):
            raise ValidityError("main window is empty at this horizon")
    return Schedule(main_first=tuple(sorted(first.items())), main_last=main_last, supplement=supplement,
                    supplement_blocks=blocks, scoring_contexts=named, shared_cutoff=shared["cutoff"] if contexts else None,
                    scheme=scheme, window=window, months=months, sample_weights=weights, calibration=calibration,
                    providers=providers, declared=True)


def scoring_blocks(horizon, schedule=None):
    s = schedule or DEFAULT_SCHEDULE
    h = int(horizon)
    if s.scoring_contexts:      # hindcast: the named windows, every one at the shared backbone cutoff
        C = parse_month(s.shared_cutoff)
        return [Block(name, "hindcast", parse_month(lo), parse_month(hi), C) for name, lo, hi in s.scoring_contexts]
    first, last = parse_month(s.first(h)), parse_month(s.main_last)
    out, lo = [], first
    while lo <= last:
        hi = min((lo // 12) * 12 + 11, last)
        out.append(Block(f"h{h:02d}_main_{lo // 12}", "main", lo, hi, fit_cutoff(lo, h)))
        lo = hi + 1
    if s.supplement is not None:
        s0, s1 = (parse_month(m) for m in s.supplement)
        out.append(Block(f"h{h:02d}_supp_{s0 // 12}", "supplement", s0, s1, fit_cutoff(s0, h)))
    return out


def provider_blocks(horizon, schedule=None):
    """Annual OOT provider blocks from the provider start up to the latest scoring cutoff, split at January and at
    the main-window first target (e.g. H6 2023-01..06 / 2023-07..12). None when the schedule has no providers."""
    s = schedule or DEFAULT_SCHEDULE
    if not s.providers:
        return []
    h = int(horizon)
    start, main_first = parse_month(PROVIDER_FIRST[h]), parse_month(s.first(h))
    last = max(b.cutoff for b in scoring_blocks(h, s))
    out, lo = [], start
    while lo <= last:
        hi = (lo // 12) * 12 + 11
        if lo < main_first <= hi:
            hi = main_first - 1
        out.append(Block(f"h{h:02d}_prov_{label(lo)}", "provider", lo, hi, fit_cutoff(lo, h)))
        lo = hi + 1
    if any(b.cutoff < parse_month(EARLIEST_CUTOFF) for b in out):
        raise ValidityError("a provider cutoff precedes 2018-01")
    return out


def decay(target, cutoff):
    age = int(cutoff) - np.asarray(target, dtype=np.int64)
    if (age < 0).any():
        raise ValidityError("weighted row after its cutoff")
    return np.power(2.0, -age.astype(np.float64) / HALF_LIFE)


def fit_weights(d, rows, cutoff):
    """Fitting weights of the schedule: halving24 = ``decay`` (default); flat = 1 (the cutoff rule still applies)."""
    w = decay(d.target[rows], cutoff)
    return np.ones_like(w) if d.schedule.sample_weights == "flat" else w


def n_eff(w):
    w = np.asarray(w, dtype=np.float64)
    return float(w.sum() ** 2 / np.sum(w * w)) if len(w) else 0.0


# --------------------------------------------------------------------------- arm data and context plan


@dataclass
class ArmData:
    arm: str
    horizon: int
    labels: pd.DataFrame      # arm rows only, aligned with X
    X: np.ndarray             # context-free base features; history columns are rebuilt per fit
    order: list
    obs: pd.DataFrame         # original reported-phase observations with families
    rows: pd.DataFrame        # row ledger (origins, oracle months)
    hist_groups: list = None  # [(history column indices, horizon)]: own block first, then any stacked blocks
    schedule: Schedule = None  # calendar/training scheme (task 10-19); None = DEFAULT_SCHEDULE (module constants)

    def __post_init__(self):
        if self.schedule is None:
            self.schedule = DEFAULT_SCHEDULE
        L = self.labels
        self.admin = L["admin_code"].to_numpy(np.int64)
        self.target = L["month_ord"].to_numpy(np.int64)
        self.avail = L["source_available_ord"].to_numpy(np.int64)
        self.family = L["source_family"].to_numpy(np.int64)
        # task 10-28: evidenced source-report family of a preserved cross-country CH label (-1 = none); every row-level
        # exclusion tests BOTH ids and every scored row contributes both to S_E. Labels without the column: all -1.
        self.family_alias = (L["source_family_alias"].to_numpy(np.int64) if "source_family_alias" in L.columns
                             else np.full(len(L), -1, np.int64))
        self.has_alias = bool((self.family_alias >= 0).any())
        # history events carry their own alias column in a CH build (a share-invalid cross-country row is no label but
        # its reported phase is an event); the saved dependency ledgers then record the selected events' aliases
        self.obs_aliased = "family_alias" in self.obs.columns
        self.Y = L[list(TARGETS)].to_numpy(np.float64)
        self.phase = L["phase_truth"].to_numpy(np.int64)
        self.kind = L["label_kind"].to_numpy(dtype=object)
        self.hist_idx = vf.history_columns(self.order)
        if self.hist_groups is None:
            self.hist_groups = [(self.hist_idx, self.horizon)]
        self.core_inputs = core_inputs(self.arm)
        self.core_idx = [self.order.index(c) for c in self.core_inputs]
        if not np.isfinite(self.Y).all() or ((self.phase < 1) | (self.phase > 5)).any():
            raise ValidityError("arm labels lack finite targets/phases")
        if (self.avail > self.target).any():
            raise ValidityError("a label's source becomes available after its target month")


def select_arm(labels, X, arm):
    if arm == "original":
        mask = (labels["label_kind"] == "original").to_numpy()
    elif arm in ("validity_augmented", IDP_ARM, HSTACK_ARM, *REFRESH_ARMS, HPT_ARM):
        mask = np.ones(len(labels), dtype=bool)
    else:
        raise ValidityError(f"unknown arm {arm!r}")
    return labels.loc[mask].reset_index(drop=True), X[mask]


def row_families(d: ArmData, rows):
    """Sorted unique family ids of ``rows``: their families plus (task 10-28) their aliases. Without aliases this is
    exactly ``np.unique(d.family[rows])``."""
    f = np.unique(d.family[rows])
    if not d.has_alias:
        return f
    a = d.family_alias[rows]
    return np.union1d(f, a[a >= 0])


def in_families(d: ArmData, families, rows=None):
    """Row mask: family OR (task 10-28) alias in ``families``. Without aliases exactly ``np.isin(d.family, families)``."""
    fam = d.family if rows is None else d.family[rows]
    m = np.isin(fam, families)
    if d.has_alias:
        al = d.family_alias if rows is None else d.family_alias[rows]
        m |= (al >= 0) & np.isin(al, families)
    return m


def fitting_window(d: ArmData, cutoff):
    """Fitting-target mask of the schedule's scheme at ``cutoff`` (the <= cutoff rule is applied separately)."""
    s = d.schedule
    if s.scheme == "fixed_window":
        lo, hi = (parse_month(m) for m in s.window)
        return (d.target >= lo) & (d.target <= hi)
    if s.scheme == "rolling_months":
        return d.target > int(cutoff) - int(s.months)
    return np.ones(len(d.target), dtype=bool)


def plan_contexts(d: ArmData):
    """No-fit enumeration of every scoring context, its backbone and its providers (row index arrays).

    A declared schedule may restrict the fitting labels (fixed_window / rolling_months), drop the providers, or serve
    named hindcast contexts with one shared backbone: that backbone excludes the union of every context's scored
    families (``train_excluded``) from its fitting labels and histories; each context's scored rows keep their own
    S_E for their histories, as in the annual design."""
    s = d.schedule
    blocks = scoring_blocks(d.horizon, s)
    shared = None
    if s.scoring_contexts:
        scored = np.zeros(len(d.target), dtype=bool)
        for E in blocks:
            scored |= (d.target >= E.target_lo) & (d.target <= E.target_hi)
        shared = row_families(d, np.flatnonzero(scored))
    plans = []
    for E in blocks:
        score = np.flatnonzero((d.target >= E.target_lo) & (d.target <= E.target_hi))
        S_E = row_families(d, score)
        eligible = (d.target <= E.cutoff) & (d.avail <= E.cutoff)
        if s.scheme != "expanding":
            eligible &= fitting_window(d, E.cutoff)
        train = np.flatnonzero(eligible & ~in_families(d, S_E if shared is None else shared))
        providers = []
        for P in provider_blocks(d.horizon, s):
            if P.target_lo > E.cutoff:
                continue
            pred = np.flatnonzero((d.target >= P.target_lo) & (d.target <= min(P.target_hi, E.cutoff))
                                  & (d.avail <= E.cutoff) & ~in_families(d, S_E))
            S_P = row_families(d, pred)
            excl = np.union1d(S_E, S_P)
            ptrain = np.flatnonzero((d.target <= P.cutoff) & (d.avail <= P.cutoff) & ~in_families(d, excl))
            providers.append({"block": P, "pred": pred, "train": ptrain, "excluded": excl, "S_P": S_P,
                              "excluded_eligible": int(((d.target <= P.cutoff) & (d.avail <= P.cutoff)).sum() - len(ptrain))})
        plan = {"block": E, "score": score, "S_E": S_E, "train": train, "providers": providers,
                "excluded_eligible": int(eligible.sum() - len(train))}
        if shared is not None:
            plan.update(train_excluded=shared, shared_fit=blocks[0].block_id)
        plans.append(plan)
    return plans


def keys_sha256(d: ArmData, rows):
    """Digest of the (admin_code, target month) keys of ``rows`` in label order."""
    rows = np.asarray(rows, dtype=np.int64)
    return array_digest(np.column_stack([d.admin[rows], d.target[rows]]))


def reused(p):
    """True for a hindcast context whose backbone is the shared fit of an earlier context (no new scalar fit)."""
    return p.get("shared_fit", p["block"].block_id) != p["block"].block_id


def plan_assertions(d: ArmData, plans):
    """Per-context fitting-label facts and checks of a declared schedule (written to the job log and receipts):
    fitting-target range and years, cutoff/window/rolling rules, excluded families, the hindcast's zero labels in the
    scored years, and the scored row-key digest. Any failed check raises."""
    s = d.schedule
    scored_years = sorted({y for p in plans for y in range(p["block"].target_lo // 12, p["block"].target_hi // 12 + 1)})
    out = {}
    for p in plans:
        E, tr, sc = p["block"], p["train"], p["score"]
        t = d.target[tr]
        excl = p.get("train_excluded", p["S_E"])
        checks = {"fitting_targets_le_cutoff": bool((t <= E.cutoff).all() and (d.avail[tr] <= E.cutoff).all()),
                  "no_excluded_family_in_fitting_labels": bool(not in_families(d, excl, tr).any()),
                  "no_scored_row_in_fitting_labels": bool(not np.intersect1d(tr, sc).size)}
        if s.scheme == "fixed_window":
            lo, hi = (parse_month(m) for m in s.window)
            checks["fitting_targets_in_window"] = bool(((t >= lo) & (t <= hi)).all())
        if s.scheme == "rolling_months":
            checks[f"fitting_targets_in_rolling_{s.months}m"] = bool(((t > E.cutoff - s.months) & (t <= E.cutoff)).all())
        if s.scoring_contexts:
            checks["no_fitting_label_in_scored_years"] = bool(not np.isin(t // 12, scored_years).any())
        rec = {"context": E.block_id, "role": E.role, "cutoff": label(E.cutoff), "scheme": s.scheme,
               "sample_weights": s.sample_weights, "calibration": s.calibration, "providers": len(p["providers"]),
               "train_rows": int(len(tr)), "train_copies": int((d.kind[tr] == "copy").sum()),
               "fit_target_min": label(int(t.min())) if len(tr) else None, "fit_target_max": label(int(t.max())) if len(tr) else None,
               "fit_targets_by_year": {int(y): int(n) for y, n in zip(*np.unique(t // 12, return_counts=True))},
               "train_excluded_families": int(len(excl)), "score_rows": int(len(sc)),
               "score_copies": int((d.kind[sc] == "copy").sum()), "score_keys_sha256": keys_sha256(d, sc),
               "train_keys_sha256": keys_sha256(d, tr), "shared_fit": p.get("shared_fit"), "checks": checks}
        if s.scoring_contexts:
            rec["scored_years"] = scored_years
        if not all(checks.values()):
            raise ValidityError(f"{E.block_id}: plan assertion failed {[k for k, v in checks.items() if not v]}")
        out[E.block_id] = rec
    return out


def fit_extra(d, train, pred, shared):
    t = d.target[train]
    return {"fit_target_min": label(int(t.min())) if len(t) else "", "fit_target_max": label(int(t.max())) if len(t) else "",
            "predicted_keys_sha256": keys_sha256(d, pred), "shared_fit": shared or ""}


def plan_summary(d: ArmData, plans):
    rows, extra = [], []
    for p in plans:
        E = p["block"]
        base = {"arm": d.arm, "horizon": d.horizon, "context": E.block_id, "role": E.role, **E.record()}
        rows.append({**base, "fit": "backbone", "fit_block": E.block_id, "fit_cutoff": label(E.cutoff),
                     "train_rows": len(p["train"]), "train_copies": int((d.kind[p["train"]] == "copy").sum()),
                     "excluded_families": len(p.get("train_excluded", p["S_E"])), "excluded_eligible_rows": p["excluded_eligible"],
                     "predicted_rows": len(p["score"]), "predicted_copies": int((d.kind[p["score"]] == "copy").sum()),
                     "scored_countries": int(pd.Series(d.labels["iso2"].to_numpy()[p["score"]]).nunique()),
                     "scored_families": len(p["S_E"]), "scalar_fits": 4 if len(p["score"]) and not reused(p) else 0})
        if d.schedule.declared:
            extra.append(fit_extra(d, p["train"], p["score"], p.get("shared_fit", "")))
        for pv in p["providers"]:
            P = pv["block"]
            rows.append({**base, "fit": "provider", "fit_block": P.block_id, "fit_cutoff": label(P.cutoff),
                         "train_rows": len(pv["train"]), "train_copies": int((d.kind[pv["train"]] == "copy").sum()),
                         "excluded_families": len(pv["excluded"]), "excluded_eligible_rows": pv["excluded_eligible"],
                         "predicted_rows": len(pv["pred"]), "predicted_copies": int((d.kind[pv["pred"]] == "copy").sum()),
                         "scored_countries": None, "scored_families": len(pv["S_P"]),
                         "scalar_fits": 4 if len(pv["pred"]) else 0})
            if d.schedule.declared:
                extra.append(fit_extra(d, pv["train"], pv["pred"], ""))
    out = pd.DataFrame(rows)
    if d.schedule.declared:      # extended schedule columns only for declared (refresh) schedules
        out = pd.concat([out, pd.DataFrame(extra)], axis=1)
    return out


# --------------------------------------------------------------------------- frozen-baseline equivalence (task 10-17)
#
# The local-IDP treatment must reuse the validity_augmented baseline's cohort exactly: arm rows, labels, memberships,
# history sources, calibration keys/weights, fitting keys/targets/weights and the original feature prefix (values and
# NaN mask). Both sides reduce to the same digests: ``equivalence_digests`` from the in-memory no-fit plan, and
# ``baseline_equivalence`` from the retained baseline artifacts. Compressed-container bytes are never compared.

EQUIVALENCE_KEYS = ("rows", "arm_rows_csv_sha256", "targets_sha256", "phase_sha256", "observations_sha256",
                    "memberships_sha256", "history_overlays_sha256", "calibration_keys_sha256", "schedule_sha256",
                    "fit_keys_sha256", "feature_prefix_order_sha256", "feature_prefix_X_sha256",
                    "feature_prefix_nan_mask_sha256")
# Task 10-27 (GOSIF-GPP v3 corrected input): a formal refit of the tuned arm with its frozen parameters on a corrected
# interim panel whose only change is the replaced GPP_mean/GPP_std columns (GPP_std is not a model input). The recipe's
# ``corrected_input`` block pins every input role (the replaced interim included), re-pins only the feature X / NaN-mask
# digests, and pins per-column digests of every unchanged feature column from the original formal no-fit build. The
# other eleven equivalence digests (labels, cohort, histories, memberships, schedule, fitting keys, order) must still
# equal the original formal run's ``baseline.equivalence``. Recipes without the block keep the original contract.
CORRECTED_INPUT_KIND = "gpp_input_replacement"
CORRECTED_INPUT_KEYS = ("kind", "data_version", "replaced_role", "inputs", "original_inputs", "changed_columns", "corrected",
                        "unchanged_columns", "original_run", "relation", "report")
REPORT_ROLE = "report_region_mapping"      # report-only region map (task 10-27 R7); never a model input
GPP_INPUT_FEATURES = tuple([f"GPP_mean__{k}_at_origin" for k in ("value", "ma3", "ma6", "ma12", "sd12")]
                           + [f"GPP_mean__hist_same_month_z{k}_at_origin" for k in ("", "_ma3", "_ma6", "_ma12")]
                           + [f"GPP_mean__vegetation_stress__{k}_at_origin" for k in ("share12", "months_since", "longest_run12", "any12")])
CORRECTED_REPINNED = ("feature_prefix_X_sha256", "feature_prefix_nan_mask_sha256")
CORRECTED_PRESERVED = tuple(k for k in EQUIVALENCE_KEYS if k not in CORRECTED_REPINNED)
POOL_KEY_COLUMNS = ("row", "admin_code", "target_ord", "label_kind", "source_family", "provider_block", "provider_cutoff", "weight")
FIT_KEY_COLUMNS = ("context", "fit_block", "role", "cutoff", "train_rows", "predicted_rows", "excluded_families",
                   "excluded_families_sha256", "train_keys_sha256", "y_sha256", "w_sha256")


def text_sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def frame_sha256(frame):
    return text_sha256(frame.to_csv(index=False, float_format="%.17g"))


def csv_text_sha256(frame, drop=()):
    """Digest of a frame after a string round trip (so a retained CSV and an in-memory frame compare by text)."""
    import io
    text = frame.to_csv(index=False) if isinstance(frame, pd.DataFrame) else open(frame).read()
    f = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    return text_sha256(f.drop(columns=list(drop)).to_csv(index=False))


def arm_rows_frame(d: ArmData):
    """The ``contexts/arm_rows.csv.gz`` table that ``run_contexts`` writes."""
    return pd.DataFrame({"row": np.arange(len(d.admin)), "admin_code": d.admin, "target_ord": d.target, "label_kind": d.kind,
                         "source_family": d.family, "source_available_ord": d.avail})


def membership_arrays(plans):
    """The ``memberships.npz`` arrays ``run_contexts`` saves, enumerated without fitting."""
    m = {}
    for p in plans:
        E = p["block"]
        for pv in p["providers"]:
            if len(pv["pred"]):
                fid = f"{E.block_id}|{pv['block'].block_id}"
                m[f"{fid}|train"], m[f"{fid}|pred"] = pv["train"].astype(np.int32), pv["pred"].astype(np.int32)
        m[f"{E.block_id}|backbone|train"], m[f"{E.block_id}|score"] = p["train"].astype(np.int32), p["score"].astype(np.int32)
    for p in plans:
        m[f"{p['block'].block_id}|excluded_families"] = np.asarray(p["S_E"], np.int64)
        for pv in p["providers"]:
            m[f"{p['block'].block_id}|{pv['block'].block_id}|excluded_families"] = np.asarray(pv["excluded"], np.int64)
        if "train_excluded" in p:      # shared hindcast backbone: the union it excludes (absent otherwise)
            m[f"{p['block'].block_id}|backbone|excluded_families"] = np.asarray(p["train_excluded"], np.int64)
    return m


def history_overlay_arrays(d: ArmData, plans):
    """The ``gcs-only/history_overlays.npz`` source months/families of every fit, without fitting."""
    out = {}

    def put(prefix, rows, excluded):
        if d.obs_aliased:      # task 10-28: the selected events' aliases are part of the saved dependency ledger
            _, src, fam, ali = vf.history_block(d.admin[rows], d.target[rows], d.horizon, d.obs, excluded, return_alias=True)
            out[f"{prefix}_alias"] = ali
        else:
            _, src, fam = vf.history_block(d.admin[rows], d.target[rows], d.horizon, d.obs, excluded)
        out[f"{prefix}_src"], out[f"{prefix}_fam"] = src, fam

    for p in plans:
        E = p["block"]
        for pv in p["providers"]:
            if len(pv["pred"]):
                fid = f"{E.block_id}|{pv['block'].block_id}"
                put(f"{fid}|train", pv["train"], pv["excluded"])
                put(f"{fid}|pred", pv["pred"], pv["excluded"])
        put(f"{E.block_id}|backbone|train", p["train"], p.get("train_excluded", p["S_E"]))
        put(f"{E.block_id}|score", p["score"], p["S_E"])
    return out


def calibration_keys(d: ArmData, plans):
    """{context: calibration-pool key/provider/cutoff/weight frame} (the saved pool without its p_q columns)."""
    out = {}
    for p in plans:
        E = p["block"]
        parts = [pd.DataFrame({"row": pv["pred"], "provider_block": pv["block"].block_id, "provider_cutoff": pv["block"].cutoff})
                 for pv in p["providers"] if len(pv["pred"])]
        f = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["row", "provider_block", "provider_cutoff"])
        rows = f["row"].to_numpy(np.int64)
        f["admin_code"], f["target_ord"], f["label_kind"], f["source_family"] = d.admin[rows], d.target[rows], d.kind[rows], d.family[rows]
        f["weight"] = decay(d.target[rows], E.cutoff) if len(rows) else np.zeros(0)
        out[E.block_id] = f[list(POOL_KEY_COLUMNS)]
    return out


def fit_keys(d: ArmData, plans):
    """Per-fit keys/targets/weights/exclusions in ``fit_ledger.csv`` order (fitting rows, not fitted values)."""
    recs = []

    def rec(context, fit_block, role, train, pred, excluded, cutoff):
        recs.append({"context": context, "fit_block": fit_block, "role": role, "cutoff": label(cutoff),
                     "train_rows": int(len(train)), "predicted_rows": int(len(pred)), "excluded_families": int(len(excluded)),
                     "excluded_families_sha256": array_digest(np.asarray(excluded, np.int64)),
                     "train_keys_sha256": array_digest(np.column_stack([d.admin[train], d.target[train]])),
                     "y_sha256": array_digest(d.Y[train]), "w_sha256": array_digest(fit_weights(d, train, cutoff))})

    for p in plans:
        E = p["block"]
        for pv in p["providers"]:
            if len(pv["pred"]):
                rec(E.block_id, pv["block"].block_id, "provider", pv["train"], pv["pred"], pv["excluded"], pv["block"].cutoff)
        if not reused(p):      # a shared hindcast backbone is one fit, recorded at its first context
            rec(E.block_id, E.block_id, "backbone", p["train"], p["score"], p.get("train_excluded", p["S_E"]), E.cutoff)
    return pd.DataFrame(recs, columns=list(FIT_KEY_COLUMNS))


def equivalence_digests(d: ArmData, plans, n_prefix):
    """No-fit cohort/key/prefix identities of one arm/H (see EQUIVALENCE_KEYS)."""
    hist = history_overlay_arrays(d, plans)
    return {"rows": int(len(d.admin)),
            "arm_rows_csv_sha256": text_sha256(arm_rows_frame(d).to_csv(index=False)),
            "targets_sha256": array_digest(d.Y), "phase_sha256": array_digest(d.phase),
            "observations_sha256": frame_sha256(d.obs[["admin_code", "month_ord", "reported_phase", "family"]]),
            "memberships_sha256": digest({k: array_digest(v) for k, v in membership_arrays(plans).items()}),
            "history_overlays_sha256": digest({k: array_digest(v) for k, v in hist.items()}),
            "calibration_keys_sha256": digest({k: frame_sha256(f) for k, f in calibration_keys(d, plans).items()}),
            "schedule_sha256": csv_text_sha256(plan_summary(d, plans), drop=("arm",)),
            "fit_keys_sha256": frame_sha256(fit_keys(d, plans)),
            "feature_prefix_order_sha256": vf.list_sha256(d.order[:n_prefix]),
            "feature_prefix_X_sha256": array_digest(d.X[:, :n_prefix]),
            "feature_prefix_nan_mask_sha256": array_digest(np.isnan(d.X[:, :n_prefix]))}


def baseline_equivalence(trial_dir, horizon):
    """The same digests from a retained baseline trial directory (contexts/, dataset/, gcs-only/)."""
    import gzip
    h = int(horizon)
    path = lambda *p: os.path.join(trial_dir, *p)
    labels = pd.read_csv(path("dataset", "labels.csv.gz"), dtype={f"{q}_str": str for q in TARGETS}, keep_default_na=False,
                         na_values=[""], usecols=[*[f"{q}_str" for q in TARGETS], "phase_truth"])
    Y = np.column_stack([np.array([float(s) for s in labels[f"{q}_str"]], dtype=np.float64) for q in TARGETS])
    obs = pd.read_csv(path("dataset", "history_observations.csv.gz"))
    members = dict(np.load(path("contexts", "memberships.npz")))
    hist = dict(np.load(path("gcs-only", "history_overlays.npz")))
    pools = {}
    for name in sorted(os.listdir(path("contexts"))):
        if name.startswith("calibration_pool_") and name.endswith(".csv.gz"):
            f = pd.read_csv(path("contexts", name), float_precision="round_trip")
            pools[name[len("calibration_pool_"):-len(".csv.gz")]] = f[list(POOL_KEY_COLUMNS)]
    ledger = pd.read_csv(path("contexts", "fit_ledger.csv"))
    order = pd.read_csv(path("dataset", f"feature_order_h{h:02d}.csv"))["name"].tolist()
    X = np.load(path("gcs-only", "dataset", f"base_X_h{h:02d}.npy"))
    return {"rows": int(len(labels)),
            "arm_rows_csv_sha256": hashlib.sha256(gzip.open(path("contexts", "arm_rows.csv.gz")).read()).hexdigest(),
            "targets_sha256": array_digest(Y), "phase_sha256": array_digest(labels["phase_truth"].to_numpy(np.int64)),
            "observations_sha256": frame_sha256(obs[["admin_code", "month_ord", "reported_phase", "family"]]),
            "memberships_sha256": digest({k: array_digest(v) for k, v in members.items()}),
            "history_overlays_sha256": digest({k: array_digest(v) for k, v in hist.items()}),
            "calibration_keys_sha256": digest({k: frame_sha256(f) for k, f in pools.items()}),
            "schedule_sha256": csv_text_sha256(path("contexts", "schedule.csv"), drop=("arm",)),
            "fit_keys_sha256": frame_sha256(ledger.rename(columns={"block": "fit_block"})[list(FIT_KEY_COLUMNS)]),
            "feature_prefix_order_sha256": vf.list_sha256(order),
            "feature_prefix_X_sha256": array_digest(X),
            "feature_prefix_nan_mask_sha256": array_digest(np.isnan(X))}


def check_equivalence(got, want):
    """Names of differing equivalence keys (empty = the treatment reuses the baseline cohort exactly)."""
    missing = [k for k in EQUIVALENCE_KEYS if k not in (want or {})]
    if missing:
        raise ValidityError(f"baseline equivalence reference lacks {missing}")
    return [k for k in EQUIVALENCE_KEYS if got.get(k) != want[k]]


# --------------------------------------------------------------------------- paired baseline gate (task 10-20, Gate A)
#
# The aggregated-ACLED arm must reuse the retained uncalibrated production run's backbone contract exactly. Both sides
# reduce to the same per-item digests: ``paired_digests`` from the in-memory no-fit plan and ``paired_reference`` from
# the retained baseline trial directory (never from the new build). Only backbone evidence is compared: provider fits
# and B2 calibration keys are absent from the new arm by design. Feature columns are compared by exact name after
# removing the 14 compact conflict columns (old side) and the 114 aggregated-ACLED columns (new side); paired NaNs are
# equal. Gate B (``baseline.kind = self_consistency``) separately pins the full new build.

PAIRED_SCALARS = ("rows", "arm_rows_csv_sha256", "targets_sha256", "phase_sha256", "observations_sha256",
                  "backbone_schedule_sha256", "backbone_fit_keys_sha256", "non_acled_order_sha256", "non_acled_nan_mask_sha256")
PAIRED_ITEMS = ("backbone_memberships", "backbone_history_overlays", "backbone_history_values", "scored", "non_acled_columns")


def backbone_key(key):
    """Memberships/overlays of the backbone and scored rows (provider entries name a ``_prov_`` block second)."""
    return "_prov_" not in key.split("|")[1]


def canonical(a):
    """Contiguous float64 copy with every NaN as the same quiet NaN (paired NaNs compare equal by digest)."""
    a = np.array(a, dtype=np.float64, copy=True)
    a[np.isnan(a)] = np.nan
    return a


def backbone_history_values(admin, target, horizon, obs, members):
    """History values each backbone fit and scored set materializes (the same exclusions as the job)."""
    out = {}
    for key in sorted(k for k in members if k.endswith("|score")):
        ctx = key.split("|")[0]
        excluded = members[f"{ctx}|excluded_families"]
        train_excluded = members.get(f"{ctx}|backbone|excluded_families", excluded)
        for name, rows, excl in (("backbone|train", members[f"{ctx}|backbone|train"], train_excluded), ("score", members[key], excluded)):
            rows = np.asarray(rows, dtype=np.int64)
            block, _, _ = vf.history_block(admin[rows], target[rows], horizon, obs, excl)
            out[f"{ctx}|{name}"] = array_digest(canonical(block))
    return out


def scored_digest(admin, target, phase, Y):
    return digest([array_digest(np.column_stack([np.asarray(admin, np.int64), np.asarray(target, np.int64)])),
                   array_digest(np.asarray(phase, np.int64)), array_digest(np.asarray(Y, np.float64))])


def backbone_schedule_sha256(schedule_csv_text):
    """Backbone rows of a schedule CSV without ``arm``. Numeric cells are written canonically: a column that also holds
    provider rows' blanks (``scored_countries``) is float text (``12.0``) in a provider schedule but integer text in a
    provider-free one."""
    import io
    f = pd.read_csv(io.StringIO(schedule_csv_text), dtype=str, keep_default_na=False)
    f = f.loc[f["fit"] == "backbone"].drop(columns=["arm"]).reset_index(drop=True)
    for c in f.columns:
        num = pd.to_numeric(f[c], errors="coerce")
        if len(f) and num.notna().all():
            f[c] = [format(float(v), ".17g") for v in num]
    return text_sha256(f.to_csv(index=False))


def non_acled_digests(X, order, names):
    idx = [order.index(c) for c in names]
    return ({c: array_digest(canonical(X[:, j])) for c, j in zip(names, idx)},
            array_digest(np.isnan(np.asarray(X)[:, idx])))


def paired_digests(d: ArmData, plans):
    """Gate A digests of the new arm's no-fit build (backbone only; named non-ACLED columns)."""
    members = {k: v for k, v in membership_arrays(plans).items() if backbone_key(k)}
    overlays = {k: v for k, v in history_overlay_arrays(d, plans).items() if backbone_key(k)}
    fk = fit_keys(d, plans)
    names = [c for c in d.order if c not in vf.ACLED_AGG_FEATURES]
    cols, mask = non_acled_digests(d.X, d.order, names)
    return {"rows": int(len(d.admin)), "arm_rows_csv_sha256": text_sha256(arm_rows_frame(d).to_csv(index=False)),
            "targets_sha256": array_digest(d.Y), "phase_sha256": array_digest(d.phase),
            "observations_sha256": frame_sha256(d.obs[["admin_code", "month_ord", "reported_phase", "family"]]),
            "backbone_schedule_sha256": backbone_schedule_sha256(plan_summary(d, plans).to_csv(index=False)),
            "backbone_fit_keys_sha256": frame_sha256(fk.loc[fk["role"] == "backbone"]),
            "non_acled_order_sha256": vf.list_sha256(names), "non_acled_nan_mask_sha256": mask,
            "backbone_memberships": {k: array_digest(v) for k, v in members.items()},
            "backbone_history_overlays": {k: array_digest(v) for k, v in overlays.items()},
            "backbone_history_values": backbone_history_values(d.admin, d.target, d.horizon, d.obs, members),
            "scored": {p["block"].block_id: scored_digest(d.admin[p["score"]], d.target[p["score"]], d.phase[p["score"]], d.Y[p["score"]])
                       for p in plans},
            "non_acled_columns": cols}


def paired_reference(trial_dir, horizon, run_id):
    """Gate A reference from a retained production trial directory (dataset/, contexts/, gcs-only/, predictions.csv.gz,
    trial.json) of ``ACLED_BASELINE_ARM`` at ``horizon``: the same digests as ``paired_digests``, the non-ACLED feature
    order, every training-input identity and the hashes of the evidence it read. Never reads a new build."""
    import gzip
    from research_cloud.training.common import sha256_file
    h = int(horizon)
    path = lambda *p: os.path.join(trial_dir, *p)
    with open(path("trial.json")) as f:
        record = json.load(f)
    cfg = record.get("config") or {}
    if cfg.get("arm") != ACLED_BASELINE_ARM or int(cfg.get("horizon", -1)) != h:
        raise ValidityError(f"{trial_dir} is not the {ACLED_BASELINE_ARM} H{h} trial")
    if record.get("status") != "succeeded" or record.get("publication_status") != "complete":
        raise ValidityError(f"{trial_dir} is not a succeeded, completely published trial")
    if not run_id or record.get("mlflow_run_id") != run_id:      # the retained record's own published run identity
        raise ValidityError(f"trial mlflow_run_id {record.get('mlflow_run_id')!r} differs from the requested {run_id!r}")
    files = {"trial.json": path("trial.json"), "labels": path("dataset", "labels.csv.gz"),
             "observations": path("dataset", "history_observations.csv.gz"), "order": path("dataset", f"feature_order_h{h:02d}.csv"),
             "arm_rows": path("contexts", "arm_rows.csv.gz"), "memberships": path("contexts", "memberships.npz"),
             "fit_ledger": path("contexts", "fit_ledger.csv"), "schedule": path("contexts", "schedule.csv"),
             "history_overlays": path("gcs-only", "history_overlays.npz"), "base_X": path("gcs-only", "dataset", f"base_X_h{h:02d}.npy"),
             "predictions": path("predictions.csv.gz")}
    labels = pd.read_csv(files["labels"], dtype={f"{q}_str": str for q in TARGETS}, keep_default_na=False, na_values=[""],
                         usecols=[*[f"{q}_str" for q in TARGETS], "phase_truth"])
    Y = np.column_stack([np.array([float(s) for s in labels[f"{q}_str"]], dtype=np.float64) for q in TARGETS])
    obs = pd.read_csv(files["observations"])
    with gzip.open(files["arm_rows"]) as f:
        arm_rows_text = f.read()
    arm_rows = pd.read_csv(files["arm_rows"])
    members = {k: v for k, v in dict(np.load(files["memberships"])).items() if backbone_key(k)}
    overlays = {k: v for k, v in dict(np.load(files["history_overlays"])).items() if backbone_key(k)}
    ledger = pd.read_csv(files["fit_ledger"]).rename(columns={"block": "fit_block"})
    with open(files["schedule"]) as f:
        schedule_text = f.read()
    order = pd.read_csv(files["order"])["name"].tolist()
    missing = [c for c in vf.OLD_ACLED_FEATURES if c not in order]
    if missing or set(order) & set(vf.ACLED_AGG_FEATURES):
        raise ValidityError(f"baseline order is not the compact-conflict order (missing {missing})")
    names = [c for c in order if c not in vf.OLD_ACLED_FEATURES]
    X = np.load(files["base_X"])
    if X.shape != (len(labels), len(order)) or len(arm_rows) != len(labels):
        raise ValidityError("baseline matrix/labels/arm rows disagree in shape")
    cols, mask = non_acled_digests(X, order, names)
    pred = pd.read_csv(files["predictions"], float_precision="round_trip")
    scored = {c: scored_digest(f["admin_code"], f["target_ord"], f["phase_truth"], f[[f"{q}_truth" for q in TARGETS]].to_numpy())
              for c, f in pred.groupby("context", sort=True)}
    admin, target = arm_rows["admin_code"].to_numpy(np.int64), arm_rows["target_ord"].to_numpy(np.int64)
    digests = {"rows": int(len(labels)), "arm_rows_csv_sha256": hashlib.sha256(arm_rows_text).hexdigest(),
               "targets_sha256": array_digest(Y), "phase_sha256": array_digest(labels["phase_truth"].to_numpy(np.int64)),
               "observations_sha256": frame_sha256(obs[["admin_code", "month_ord", "reported_phase", "family"]]),
               "backbone_schedule_sha256": backbone_schedule_sha256(schedule_text),
               "backbone_fit_keys_sha256": frame_sha256(ledger.loc[ledger["role"] == "backbone", list(FIT_KEY_COLUMNS)]),
               "non_acled_order_sha256": vf.list_sha256(names), "non_acled_nan_mask_sha256": mask,
               "backbone_memberships": {k: array_digest(v) for k, v in members.items()},
               "backbone_history_overlays": {k: array_digest(v) for k, v in overlays.items()},
               "backbone_history_values": backbone_history_values(admin, target, h, obs, members),
               "scored": scored, "non_acled_columns": cols}
    inputs = ((record.get("input_manifest") or {}).get("content") or {}).get("files") or {}
    return {"kind": "acled_baseline_reference", "horizon": h,
            "baseline": {"arm": ACLED_BASELINE_ARM, "run_id": run_id, "vertex_job": (record.get("runtime") or {}).get("vertex", {}).get("CLOUD_ML_JOB_ID"),
                         "prediction_columns": [*[f"{q}_star_uncal" for q in TARGETS], "phase_uncal"]},
            "evidence_sha256": {k: sha256_file(p) for k, p in files.items()},
            "training_inputs": {r: e["sha256"] for r, e in sorted(inputs.items())},
            "removed_features": list(vf.OLD_ACLED_FEATURES), "non_acled_order": names,
            "predictions": {"rows": int(len(pred)), "contexts": sorted(scored)}, "digests": digests}


def paired_gate(d: ArmData, plans, reference, manifest):
    """Gate A receipt: every check with its mismatch count; ``passed`` only if all pass. Also checks the new arm's own
    structure (old 14 absent, the 114 block and local-IDP suffix in place, no providers or B2 inputs) and that every
    training input except the interim keeps its baseline identity."""
    n = len(d.order)
    checks = {}

    def check(name, bad, detail=None):
        checks[name] = {"passed": not bad, "mismatches": int(bad), **({"detail": detail} if detail else {})}

    check("reference_kind_and_horizon", int(reference.get("kind") != "acled_baseline_reference" or reference.get("horizon") != d.horizon
                                            or (reference.get("baseline") or {}).get("arm") != ACLED_BASELINE_ARM))
    check("width", int(n != vf.expected_features(d.horizon, idp_local=True, acled_agg=True)), [n])
    check("old_conflict_columns_absent", len(set(vf.OLD_ACLED_FEATURES) & set(d.order)))
    check("acled_block_in_order", int(d.order[n - 117:n - 3] != list(vf.ACLED_AGG_FEATURES)))
    check("local_idp_suffix", int(d.order[-3:] != list(vf.IDP_LOCAL_FEATURES)))
    check("no_b2_core_inputs", len(d.core_idx))
    check("no_providers", sum(len(p["providers"]) for p in plans))
    names = [c for c in d.order if c not in vf.ACLED_AGG_FEATURES]
    want_names = reference.get("non_acled_order") or []
    check("non_acled_order", sum(a != b for a, b in zip(names, want_names)) + abs(len(names) - len(want_names)),
          [f"{i}: {a} != {b}" for i, (a, b) in enumerate(zip(names, want_names)) if a != b][:5])
    files = (manifest or {}).get("files") or {}
    roles = {r: e.get("sha256") for r, e in files.items() if r not in COMPARISON_ROLES}
    base = reference.get("training_inputs") or {}
    differ = sorted(r for r in set(roles) | set(base) if r != "interim" and roles.get(r) != base.get(r))
    check("training_inputs_except_interim", len(differ), differ)
    check("interim_replaced", int("interim" not in roles or roles.get("interim") == base.get("interim")))
    got, want = paired_digests(d, plans), reference.get("digests") or {}
    for k in PAIRED_SCALARS:
        check(k, int(k not in want or got[k] != want[k]))
    for k in PAIRED_ITEMS:
        a, b = got[k], want.get(k) or {}
        bad = sorted(x for x in set(a) | set(b) if a.get(x) != b.get(x))
        check(k, len(bad) + (not b), bad[:10])
    failed = [k for k, v in checks.items() if not v["passed"]]
    return {"gate": "paired_baseline", "arm": d.arm, "horizon": d.horizon, "baseline": reference.get("baseline"),
            "reference_evidence_sha256": reference.get("evidence_sha256"), "checks": checks, "failed": failed, "passed": not failed}


# --------------------------------------------------------------------------- history-materialized matrices


def materialize(d: ArmData, rows, excluded, with_alias=False):
    """Rows of the base matrix with history rebuilt after removing ``excluded`` families; returns (X, sources,
    families) and refuses any excluded family among the selected history sources. Every history group (own block and
    any stacked longer-horizon block) is rebuilt with its own horizon's bound and the same exclusions; sources and
    families of the groups are returned side by side (own group first). With aliased observations (task 10-28) an
    excluded alias is refused too, and ``with_alias`` appends the selected events' aliases as a fourth value."""
    X = np.array(d.X[rows], dtype=np.float64, copy=True)
    srcs, fams, alis = [], [], []
    for idx, horizon in d.hist_groups:
        if d.obs_aliased:
            block, src, fam, ali = vf.history_block(d.admin[rows], d.target[rows], horizon, d.obs, excluded, return_alias=True)
            if len(excluded) and np.isin(ali[ali >= 0], excluded).any():
                raise ValidityError("an excluded alias family supplies a history value")
            alis.append(ali)
        else:
            block, src, fam = vf.history_block(d.admin[rows], d.target[rows], horizon, d.obs, excluded)
            alis.append(np.full(src.shape, -1, np.int64))
        used = fam[fam >= 0]
        if len(excluded) and np.isin(used, excluded).any():
            raise ValidityError("an excluded family supplies a history value")
        X[:, idx] = block
        srcs.append(src)
        fams.append(fam)
    if len(srcs) == 1:
        out = (X, srcs[0], fams[0], alis[0])
    else:
        out = (X, np.hstack(srcs), np.hstack(fams), np.hstack(alis))
    return out if with_alias else out[:3]


def stack_features(horizons, h, invariant=None):
    """Own-horizon matrix followed by each stacked horizon's origin-dependent block (names suffixed ``__hKK``).

    ``horizons`` maps horizon -> {"X", "order"} built for the same label rows (identical row order). Returns
    (X, order, hist_groups, blocks) where blocks = [(k, source names, column slice)]."""
    own = horizons[h]
    X_parts, order, blocks = [own["X"]], list(own["order"]), []
    groups = [(vf.history_columns(order), h)]
    for k in STACK[h]:
        src = horizons[k]
        if src["X"].shape[0] != own["X"].shape[0]:
            raise ValidityError(f"H{k} block rows differ from H{h}")
        inv = invariant if invariant is not None else vf.invariant_feature_names(src["order"])
        names = [c for c in src["order"] if c not in inv]
        idx = [src["order"].index(c) for c in names]
        start = len(order)
        order += [f"{c}__h{k:02d}" for c in names]
        X_parts.append(src["X"][:, idx])
        groups.append(([start + names.index(c) for c in vf.HISTORY_FEATURES], k))
        blocks.append((k, names, slice(start, len(order))))
    if len(set(order)) != len(order):
        raise ValidityError("stacked feature names are not unique")
    return np.ascontiguousarray(np.hstack(X_parts)), order, groups, blocks


def xgb_params(q, quartet=None):
    """Estimator settings of target ``q``: the fixed QUARTET, or a resolved tuned quartet (``hpt_quartet``)."""
    return {**(QUARTET if quartet is None else quartet)[q], **XGB_FIXED}


def fit_quartet(X, Y, w, quartet=None):
    import xgboost as xgb
    boosters, payloads, records = {}, {}, {}
    for k, q in enumerate(TARGETS):
        t0 = time.time()
        model = xgb.XGBRegressor(**xgb_params(q, quartet))
        model.fit(X, Y[:, k], sample_weight=w, verbose=False)
        b = model.get_booster()
        raw = bytes(b.save_raw("ubj"))
        boosters[q], payloads[q] = b, raw
        records[q] = {"booster_sha256": hashlib.sha256(raw).hexdigest(), "rounds": b.num_boosted_rounds(),
                      "seconds": round(time.time() - t0, 2), "params": xgb_params(q, quartet)}
    return boosters, payloads, records


def predict_quartet(boosters, X):
    import xgboost as xgb
    dm = xgb.DMatrix(np.ascontiguousarray(X, dtype=np.float64), missing=np.nan, nthread=N_THREADS)
    out = []
    for q in TARGETS:
        boosters[q].set_param({"nthread": N_THREADS})
        out.append(np.asarray(boosters[q].predict(dm), dtype=np.float64))
    P = np.column_stack(out)
    if not np.isfinite(P).all():
        raise ValidityError("nonfinite backbone prediction")
    return P


def run_fit(d: ArmData, role, block: Block, train, pred, excluded, cutoff, pred_excluded=None, quartet=None):
    """Fit one quartet at ``cutoff`` on ``train`` (histories excluding ``excluded``) and predict ``pred`` (histories
    excluding ``pred_excluded``, default ``excluded``; a shared hindcast backbone excludes the union of the scored
    families from its fitting rows while each context's scored rows keep their own S_E). ``quartet`` (task 10-21)
    replaces the fixed QUARTET settings of every target fit."""
    if pred_excluded is None:
        pred_excluded = excluded
    if len(train) == 0:
        raise ValidityError(f"{block.block_id}: empty fitting pool (no invented labels)")
    if (d.target[train] > cutoff).any() or (d.avail[train] > cutoff).any():
        raise ValidityError(f"{block.block_id}: a fitting label or its source is after the cutoff")
    if len(excluded) and in_families(d, excluded, train).any():
        raise ValidityError(f"{block.block_id}: an excluded family is in the fitting labels")
    if np.intersect1d(train, pred).size:
        raise ValidityError(f"{block.block_id}: a predicted row is in its own fitting pool")
    Xt, tsrc, tfam, tali = materialize(d, train, excluded, with_alias=True)
    Xp, psrc, pfam, pali = materialize(d, pred, pred_excluded, with_alias=True)
    w = fit_weights(d, train, cutoff)
    boosters, payloads, recs = fit_quartet(Xt, d.Y[train], w, quartet)
    P = predict_quartet(boosters, Xp) if len(pred) else np.zeros((0, 4))
    record = {"role": role, "block": block.record(), "cutoff": label(cutoff), "train_rows": int(len(train)),
              "train_copies": int((d.kind[train] == "copy").sum()), "train_families": int(len(np.unique(d.family[train]))),
              "sum_weight": float(w.sum()), "n_eff": n_eff(w), "max_train_target": label(int(d.target[train].max())),
              "max_train_source": label(int(d.avail[train].max())), "predicted_rows": int(len(pred)),
              "excluded_families": int(len(excluded)), "excluded_families_sha256": array_digest(np.asarray(excluded, np.int64)),
              "train_keys_sha256": array_digest(np.column_stack([d.admin[train], d.target[train]])),
              "X_train_sha256": array_digest(Xt), "y_sha256": array_digest(d.Y[train]), "w_sha256": array_digest(w),
              "history_sources_excluded_hits": 0, "targets": recs}
    if d.schedule.declared:
        record.update(min_train_target=label(int(d.target[train].min())), sample_weights=d.schedule.sample_weights,
                      scheme=d.schedule.scheme)
    history = {"train_src": tsrc, "train_fam": tfam, "pred_src": psrc, "pred_fam": pfam}
    if d.obs_aliased:      # task 10-28: the same alias evidence as the no-fit history_overlay_arrays
        history.update(train_alias=tali, pred_alias=pali)
    return {"record": record, "boosters": boosters, "payloads": payloads, "P": P, "Xp": Xp, "history": history}


def predict_rows(d: ArmData, boosters, rows, excluded):
    """Raw quartet of an already fitted backbone on ``rows`` (histories excluding ``excluded``) without refitting."""
    Xp, src, fam = materialize(d, rows, excluded)
    return (predict_quartet(boosters, Xp) if len(rows) else np.zeros((0, 4))), Xp, src, fam


# --------------------------------------------------------------------------- B2 calibration (design section 7)


def fit_b2(P, Z, Y, target, cutoff):
    cr = ae("correction")
    if len(P) == 0:
        return {"status": "identity_no_support", "transform": None, "beta": np.zeros((4, 8)), "rows": 0}
    if (np.asarray(target) > cutoff).any():
        raise ValidityError("calibration row after the context cutoff")
    w = decay(target, cutoff)
    T = cr.Transform.fit(P, Z, w)
    V = T.design(P, Z)
    stats = cr.Stats.from_rows(V, Y - P, w / w.sum())
    sol = cr.solve_b2(stats, T.active(), RIDGE, SOLVER_TOL)
    if not np.isfinite(sol["beta"]).all():
        raise ValidityError("invalid ridge result")
    return {"status": "calibrated_b2", "transform": T, "beta": sol["beta"], "objective": sol["objective"], "rows": int(len(P)),
            "sum_weight": float(w.sum()), "n_eff": n_eff(w)}


def apply_b2(cal, P, Z):
    cr = ae("correction")
    if cal["status"] == "identity_no_support":
        if not np.isfinite(P).all():
            raise ValidityError("nonfinite raw prediction")
        return P.copy(), np.zeros_like(P)
    V = cal["transform"].design(P, Z)
    corrected = cr.correct(P, V, cal["beta"])
    return corrected, corrected - P


def b2_record(cal, core=CORE_INPUTS):
    return {"status": cal["status"], "rows": cal["rows"], "beta": np.asarray(cal["beta"]).tolist(),
            "transform": None if cal["transform"] is None else cal["transform"].record(),
            "objective": cal.get("objective"), "sum_weight": cal.get("sum_weight"), "n_eff": cal.get("n_eff"),
            "slots": list(ae("correction").SLOT_NAMES), "penalty": RIDGE, "core_inputs": list(core)}


# --------------------------------------------------------------------------- metrics (existing semantics)


LEGACY_LEAVES = ("binary.accuracy", "binary.precision", "binary.recall", "binary.f1", "binary.f2",
                 "four_class.accuracy", "four_class.macro_f1", "share_phase3plus_r2", "n_rows")


def metric_block(truth_phase, pred_phase, Y, star):
    """Existing metric semantics (ipcch_alphaearth.metrics). Undefined values are None with an explicit reason in
    ``na_reasons`` (zero denominators, absent four-class classes, constant truth / n < 2 for R2)."""
    m = ae("metrics")
    out = {"n_rows": int(len(truth_phase)), "na_reasons": {}}
    if not len(truth_phase):
        out["na_reasons"]["all"] = "no scored rows"
        return out
    panel = m.metric_panel(truth_phase, pred_phase)
    b, f = panel["binary"], panel["four_class"]
    out.update({f"binary.{k}": b[k] for k in ("accuracy", "precision", "recall", "f1", "f2")})
    out["binary.counts"] = b["counts"]
    out["na_reasons"].update({f"binary.{k}": v for k, v in b["na_reasons"].items()})
    out.update({"four_class.accuracy": f["accuracy"], "four_class.macro_f1": f["macro_f1"],
                "four_class.confusion": f["confusion_rows_truth_cols_pred"]})
    out["na_reasons"].update({f"four_class.{k}": v for k, v in f["na_reasons"].items()})
    out["ordinal_phase_mae"] = float(np.mean(np.abs(np.asarray(truth_phase) - np.asarray(pred_phase))))
    for k, q in enumerate(TARGETS):
        err = star[:, k] - Y[:, k]
        out[f"{q}_mae"], out[f"{q}_rmse"] = float(np.mean(np.abs(err))), float(np.sqrt(np.mean(err ** 2)))
        out[f"{q}_r2"], why = m.r_squared(Y[:, k], star[:, k])
        if why:
            out["na_reasons"][f"{q}_r2"] = why
    out["share_phase3plus_r2"] = out["q3_r2"]
    if "q3_r2" in out["na_reasons"]:
        out["na_reasons"]["share_phase3plus_r2"] = out["na_reasons"]["q3_r2"]
    undefined = sorted(k for k, v in out.items() if v is None)
    missing = [k for k in undefined if k not in out["na_reasons"]]
    if missing:
        raise ValidityError(f"undefined metrics without a reason: {missing}")
    return out


def mlflow_metrics(period_blocks):
    """Legacy dashboard keys ``<period_role>.all_scored.<metric>`` (primary = main, holdout = supplement) plus the
    extended q-share metrics; undefined values are omitted (listed in metrics.json)."""
    out = {}
    for role, block in period_blocks.items():
        for k, v in block.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v is not None and np.isfinite(v):
                out[f"{role}.all_scored.{k}"] = float(v)
    return out


# --------------------------------------------------------------------------- the job


def check_config(config, horizon, arm):
    if "ch_correction" in config and (arm != HPT_ARM or config.get("mode") != "formal"):
        raise ValidityError(f"ch_correction (task 10-28) is defined only for formal {HPT_ARM} recipes")
    if arm == HPT_ARM:      # task 10-21: its own mode-specific contract (tuning search/reference or formal refit)
        return check_hpt_config(config, horizon)
    if config.get("fixed") != fixed_settings(arm):
        raise ValidityError("recipe fixed settings differ from the frozen validity quartet/B2 contract" if arm not in ACLED_ARMS
                            else "recipe fixed settings differ from the frozen validity quartet (calibration disabled)")
    if config.get("space"):
        raise ValidityError("this family has no tuning space")
    if config.get("objective") != OBJECTIVE:
        raise ValidityError(f"objective must be {OBJECTIVE}")
    if horizon not in HORIZONS or arm not in ARMS:
        raise ValidityError(f"unsupported arm/horizon {arm}/{horizon}")
    if arm == HSTACK_ARM and horizon not in STACK:
        raise ValidityError(f"{HSTACK_ARM} is defined only at H{sorted(STACK)}")
    want = HSTACK_FEATURES[horizon] if arm == HSTACK_ARM else vf.expected_features(horizon, idp_local=arm in IDP_ARMS,
                                                                                    acled_agg=arm in ACLED_ARMS)
    if config.get("n_features") != want:
        raise ValidityError(f"recipe n_features must be {want} at H{horizon}")
    kind = baseline_kind(config)
    if arm in REFRESH_ARMS:      # task 10-19: explicit schedule, self-consistency digests, truthful role
        role, scheme = REFRESH_ARMS[arm]
        if kind != SELF_CONSISTENCY or not isinstance((config.get("baseline") or {}).get("equivalence"), dict):
            raise ValidityError(f"{arm} pins self_consistency equivalence digests (baseline.kind / baseline.equivalence)")
        if "calendar" not in config or "training" not in config or "region" in config:
            raise ValidityError(f"{arm} declares calendar and training (and no region)")
        if (config.get("model_card") or {}).get("arm_role") != role:
            raise ValidityError(f"{arm} has model_card.arm_role {role!r}")
        s = schedule_from_config(config, horizon)
        if s.scheme != scheme or bool(s.scoring_contexts) != (role == "hindcast"):
            raise ValidityError(f"{arm} is a {scheme} arm{' with scoring contexts' if role == 'hindcast' else ''}")
        if role == "production" and (s.sample_weights, s.calibration) != ("halving24", "b2"):
            raise ValidityError(f"{arm} keeps the halving24 weights and B2 calibration")
        if arm in ACLED_ARMS:
            check_acled_arm(config, s)
    elif "calendar" in config or "training" in config or kind != FROZEN_BASELINE:
        raise ValidityError("calendar/training overrides and self-consistency digests are defined only for the refresh arms")
    if "region" in config:
        region_iso2(config, arm)
        ref = config.get("region_equivalence") or {}
        missing = [k for k in REGION_EQUIVALENCE_KEYS if k not in ref]
        if missing:
            raise ValidityError(f"region_equivalence reference lacks {missing}")


def is_sha256(text):
    return isinstance(text, str) and len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def check_acled_arm(config, s: Schedule):
    """Task 10-20: the aggregated-ACLED arm is exactly the production calendar with an expanding halving24 backbone,
    identity calibration and no providers; Gate B (self-consistency digests) and Gate A (the paired baseline reference,
    baseline predictions and the frozen region map, each pinned by sha256 in ``comparison``) are both required."""
    if (s.scheme, s.sample_weights, s.calibration, s.providers) != ("expanding", "halving24", "identity", False):
        raise ValidityError(f"{ACLED_ARM} is an expanding halving24 backbone with identity calibration and no providers")
    if (s.main_first, s.main_last, s.supplement, s.supplement_blocks, s.scoring_contexts) != (
            tuple(sorted(MAIN_FIRST.items())), MAIN_LAST, ACLED_SUPPLEMENT, ACLED_SUPPLEMENT_BLOCKS, ()):
        raise ValidityError(f"{ACLED_ARM} keeps the production calendar (main windows to {MAIN_LAST}, supplement "
                            f"{ACLED_SUPPLEMENT[0]}..{ACLED_SUPPLEMENT[1]} with blocks {ACLED_SUPPLEMENT_BLOCKS})")
    comp = config.get("comparison")
    if not isinstance(comp, dict) or set(comp) != set(COMPARISON_ROLES) or not all(is_sha256(v) for v in comp.values()):
        raise ValidityError(f"{ACLED_ARM} pins the sha256 of every comparison role {list(COMPARISON_ROLES)}")
    if comp["region_mapping"] != REGION_MAPPING_SHA256:
        raise ValidityError("comparison region_mapping must be the frozen area_id -> region map")
    relation = (config.get("baseline") or {}).get("relation")
    if not isinstance(relation, str) or not relation.strip():
        raise ValidityError(f"{ACLED_ARM} states its two-gate baseline relation explicitly")


def baseline_kind(config):
    """``frozen_baseline`` (default: digests of a retained earlier run) or ``self_consistency`` (task 10-19: digests
    of a reviewed local no-fit build of the same inputs and recipe; no baseline run, no ablation claim)."""
    kind = (config.get("baseline") or {}).get("kind", FROZEN_BASELINE)
    if kind not in (FROZEN_BASELINE, SELF_CONSISTENCY):
        raise ValidityError(f"unknown baseline.kind {kind!r}")
    return kind


def equivalence_width(arm, horizon, kind, order):
    """Feature columns the pre-fit digests cover: the frozen baseline's prefix (idp), the own block (hstack) or, for
    self-consistency, every column of the recipe's order."""
    if kind == SELF_CONSISTENCY:
        return len(order)
    return vf.expected_features(horizon, idp_local=True) if arm == HSTACK_ARM else vf.EXPECTED_FEATURES[int(horizon)]


def region_iso2(config, arm):
    """The validated ISO2 set of a regional recipe (exact frozen list; only the idp/hstack arms)."""
    r = config["region"]
    if not isinstance(r, dict) or r.get("name") not in REGIONS:
        raise ValidityError(f"unknown region {r!r}")
    spec = REGIONS[r["name"]]
    if arm not in REGION_ARMS:
        raise ValidityError(f"regional recipes are defined only for {REGION_ARMS}")
    if r.get("code") != spec["code"] or list(r.get("iso2") or []) != list(spec["iso2"]):
        raise ValidityError(f"region {r['name']} must be code {spec['code']} with iso2 {list(spec['iso2'])}")
    sha = str(r.get("mapping_sha256") or "")
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValidityError("region mapping_sha256 must be a sha256 hex digest")
    return frozenset(spec["iso2"])


def region_mask(labels, iso2):
    """Rows of the arm-selected labels inside the region; every region country must be present and no ISO2 missing
    (Namibia is the string 'NA', never a missing value)."""
    codes = labels["iso2"].to_numpy(dtype=object)
    if any(not isinstance(c, str) or not c for c in codes):
        raise ValidityError("labels have a missing iso2 code")
    mask = np.isin(codes, sorted(iso2))
    present = set(codes[mask])
    if present != set(iso2):
        raise ValidityError(f"region countries without labels: {sorted(set(iso2) - present)}")
    return mask


def region_equivalence_digests(d):
    """Rows/labels/targets/phases and the whole context-free feature matrix (own block and any stacked blocks) of a
    regional arm; compared with the pooled baseline's retained artifacts restricted to the same region rows."""
    return {"rows": int(len(d.admin)), "arm_rows_csv_sha256": text_sha256(arm_rows_frame(d).to_csv(index=False)),
            "targets_sha256": array_digest(d.Y), "phase_sha256": array_digest(d.phase),
            "feature_order_sha256": vf.list_sha256(d.order), "feature_X_sha256": array_digest(d.X),
            "feature_nan_mask_sha256": array_digest(np.isnan(d.X))}


def region_reference(labels, X, order, iso2):
    """The same digests from retained baseline artifacts (labels.csv.gz with q*_str, base matrices, order), restricted
    to the region rows; used to pin a regional recipe's ``region_equivalence`` before any cloud job."""
    L = labels.reset_index(drop=True)
    for q in TARGETS:      # exact decimal text (read with dtype=str), never a lossy default float parse
        if not all(isinstance(v, str) for v in L[f"{q}_str"]):
            raise ValidityError(f"{q}_str must be read as text for an exact target digest")
    m = region_mask(L, iso2)
    Ls = L.loc[m].reset_index(drop=True)
    Y = np.column_stack([np.array([float(v) for v in Ls[f"{q}_str"]], dtype=np.float64) for q in TARGETS])
    frame = pd.DataFrame({"row": np.arange(len(Ls)), "admin_code": Ls["admin_code"].to_numpy(np.int64),
                          "target_ord": Ls["month_ord"].to_numpy(np.int64), "label_kind": Ls["label_kind"].to_numpy(dtype=object),
                          "source_family": Ls["source_family"].to_numpy(np.int64),
                          "source_available_ord": Ls["source_available_ord"].to_numpy(np.int64)})
    Xs = np.ascontiguousarray(np.asarray(X)[m])
    return {"rows": int(len(Ls)), "arm_rows_csv_sha256": text_sha256(frame.to_csv(index=False)),
            "targets_sha256": array_digest(Y), "phase_sha256": array_digest(Ls["phase_truth"].to_numpy(np.int64)),
            "feature_order_sha256": vf.list_sha256(list(order)), "feature_X_sha256": array_digest(Xs),
            "feature_nan_mask_sha256": array_digest(np.isnan(Xs))}


def scored_nan_table(d: ArmData, E: Block, rows, Xs):
    """Scored rows, label kinds, countries, NaN fraction and all-NaN column count of the history-materialized
    scoring inputs per target month, plus one context total (``target_month = all``)."""
    t, kinds = d.target[rows], d.kind[rows]
    iso2 = d.labels["iso2"].to_numpy()[rows]
    nan = np.isnan(Xs)
    out = []
    for name, i in [(label(int(m)), t == m) for m in np.unique(t)] + [("all", np.ones(len(t), dtype=bool))]:
        out.append({"context": E.block_id, "role": E.role, "target_month": name, "rows": int(i.sum()),
                    "originals": int((kinds[i] == "original").sum()), "copies": int((kinds[i] == "copy").sum()),
                    "countries": int(pd.Series(iso2[i]).nunique()), "nan_fraction": float(nan[i].mean()) if i.any() else None,
                    "all_nan_columns": int(nan[i].all(axis=0).sum()) if i.any() else None})
    return pd.DataFrame(out)


def run_contexts(d: ArmData, out_dir, log=print, quartet=None):
    """Fit every context of one arm/H; write contexts/, predictions and memberships; return package inputs.
    ``quartet`` (task 10-21 formal refits) replaces the fixed QUARTET settings in every provider and backbone fit."""
    os.makedirs(os.path.join(out_dir, "contexts"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "gcs-only"), exist_ok=True)
    plans = plan_contexts(d)
    summary = plan_summary(d, plans)
    summary.to_csv(os.path.join(out_dir, "contexts", "schedule.csv"), index=False)
    s = d.schedule
    assertions = plan_assertions(d, plans) if s.declared else None
    if assertions is not None:      # task 10-19: per-context fitting-label/scored-key receipts, logged before any fit
        with open(os.path.join(out_dir, "contexts", "assertions.json"), "w") as f:
            json.dump({"schedule": s.record(), "contexts": assertions}, f, indent=1, default=str)
        for c, a in assertions.items():
            log(f"assert {c}: cutoff {a['cutoff']} fitting targets {a['fit_target_min']}..{a['fit_target_max']} "
                f"({a['train_rows']} rows, {s.scheme}, {s.sample_weights}, {s.calibration}) scored {a['score_rows']} "
                f"keys {a['score_keys_sha256'][:16]} checks passed: {', '.join(sorted(a['checks']))}")
    t0 = time.time()
    preds, units, members, overlays, fit_ledger = [], [], {}, {}, []
    shared, nan_tables = {}, []
    for p in plans:
        E = p["block"]
        if len(p["score"]) == 0:
            raise ValidityError(f"{E.block_id}: no scored rows")
        cal_parts, prov_records = [], []
        for pv in p["providers"]:
            if len(pv["pred"]) == 0:
                prov_records.append({"role": "provider", "block": pv["block"].record(), "status": "no_rows_to_predict"})
                continue
            fit = run_fit(d, "provider", pv["block"], pv["train"], pv["pred"], pv["excluded"], pv["block"].cutoff, quartet=quartet)
            rec = fit["record"]
            if np.isin(d.family[pv["pred"]], d.family[pv["train"]]).any():
                raise ValidityError(f"{pv['block'].block_id}: a predicted family is in the provider's fitting labels")
            prov_records.append(rec)
            fit_ledger.append({"context": E.block_id, **{k: v for k, v in rec.items() if k not in ("targets", "block")},
                               "fit_block": pv["block"].block_id})
            fid = f"{E.block_id}|{pv['block'].block_id}"
            members[f"{fid}|train"], members[f"{fid}|pred"] = pv["train"].astype(np.int32), pv["pred"].astype(np.int32)
            overlays[f"{fid}|train_src"], overlays[f"{fid}|train_fam"] = fit["history"]["train_src"], fit["history"]["train_fam"]
            overlays[f"{fid}|pred_src"], overlays[f"{fid}|pred_fam"] = fit["history"]["pred_src"], fit["history"]["pred_fam"]
            if d.obs_aliased:
                overlays[f"{fid}|train_alias"], overlays[f"{fid}|pred_alias"] = fit["history"]["train_alias"], fit["history"]["pred_alias"]
            cal_parts.append(pd.DataFrame({"row": pv["pred"], "provider_block": pv["block"].block_id,
                                           "provider_cutoff": pv["block"].cutoff,
                                           **{f"p_{q}": fit["P"][:, k] for k, q in enumerate(TARGETS)}}))
            log(f"[{time.time() - t0:7.0f}s] {E.block_id} provider {pv['block'].block_id}: train {len(pv['train'])} pred {len(pv['pred'])}")
        pool = pd.concat(cal_parts, ignore_index=True) if cal_parts else pd.DataFrame(columns=["row", "provider_block", "provider_cutoff", *[f"p_{q}" for q in TARGETS]])
        rows = pool["row"].to_numpy(np.int64)
        if len(np.unique(rows)) != len(rows):
            raise ValidityError(f"{E.block_id}: a calibration key has more than one provider")
        if len(rows) and (np.isin(d.family[rows], p["S_E"]).any() or (d.target[rows] > E.cutoff).any() or (d.avail[rows] > E.cutoff).any()):
            raise ValidityError(f"{E.block_id}: calibration row violates the context cutoff or family exclusion")
        Pcal = pool[[f"p_{q}" for q in TARGETS]].to_numpy(np.float64)
        cal = fit_b2(Pcal, d.X[rows][:, d.core_idx], d.Y[rows], d.target[rows], E.cutoff)
        if s.calibration == "identity" and cal["status"] != "identity_no_support":
            raise ValidityError(f"{E.block_id}: declared identity calibration has a calibration pool")
        pool["weight"] = decay(d.target[rows], E.cutoff) if len(rows) else []
        pool.insert(1, "admin_code", d.admin[rows])
        pool.insert(2, "target_ord", d.target[rows])
        pool.insert(3, "label_kind", d.kind[rows])
        pool.insert(4, "source_family", d.family[rows])
        pool.to_csv(os.path.join(out_dir, "contexts", f"calibration_pool_{E.block_id}.csv.gz"), index=False)
        sid = p.get("shared_fit")
        if reused(p):      # hindcast: the shared backbone of the first context predicts this context (no refit)
            if d.obs_aliased:
                raise ValidityError("aliased (CH) history is not supported with a shared hindcast backbone")
            first = shared[sid]
            if np.intersect1d(p["train"], p["score"]).size or not np.array_equal(p["train"], first["train"]):
                raise ValidityError(f"{E.block_id}: shared backbone rows differ or contain a scored row")
            P, Xp, psrc, pfam = predict_rows(d, first["boosters"], p["score"], p["S_E"])
            fit = {"record": {**first["record"], "predicted_rows": int(len(p["score"])), "shared_fit_of": sid},
                   "boosters": first["boosters"], "payloads": first["payloads"], "P": P, "Xp": Xp,
                   "history": {"train_src": first["history"]["train_src"], "train_fam": first["history"]["train_fam"],
                               "pred_src": psrc, "pred_fam": pfam}}
        else:
            fit = run_fit(d, "backbone", E, p["train"], p["score"], p.get("train_excluded", p["S_E"]), E.cutoff,
                          pred_excluded=p["S_E"], quartet=quartet)
            if sid is not None:
                fit["record"]["shared_contexts"] = [q["block"].block_id for q in plans if q.get("shared_fit") == sid]
                shared[sid] = {**fit, "train": p["train"]}
            fit_ledger.append({"context": E.block_id, **{k: v for k, v in fit["record"].items() if k not in ("targets", "block")},
                               "fit_block": E.block_id})
        members[f"{E.block_id}|backbone|train"], members[f"{E.block_id}|score"] = p["train"].astype(np.int32), p["score"].astype(np.int32)
        overlays[f"{E.block_id}|backbone|train_src"], overlays[f"{E.block_id}|backbone|train_fam"] = fit["history"]["train_src"], fit["history"]["train_fam"]
        overlays[f"{E.block_id}|score_src"], overlays[f"{E.block_id}|score_fam"] = fit["history"]["pred_src"], fit["history"]["pred_fam"]
        if d.obs_aliased:      # task 10-28: identical keys to history_overlay_arrays; a missing array is an error, never skipped
            overlays[f"{E.block_id}|backbone|train_alias"] = fit["history"]["train_alias"]
            overlays[f"{E.block_id}|score_alias"] = fit["history"]["pred_alias"]
        Zs = d.X[p["score"]][:, d.core_idx]
        corrected, delta = apply_b2(cal, fit["P"], Zs)
        star, phase = ae("projection").project_and_decode(corrected)
        frame = pd.DataFrame({"arm": d.arm, "horizon": d.horizon, "context": E.block_id, "period": E.role,
                              "row": p["score"], "admin_code": d.admin[p["score"]], "target_ord": d.target[p["score"]],
                              "target_month": label(d.target[p["score"]]), "iso2": d.labels["iso2"].to_numpy()[p["score"]],
                              "label_kind": d.kind[p["score"]], "source_family": d.family[p["score"]],
                              "source_month_ord": d.labels["source_month_ord"].to_numpy()[p["score"]],
                              "phase_truth": d.phase[p["score"]],
                              **{f"{q}_truth": d.Y[p["score"], k] for k, q in enumerate(TARGETS)},
                              **{f"{q}_backbone": fit["P"][:, k] for k, q in enumerate(TARGETS)},
                              **{f"{q}_correction": delta[:, k] for k, q in enumerate(TARGETS)},
                              **{f"{q}_raw": corrected[:, k] for k, q in enumerate(TARGETS)},
                              **{f"{q}_star": star[:, k] for k, q in enumerate(TARGETS)},
                              "phase": phase, "calibration_status": cal["status"]})
        nf, comp = vf.oracle_completeness(d.X[p["score"]], d.order, d.horizon)
        frame["oracle_finite_values"] = -1 if nf is None else nf
        frame["oracle_complete"] = "not_applicable_h0" if comp is None else np.where(comp, "complete", "incomplete")
        if s.declared:      # uncalibrated backbone: raw quartet -> projection -> 0.20 decoding (no B2)
            ustar, uphase = ae("projection").project_and_decode(fit["P"])
            for k, q in enumerate(TARGETS):
                frame[f"{q}_star_uncal"] = ustar[:, k]
            frame["phase_uncal"] = uphase
            nan_tables.append(scored_nan_table(d, E, p["score"], fit["Xp"]))
        preds.append(frame)
        ctx = {"context": E.record(), "scored_rows": int(len(p["score"])), "scored_families": int(len(p["S_E"])),
               "excluded_families_sha256": array_digest(np.asarray(p["S_E"], np.int64)),
               "excluded_eligible_rows": p["excluded_eligible"], "backbone": fit["record"], "providers": prov_records,
               "calibration": b2_record(cal, d.core_inputs)}
        if assertions is not None:
            ctx.update(assertions=assertions[E.block_id], schedule=s.record())
        with open(os.path.join(out_dir, "contexts", f"{E.block_id}.json"), "w") as f:
            json.dump(ctx, f, indent=1, default=str)
        units.append({"context": E, "payloads": fit["payloads"], "record": fit["record"], "calibration": cal,
                      "score": p["score"], "Xs": fit["Xp"], "frame": frame})
        log(f"[{time.time() - t0:7.0f}s] {E.block_id}: backbone train {len(p['train'])} scored {len(p['score'])} calibration {cal['status']} ({cal['rows']} rows)")
    for p in plans:
        members[f"{p['block'].block_id}|excluded_families"] = np.asarray(p["S_E"], np.int64)
        for pv in p["providers"]:
            members[f"{p['block'].block_id}|{pv['block'].block_id}|excluded_families"] = np.asarray(pv["excluded"], np.int64)
        if "train_excluded" in p:
            members[f"{p['block'].block_id}|backbone|excluded_families"] = np.asarray(p["train_excluded"], np.int64)
    np.savez_compressed(os.path.join(out_dir, "contexts", "memberships.npz"), **members)
    pd.DataFrame({"row": np.arange(len(d.admin)), "admin_code": d.admin, "target_ord": d.target, "label_kind": d.kind,
                  "source_family": d.family, "source_available_ord": d.avail}).to_csv(
        os.path.join(out_dir, "contexts", "arm_rows.csv.gz"), index=False)
    np.savez_compressed(os.path.join(out_dir, "gcs-only", "history_overlays.npz"), **overlays)
    pd.DataFrame(fit_ledger).to_csv(os.path.join(out_dir, "contexts", "fit_ledger.csv"), index=False)
    predictions = pd.concat(preds, ignore_index=True)
    predictions.to_csv(os.path.join(out_dir, "predictions.csv.gz"), index=False)
    if nan_tables:
        pd.concat(nan_tables, ignore_index=True).to_csv(os.path.join(out_dir, "contexts", "scored_nan_by_month.csv"), index=False)
    return {"plans": plans, "summary": summary, "units": units, "predictions": predictions, "fit_ledger": fit_ledger,
            "assertions": assertions}


def holdout_name(lo, hi):
    """``holdout_2026_01_04`` for 2026-01..2026-04 (``holdout_2025_11_2026_02`` across a year)."""
    (y0, m0), (y1, m1) = (tuple(int(x) for x in str(m).split("-")) for m in (lo, hi))
    return f"holdout_{y0}_{m0:02d}_{m1:02d}" if y0 == y1 else f"holdout_{y0}_{m0:02d}_{y1}_{m1:02d}"


def report_periods(predictions, schedule):
    """Named row masks of a declared schedule: ``primary_<year>`` (main or hindcast rows by target year) and one
    ``holdout_<from>_<to>`` per supplement report block."""
    role, t = predictions["period"].to_numpy(), predictions["target_ord"].to_numpy(np.int64)
    prim = np.isin(role, ("main", "hindcast"))
    out = {f"primary_{y}": prim & (t // 12 == y) for y in sorted(set((t[prim] // 12).tolist()))}
    for lo, hi in schedule.supplement_blocks:
        out[holdout_name(lo, hi)] = (role == "supplement") & (t >= parse_month(lo)) & (t <= parse_month(hi))
    return out


def evaluate(predictions, schedule=None):
    """Per-context (year) and per-period pooled metric blocks, with row/copy/country/round denominators. A declared
    schedule (task 10-19) adds the per-year / per-block periods and the same blocks for the uncalibrated backbone
    (``*_star_uncal`` / ``phase_uncal``) as ``by_context_uncalibrated`` / ``by_period_uncalibrated``."""
    def block(f, star="star", phase="phase"):
        b = metric_block(f["phase_truth"].to_numpy(), f[phase].to_numpy(),
                         f[[f"{q}_truth" for q in TARGETS]].to_numpy(), f[[f"{q}_{star}" for q in TARGETS]].to_numpy())
        b.update(original_rows=int((f["label_kind"] == "original").sum()), copy_rows=int((f["label_kind"] == "copy").sum()),
                 countries=int(f["iso2"].nunique()), source_rounds=int(f["source_family"].nunique()),
                 calibration_status=sorted(set(f["calibration_status"])))
        return b
    out = {"by_context": {c: block(f) for c, f in predictions.groupby("context", sort=True)},
           "by_period": {r: block(f) for r, f in predictions.groupby("period", sort=True)}}
    if schedule is not None and schedule.declared:
        named = report_periods(predictions, schedule)
        out["by_period"].update({k: block(predictions[m]) for k, m in named.items()})
        unc = {"star": "star_uncal", "phase": "phase_uncal"}
        out["by_context_uncalibrated"] = {c: block(f, **unc) for c, f in predictions.groupby("context", sort=True)}
        out["by_period_uncalibrated"] = {**{r: block(f, **unc) for r, f in predictions.groupby("period", sort=True)},
                                         **{k: block(predictions[m], **unc) for k, m in named.items()}}
    return out


def metric_periods(ev, schedule):
    """MLflow period blocks: ``primary`` = main (hindcast: the pooled scoring contexts), ``holdout`` = the pooled
    supplement, and for a declared schedule every ``primary_<year>`` / ``holdout_<from>_<to>`` block."""
    bp = ev["by_period"]
    prim = "hindcast" if schedule.scoring_contexts else "main"
    out = {"primary": bp.get(prim, {}), "holdout": bp.get("supplement", {})}
    if schedule.declared:
        out.update({k: v for k, v in bp.items() if k.startswith(("primary_", "holdout_"))})
    return out, prim


# --------------------------------------------------------------------------- paired augmented comparison (task 10-20)
#
# Old = the retained production run's uncalibrated outputs (``q*_star_uncal``, ``phase_uncal``); new = this arm's
# outputs. Rows are paired on the unique scored-row key and must match one to one with equal truths; every cohort holds
# originals and validity copies together (no original-only/copy-only scores, no completeness filter). The nine regions
# are exclusive area_id slices of the global model. Pooled cells are recomputed from rows. Undefined values stay null
# with their reason; delta = new - old only where both are defined.

SCALAR_METRICS = ("binary.accuracy", "binary.precision", "binary.recall", "binary.f1", "binary.f2", "four_class.accuracy",
                  "four_class.macro_f1", "ordinal_phase_mae", *[f"{q}_{m}" for q in TARGETS for m in ("mae", "rmse", "r2")],
                  "share_phase3plus_r2")
PAIR_KEYS = ("context", "admin_code", "target_ord", "label_kind", "source_family")
BASELINE_TAG, DELTA_TAG = "baseline_uncalibrated", "delta_vs_baseline_uncalibrated"
FOUR_CLASSES = ("1", "2", "3", "4-5")


def region_cohort(r):
    return "region_" + REGION_NAMES[int(r)].lower().replace(" ", "_") + "_global_model"


def comparison_periods(schedule, horizon):
    """[{name, rows, target_from, target_to, eligible, label}] in report order: pooled primary, every primary year of the
    family calendar (a year outside this horizon's window is listed as ineligible), the supplement and its blocks."""
    h = int(horizon)
    first, last = parse_month(schedule.first(h)), parse_month(schedule.main_last)
    rec = lambda name, rows, lo, hi, ok, text: {"name": name, "rows": rows, "target_from": label(lo), "target_to": label(hi),
                                                "eligible": ok, "label": text}
    out = [rec("primary", "main", first, last, True, f"pooled primary targets {label(first)}..{label(last)}")]
    for y in range(min(parse_month(m) for _, m in schedule.main_first) // 12, last // 12 + 1):
        lo, hi = max(first, y * 12), min(last, y * 12 + 11)
        out.append(rec(f"primary_{y}", "main", lo, hi, True, f"primary targets {label(lo)}..{label(hi)}") if lo <= hi else
                   rec(f"primary_{y}", "main", y * 12, y * 12 + 11, False, "outside primary window"))
    s0, s1 = (parse_month(m) for m in schedule.supplement)
    out.append(rec("holdout", "supplement", s0, s1, True, f"supplement {label(s0)}..{label(s1)} (not a full calendar year)"))
    for lo, hi in schedule.supplement_blocks:
        out.append(rec(holdout_name(lo, hi), "supplement", parse_month(lo), parse_month(hi), True, f"supplement block {lo}..{hi}"))
    return out


def paired_rows(new_pred, baseline_path, region_path):
    """New predictions (row order kept) joined one to one with the baseline's uncalibrated outputs and the region map.
    Duplicate or unmatched keys, unequal truths/periods, a non-identity new output or an unmapped area raise."""
    truth = ["phase_truth", *[f"{q}_truth" for q in TARGETS]]
    old_cols = [*[f"{q}_star_uncal" for q in TARGETS], "phase_uncal"]
    new = new_pred[[*PAIR_KEYS, "period", *truth, *[f"{q}_star" for q in TARGETS], "phase",
                    *[f"{q}_star_uncal" for q in TARGETS], "phase_uncal"]]
    for a, b in [(f"{q}_star", f"{q}_star_uncal") for q in TARGETS] + [("phase", "phase_uncal")]:
        if not np.array_equal(new[a].to_numpy(), new[b].to_numpy()):
            raise ValidityError(f"the new arm's delivered {a} is not its uncalibrated backbone output")
    new = new.drop(columns=old_cols)
    base = pd.read_csv(baseline_path, float_precision="round_trip", usecols=[*PAIR_KEYS, "period", *truth, *old_cols])
    for side, f in (("new", new), ("baseline", base)):
        if f.duplicated(list(PAIR_KEYS)).any():
            raise ValidityError(f"{side} predictions have duplicate scored-row keys")
    m = new.merge(base.rename(columns={c: f"{c}_base" for c in ["period", *truth]}), on=list(PAIR_KEYS), how="left",
                  validate="one_to_one", indicator=True)
    matched = int((m["_merge"] == "both").sum())
    if matched != len(new) or matched != len(base):
        raise ValidityError(f"unmatched scored keys: {len(new) - matched} new-only, {len(base) - matched} baseline-only")
    for c in ["period", *truth]:
        if not np.array_equal(m[c].to_numpy(), m[f"{c}_base"].to_numpy()):
            raise ValidityError(f"paired rows differ in {c}")
    regions = pd.read_csv(region_path)
    if list(regions.columns) != ["area_id", "region"] or regions["area_id"].duplicated().any() \
            or not regions["region"].isin(list(REGION_NAMES)).all():
        raise ValidityError("region map must be unique area_id -> region 0..8")
    m["region"] = m["admin_code"].map(regions.set_index("area_id")["region"])
    if m["region"].isna().any():
        raise ValidityError(f"{int(m['region'].isna().sum())} scored rows have an unmapped area")
    m["region"] = m["region"].astype(np.int64)
    return m.drop(columns=["_merge", *[f"{c}_base" for c in ["period", *truth]]])


def class_support(phase):
    return dict(zip(FOUR_CLASSES, np.bincount(np.minimum(np.asarray(phase, dtype=np.int64), 4), minlength=5)[1:].tolist()))


def comparison_cell(f):
    """Old/new metric blocks, delta, NA reasons, supports and fixed-axis confusions of one period x cohort."""
    T, Y = f["phase_truth"].to_numpy(), f[[f"{q}_truth" for q in TARGETS]].to_numpy()
    old = metric_block(T, f["phase_uncal"].to_numpy(), Y, f[[f"{q}_star_uncal" for q in TARGETS]].to_numpy())
    new = metric_block(T, f["phase"].to_numpy(), Y, f[[f"{q}_star" for q in TARGETS]].to_numpy())
    why = lambda b, k: b["na_reasons"].get(k) or b["na_reasons"].get("all")
    cell = {"eligible": True, "support": {"n_rows": int(len(f)), "unique_areas": int(f["admin_code"].nunique()),
                                          "original_rows": int((f["label_kind"] == "original").sum()),
                                          "copy_rows": int((f["label_kind"] == "copy").sum()),
                                          "truth_class_support": class_support(T),
                                          "old_pred_class_support": class_support(f["phase_uncal"]),
                                          "new_pred_class_support": class_support(f["phase"]),
                                          "old_binary_counts": old.get("binary.counts"), "new_binary_counts": new.get("binary.counts")},
            "old": {}, "new": {}, "delta": {}, "na_reasons": {"old": {}, "new": {}, "delta": {}}}
    for k in SCALAR_METRICS:
        o, n = old.get(k), new.get(k)
        cell["old"][k], cell["new"][k] = o, n
        for side, v, b in (("old", o, old), ("new", n, new)):
            if v is None:
                cell["na_reasons"][side][k] = why(b, k)
        if o is None or n is None:
            cell["delta"][k] = None
            cell["na_reasons"]["delta"][k] = "; ".join(f"{s} undefined: {why(b, k)}" for s, v, b in (("old", o, old), ("new", n, new)) if v is None)
        else:
            cell["delta"][k] = float(n) - float(o)
    co, cn = old.get("four_class.confusion"), new.get("four_class.confusion")
    zero = [[0] * 4 for _ in range(4)]
    co, cn = co or zero, cn or zero
    cell["confusion"] = {"axis": list(FOUR_CLASSES), "rows": "truth", "cols": "prediction", "old": co, "new": cn,
                         "diff": [[cn[i][j] - co[i][j] for j in range(4)] for i in range(4)]}
    return cell


def ineligible_cell(reason):
    return {"eligible": False, "support": {"n_rows": 0}, "old": {k: None for k in SCALAR_METRICS},
            "new": {k: None for k in SCALAR_METRICS}, "delta": {k: None for k in SCALAR_METRICS},
            "na_reasons": {s: {k: reason for k in SCALAR_METRICS} for s in ("old", "new", "delta")}, "confusion": None}


def paired_comparison(new_pred, baseline_path, region_path, schedule, horizon, baseline):
    """Complete per-horizon comparison: every period x (all_scored + nine regions) cell, pairing and accounting facts."""
    m = paired_rows(new_pred, baseline_path, region_path)
    t, role = m["target_ord"].to_numpy(np.int64), m["period"].to_numpy()
    periods = comparison_periods(schedule, horizon)
    cohorts = [("all_scored", None)] + [(region_cohort(r), r) for r in REGION_NAMES]
    cells, accounting = {}, {}
    for p in periods:
        mask = (role == p["rows"]) & (t >= parse_month(p["target_from"])) & (t <= parse_month(p["target_to"]))
        if not p["eligible"]:
            if mask.any():
                raise ValidityError(f"{p['name']}: an ineligible period has scored rows")
            cells[p["name"]] = {c: ineligible_cell(p["label"]) for c, _ in cohorts}
            continue
        cells[p["name"]] = {c: comparison_cell(m[mask if r is None else mask & (m["region"].to_numpy() == r)]) for c, r in cohorts}
        n = cells[p["name"]]["all_scored"]["support"]["n_rows"]
        regional = sum(cells[p["name"]][c]["support"]["n_rows"] for c, r in cohorts if r is not None)
        accounting[p["name"]] = {"rows": n, "regions_sum": regional, "mask_rows": int(mask.sum())}
        if not n == regional == int(mask.sum()):
            raise ValidityError(f"{p['name']}: regional rows {regional} do not sum to {n}")
    blocks = [p for p in periods if p["name"].startswith("holdout_")]
    if cells["primary"]["all_scored"]["support"]["n_rows"] != sum(accounting[p["name"]]["rows"] for p in periods
                                                                   if p["name"].startswith("primary_") and p["eligible"]):
        raise ValidityError("annual primary rows do not sum to the pooled primary")
    if accounting["primary"]["rows"] + accounting["holdout"]["rows"] != len(m):
        raise ValidityError("scored rows outside the primary window and the supplement")
    return {"kind": "acled_paired_comparison", "arm": ACLED_ARM, "horizon": int(horizon), "baseline": baseline,
            "new_columns": [*[f"{q}_star" for q in TARGETS], "phase"],
            "pairing": {"keys": list(PAIR_KEYS), "rows": int(len(m)), "unmatched": 0, "truth_mismatches": 0,
                        "originals": int((m["label_kind"] == "original").sum()), "copies": int((m["label_kind"] == "copy").sum())},
            "region_map": {"sha256": REGION_MAPPING_SHA256, "cohorts": {region_cohort(r): n for r, n in REGION_NAMES.items()}},
            "periods": periods, "supplement_blocks": [p["name"] for p in blocks], "metrics": list(SCALAR_METRICS),
            "cells": cells, "accounting": accounting,
            "semantics": "augmented cohort (originals and validity copies together) for every cell; unweighted rows; "
                         "delta = new - old; undefined values are null with their reason"}


def comparison_tables(comp):
    """(long scalar table, fixed-axis confusion table) of a ``paired_comparison``."""
    h, run = comp["horizon"], comp["baseline"]["run_id"]
    region_of = {c: n for c, n in comp["region_map"]["cohorts"].items()}
    rows, conf = [], []
    for p in comp["periods"]:
        for cohort, cell in comp["cells"][p["name"]].items():
            s = cell["support"]
            base = {"horizon": h, "period": p["name"], "period_label": p["label"], "target_from": p["target_from"],
                    "target_to": p["target_to"], "eligible": p["eligible"], "cohort": cohort, "region": region_of.get(cohort, "all")}
            for k in SCALAR_METRICS:
                rows.append({**base, "metric": k, "baseline_run_id": run, "old": cell["old"][k], "new": cell["new"][k],
                             "delta": cell["delta"][k], "old_na_reason": cell["na_reasons"]["old"].get(k),
                             "new_na_reason": cell["na_reasons"]["new"].get(k), "delta_na_reason": cell["na_reasons"]["delta"].get(k),
                             "n_rows": s["n_rows"], "unique_areas": s.get("unique_areas", 0), "original_rows": s.get("original_rows", 0),
                             "copy_rows": s.get("copy_rows", 0)})
            c = cell["confusion"]
            for i, tc in enumerate(FOUR_CLASSES):
                for j, pc in enumerate(FOUR_CLASSES):
                    conf.append({**base, "truth_class": tc, "pred_class": pc, "old": c["old"][i][j] if c else None,
                                 "new": c["new"][i][j] if c else None, "diff": c["diff"][i][j] if c else None})
    return pd.DataFrame(rows), pd.DataFrame(conf)


def comparison_metrics(comp):
    """Finite MLflow scalars: ``<period>.<cohort>.<metric>`` (new), ``…baseline_uncalibrated.<metric>`` (old),
    ``…delta_vs_baseline_uncalibrated.<metric>`` and each eligible cell's ``n_rows``."""
    out = {}
    for p in comp["periods"]:
        if not p["eligible"]:
            continue
        for cohort, cell in comp["cells"][p["name"]].items():
            out[f"{p['name']}.{cohort}.n_rows"] = float(cell["support"]["n_rows"])
            for k in SCALAR_METRICS:
                for key, v in ((f"{p['name']}.{cohort}.{k}", cell["new"][k]), (f"{p['name']}.{cohort}.{BASELINE_TAG}.{k}", cell["old"][k]),
                               (f"{p['name']}.{cohort}.{DELTA_TAG}.{k}", cell["delta"][k])):
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v):
                        out[key] = float(v)
    return out


def write_comparison(out, comp):
    """comparison.json (null for undefined; never NaN/Infinity), comparison.csv and comparison_confusion.csv."""
    text = json.dumps(comp, indent=1, allow_nan=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    with open(out.path("comparison.json"), "w") as f:
        f.write(text)
    scalars, conf = comparison_tables(comp)
    scalars.to_csv(out.path("comparison.csv"), index=False, float_format="%.17g")
    conf.to_csv(out.path("comparison_confusion.csv"), index=False)
    return ["comparison.json", "comparison.csv", "comparison_confusion.csv"]


REFRESH_INPUTS = ("refreshed 2026-10-19 inputs: new raw/interim panel versions extended to 2026-10; WFP_Price redefined for "
                  "the whole history (100 + local-currency year-on-year %); World Bank RTP and Bloomberg new vintages; ACLED "
                  "2025-05 replaced; GOSIF v3 for 2025; VIIRS and Nino3.4 2026-04 placeholders replaced; IPC areas/analyses "
                  "snapshot 2026-10-19")


def refresh_caveat(arm, s: Schedule):
    role = REFRESH_ARMS[arm][0]
    tail = (" Self-consistency digests from a reviewed local no-fit build were verified before fitting; not a same-cohort "
            "or same-feature comparison with earlier runs. Fixed learner, retrospective data, one seed; no causal or "
            "significance claim.")
    if role == "hindcast":
        return (f"Out-of-period hindcast on the {REFRESH_INPUTS}: one backbone fitted on labels with target in "
                f"{s.window[0]}..{min(s.window[1], s.shared_cutoff)} ({s.sample_weights} weights, {s.calibration} calibration) "
                f"scores {', '.join(n for n, _, _ in s.scoring_contexts)}; it is trained on later years, so this is not a "
                "temporal forecast; the scored report families are excluded from its fitting labels and histories." + tail)
    if role == "control":
        return (f"Rolling control on the {REFRESH_INPUTS}: each annual context's backbone is fitted only on labels with target "
                f"in the {s.months} months up to its cutoff ({s.sample_weights} weights, {s.calibration} calibration); scored "
                "rows equal the production contexts'." + tail)
    return (f"Production retrain on the {REFRESH_INPUTS}; annual contexts as before, supplement {s.supplement[0]}.."
            f"{s.supplement[1]} scored only (latest backbone cutoff unchanged)." + tail)


def comparison_inputs(inputs, config):
    """Task 10-20: every comparison role is present and has exactly the sha256 its recipe pins."""
    from research_cloud.training.common import TrialError, sha256_file
    pins = config["comparison"]
    missing = [r for r in COMPARISON_ROLES if r not in inputs]
    if missing:
        raise TrialError(f"input manifest lacks the comparison roles {missing}")
    differ = [r for r in COMPARISON_ROLES if sha256_file(inputs[r]) != pins[r]]
    if differ:
        raise TrialError(f"comparison inputs differ from the recipe pins: {differ}")
    return {r: pins[r] for r in COMPARISON_ROLES}


def prepare(inputs, config, out, manifest=None):
    """Stage 1, arm selection and every pre-fit gate of one job (shared by ``fit`` and the no-fit ``gate`` command).
    Returns {"d", "order", "built", "idp", "hstack", "regional", "kind"}; a failed gate writes equivalence.json and
    raises TrialError. Never fits. The aggregated-ACLED arm also needs ``manifest`` (training-input identities) and
    passes Gate A (``paired_gate.json``) after Gate B."""
    from research_cloud.training.common import TrialError
    h, arm = config.get("horizon"), config.get("arm")
    try:
        check_config(config, h, arm)
        schedule = schedule_from_config(config, h)
    except ValidityError as e:
        raise TrialError(str(e)) from e
    if arm == HPT_ARM:
        return hpt_prepare(inputs, config, out, schedule)
    idp, hstack, acled = arm in IDP_ARMS, arm == HSTACK_ARM, arm in ACLED_ARMS
    if acled:      # bind the reference, baseline predictions and region map before any build
        if manifest is None:
            raise TrialError(f"{arm} needs the input manifest for its paired baseline gate")
        comparison_inputs(inputs, config)
    built = vf.build_dataset(inputs, out.path("dataset"), horizons=(h, *STACK[h]) if hstack else (h,),
                             matrix_dir=out.path("gcs-only/dataset"), keep=True, idp_local=idp or hstack,
                             **({"acled_agg": True} if acled else {}))
    objs = built.pop("objects")
    hist_groups, stack_got = None, {}
    if hstack:      # own idp matrix + longer-horizon origin blocks (task 10-17 hstack)
        Xs, order, hist_groups, blocks = stack_features(objs["horizons"], h)
        for k, names, sl in blocks:
            if len(names) != 243 + len(vf.oracle_names(k)):
                raise TrialError(f"H{k} stacked block has {len(names)} origin-dependent columns")
            stack_got[str(k)] = {"columns": len(names), "names_sha256": vf.list_sha256(names),
                                 "X_sha256": array_digest(Xs[:, sl]), "nan_mask_sha256": array_digest(np.isnan(Xs[:, sl]))}
        labels, X = select_arm(objs["labels"], Xs, arm)
        del Xs
    else:
        labels, X = select_arm(objs["labels"], objs["horizons"][h]["X"], arm)
        order = objs["horizons"][h]["order"]
    if len(order) != config["n_features"]:
        raise TrialError("feature order length differs from the recipe")
    rows = objs["horizons"][h]["rows"]
    rows = rows.loc[(objs["labels"]["label_kind"] == "original").to_numpy() if arm == "original" else slice(None)].reset_index(drop=True)
    regional = "region" in config
    if regional:      # SA-local (task 10-17): the same arm restricted to the region's rows before any planning or fit
        m = region_mask(labels, region_iso2(config, arm))
        labels = labels.loc[m].reset_index(drop=True)
        X = np.ascontiguousarray(X[m])
        rows = rows.loc[m].reset_index(drop=True)
        print(f"region {config['region']['name']}: {int(m.sum())} of {len(m)} arm rows kept", flush=True)
    d = ArmData(arm, h, labels, X, order, objs["observations"], rows, hist_groups, schedule)
    del objs
    kind = baseline_kind(config)
    if regional:      # rows, labels and every context-free feature must equal the pooled baseline restricted to the region
        n0 = vf.EXPECTED_FEATURES[h]
        if set(order[n0:]) & set(CORE_INPUTS) or d.core_idx != [order.index(c) for c in CORE_INPUTS] or max(d.core_idx) >= n0:
            raise TrialError("B2 dynamics must come from the own block")
        want = config["region_equivalence"]
        got = region_equivalence_digests(d)
        differ = [k for k in REGION_EQUIVALENCE_KEYS if got[k] != want[k]]
        out.write_json("equivalence.json", {"arm": arm, "horizon": h, "region": config["region"], "baseline": config.get("baseline"),
                                            "treatment": got, "reference": want, "differing": differ, "passed": not differ,
                                            "stage": "pre-fit", "kind": "region-restricted pooled baseline",
                                            **({"stack_treatment": stack_got} if hstack else {})})
        if differ:
            raise TrialError(f"regional rows/features differ from the pooled baseline restricted to the region: {differ}")
        print(f"region equivalence passed ({len(REGION_EQUIVALENCE_KEYS)} keys; {got['rows']} rows)", flush=True)
    elif idp or hstack:     # the treatment must reuse the frozen baseline cohort (or the pinned build) before any fit
        if acled:      # task 10-20: 114 aggregated-ACLED columns then the local-IDP suffix, located by name; no B2 inputs
            n = len(order)
            if (order[n - 3:] != list(vf.IDP_LOCAL_FEATURES) or order[n - 117:n - 3] != list(vf.ACLED_AGG_FEATURES)
                    or set(order) & set(vf.OLD_ACLED_FEATURES) or d.core_idx):
                raise TrialError("aggregated-ACLED order: the 114 columns precede the local-IDP suffix, no compact conflict "
                                 "column remains and no B2 dynamics are used")
        else:
            n0 = vf.EXPECTED_FEATURES[h]
            n_own = vf.expected_features(h, idp_local=True)
            if (order[n0:n_own] != list(vf.IDP_LOCAL_FEATURES) or set(order[n0:]) & set(CORE_INPUTS)
                    or d.core_idx != [order.index(c) for c in CORE_INPUTS] or max(d.core_idx) >= n0):
                raise TrialError("local-IDP/stacked columns must follow the own block and never be B2 dynamics")
        want = (config.get("baseline") or {}).get("equivalence")
        width = equivalence_width(arm, h, kind, order)
        plans = plan_contexts(d)
        got = equivalence_digests(d, plans, width)
        if hstack:
            stack_want = config.get("stack_equivalence") or {}
            if stack_got != stack_want:
                out.write_json("equivalence.json", {"arm": arm, "horizon": h, "stack_treatment": stack_got,
                                                    "stack_reference": stack_want, "passed": False, "stage": "pre-fit"})
                raise TrialError("stacked blocks differ from the retained idp horizon matrices")
        try:
            differ = check_equivalence(got, want)
        except ValidityError as e:
            raise TrialError(str(e)) from e
        self_check = kind == SELF_CONSISTENCY
        out.write_json("equivalence.json", {"arm": arm, "horizon": h, "baseline": config["baseline"], "treatment": got,
                                            "differing": differ, "passed": not differ, "stage": "pre-fit",
                                            **({"stack_treatment": stack_got, "stack_reference": config.get("stack_equivalence")}
                                               if hstack else {}),
                                            **({"kind": kind, "width": width, "schedule": schedule.record()} if self_check else {})})
        if differ:
            raise TrialError(f"self-consistency digests differ from the pinned build: {differ}" if self_check else
                             f"treatment cohort/prefix differs from the frozen baseline: {differ}")
        print(("self-consistency digests passed" if self_check else "baseline equivalence passed") + f" ({len(EQUIVALENCE_KEYS)} keys)"
              + (f"; stacked blocks equal ({', '.join(f'H{k}' for k in STACK[h])})" if hstack else ""), flush=True)
        if acled:      # Gate A: the retained uncalibrated production run's backbone contract, item by item
            with open(inputs["acled_baseline_reference"]) as f:
                reference = json.load(f)
            paired = paired_gate(d, plans, reference, manifest)
            out.write_json("paired_gate.json", paired)
            if not paired["passed"]:
                raise TrialError(f"paired baseline gate failed: {paired['failed']}")
            print(f"paired baseline gate passed ({len(paired['checks'])} checks against run {paired['baseline']['run_id']})", flush=True)
    return {"d": d, "order": order, "built": built, "idp": idp, "hstack": hstack, "regional": regional, "kind": kind}


def acled_caveat(s: Schedule):
    return ("Aggregated-ACLED candidate on the 2026-10-19 refreshed inputs: the 14 compact conflict columns are replaced by "
            "114 columns of the 18 staged aggregated ACLED series (2026-10-20 export, retrospective vintage), all at "
            "A = T - H - 1 for fitting and scoring rows; every other input, the annual expanding halving24 backbone, its "
            "contexts/cutoffs and the augmented scored rows equal the retained production run (paired gate verified before "
            "fitting). Uncalibrated by design (no B2 or providers). Comparisons pair this arm with that run's uncalibrated "
            "predictions on identical augmented keys; they jointly reflect the ACLED source, feature definitions, coverage "
            "and the one-month cutoff. Fixed learner, one seed; no real-time, causal or significance claim.")


# --------------------------------------------------------------------------- task 10-21 tuned aggregated-ACLED arm


def hpt_values(values):
    """The 12 tuned values (D8): exactly the space's names, finite, inside the inclusive bounds, integers integral."""
    if not isinstance(values, dict) or set(values) != set(HPT_SPACE):
        raise ValidityError(f"tuned values must name exactly {sorted(HPT_SPACE)}")
    out = {}
    for k, s in HPT_SPACE.items():
        v = values[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v):
            raise ValidityError(f"{k}={v!r} is not a finite number")
        if s["type"] == "int":
            if float(v) != int(v):
                raise ValidityError(f"{k}={v!r} is not an integer")
            v = int(v)
        else:
            v = float(v)
        if not s["min"] <= v <= s["max"]:
            raise ValidityError(f"{k}={v} outside [{s['min']}, {s['max']}]")
        out[k] = v
    return out


def hpt_quartet(values):
    """Per-target estimator settings (the QUARTET layout) of the 12 values: q3 from its own group, q2/q4/q5 from the
    shared group, each with its group's untuned gamma/reg_alpha/reg_lambda."""
    v = hpt_values(values)
    by = {q: {**{a: v[f"{g}_{a}"] for a in HPT_AXES}, **HPT_UNTUNED[g]} for g, qs in HPT_GROUPS.items() for q in qs}
    return {q: by[q] for q in TARGETS}


def tuned_values(config, params):
    """The resolved 12 values of one job: the provider's suggestion (search) or the recipe's fixed values
    (reference/formal)."""
    merged = {**(config.get("fixed") or {}), **(params or {})}
    return hpt_values({k: merged[k] for k in HPT_SPACE if k in merged})


def selection_excluded_families(d: ArmData, keys=None):
    """Family IDs of the D7 keys (default SELECTION_EXCLUDED), resolved from the labels by (iso2, original month) and
    checked against the frozen IDs; every row of each family must carry only that country and source month."""
    keys = SELECTION_EXCLUDED if keys is None else keys
    iso2 = d.labels["iso2"].to_numpy(dtype=object)
    src = d.labels["source_month_ord"].to_numpy(np.int64)
    out = []
    for c, m, frozen in keys:
        got = np.unique(d.family[(iso2 == c) & (d.kind == "original") & (src == parse_month(m))]).tolist()
        rows = d.family == frozen
        if got != [frozen] or set(iso2[rows]) != {c} or set(src[rows].tolist()) != {parse_month(m)}:
            raise ValidityError(f"selection-excluded family ({c}, {m}) resolves to {got}, not the frozen {frozen}")
        out.append(frozen)
    return np.asarray(sorted(out), dtype=np.int64)


def selection_plans(d: ArmData, excluded):
    """Tuning contexts (D1/D7/D9): the main annual contexts only (the supplement is never fitted or scored); scored rows
    without the selection-excluded families; S_E = the selected rows' families UNION the excluded families, removed
    from the fitting labels and from both the fitting and the scoring histories. The union is explicit even where the
    excluded rows already lie outside a context's scored window."""
    excluded = np.asarray(excluded, dtype=np.int64)
    plans = []
    for E in scoring_blocks(d.horizon, d.schedule):
        if E.role != "main":
            continue
        window = (d.target >= E.target_lo) & (d.target <= E.target_hi)
        score = np.flatnonzero(window & ~np.isin(d.family, excluded))
        selected = np.unique(d.family[score])
        S_E = np.union1d(selected, excluded)
        eligible = (d.target <= E.cutoff) & (d.avail <= E.cutoff)
        train = np.flatnonzero(eligible & ~np.isin(d.family, S_E))
        plans.append({"block": E, "score": score, "S_E": S_E, "selected_families": selected, "selection_excluded": excluded,
                      "removed_scored_rows": int(window.sum() - len(score)), "train": train, "providers": [],
                      "excluded_eligible": int(eligible.sum() - len(train))})
    return plans


def hpt_plans(d: ArmData, config):
    """(plans, excluded families) of a tuned-arm recipe: D7 selection plans (tuning) or the ordinary annual contexts
    with their inherited exclusions (formal; the D7 mask is selection-only)."""
    excluded = selection_excluded_families(d)
    return (selection_plans(d, excluded) if config["mode"] == "tuning" else plan_contexts(d)), excluded


def selection_cohort(horizon):
    return {"selection_rows": SELECTION_ROWS[int(horizon)],
            "excluded_families": [{"iso2": c, "original_month": m, "family_id": f} for c, m, f in SELECTION_EXCLUDED]}


def check_formal_contract(c, horizon):
    """The formal refit contract, pinned in every tuning recipe before its search and copied into the formal recipe:
    the selected ACLED run as linked baseline (with its no-fit digests), the comparison inputs, final cohort counts,
    objective and DatasetInput."""
    from research_cloud.training.model_metadata import BASELINE_KEYS
    h = int(horizon)
    base = c.get("baseline") or {}
    ch = "ch_correction" in c      # task 10-28: the GOSIF-v3 corrected run of this horizon is the linked baseline
    if base.get("kind") != FROZEN_BASELINE or any(not isinstance(base.get(k), str) or not base[k].strip() for k in BASELINE_KEYS):
        raise ValidityError("the formal baseline links the selected ACLED run (frozen_baseline with every link key)" if not ch else
                            "the CH-correction baseline links the GOSIF-v3 run (frozen_baseline with every link key)")
    if ch:
        if base["arm"] != HPT_ARM or base["run_id"] != GPP_BASELINE_RUNS[h]:
            raise ValidityError(f"the CH-correction baseline is the GOSIF-v3 {HPT_ARM} H{h} run {GPP_BASELINE_RUNS[h]}")
    elif base["arm"] != ACLED_ARM or base["run_id"] != ACLED_BASELINE_RUNS[h]:
        raise ValidityError(f"the formal baseline is the selected {ACLED_ARM} H{h} run {ACLED_BASELINE_RUNS[h]}")
    if not isinstance(base.get("relation"), str) or not base["relation"].strip():
        raise ValidityError("the formal baseline states its relation explicitly")
    if not isinstance(base.get("equivalence"), dict) or sorted(base["equivalence"]) != sorted(EQUIVALENCE_KEYS):
        raise ValidityError("the formal baseline pins every no-fit equivalence digest")
    comp = c.get("comparison")
    if (not isinstance(comp, dict) or set(comp) != {"baseline_predictions", "region_mapping"}
            or not all(is_sha256(v) for v in comp.values()) or comp["region_mapping"] != REGION_MAPPING_SHA256):
        raise ValidityError("formal comparison pins the baseline predictions and the frozen region map")
    cohort = c.get("cohort")
    if ch:      # measured on the reviewed local no-fit build (never forced to the GOSIF-v3 counts)
        if (not isinstance(cohort, dict) or set(cohort) != {"final_rows", "holdout_rows"}
                or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in cohort.values())):
            raise ValidityError("the CH-correction cohort pins its measured final and holdout rows")
    elif cohort != {"final_rows": FINAL_ROWS[h], "holdout_rows": HOLDOUT_ROWS}:
        raise ValidityError(f"formal cohort must be {FINAL_ROWS[h]} rows with {HOLDOUT_ROWS} 2026 rows")
    if c.get("objective") != HPT_FORMAL_OBJECTIVE or not isinstance(c.get("dataset_input"), dict):
        raise ValidityError(f"formal recipes report {HPT_FORMAL_OBJECTIVE} and declare a dataset_input")
    card = c.get("model_card")
    if not isinstance(card, dict) or card.get("arm") != HPT_ARM or card.get("arm_role") != "candidate":
        raise ValidityError("the formal contract carries the final model card of this arm")


def check_hpt_config(config, horizon):
    """Task 10-21 tuned arm: the ACLED arm's schedule and features plus the mode contract. tuning/search = exactly
    HPT_FIXED and HPT_SPACE; tuning/reference = HPT_FIXED plus the fixed quartet's 12 values and no space; formal =
    HPT_FIXED plus 12 frozen values inside the space, the frozen winner record and the formal contract."""
    mode, role = config.get("mode"), config.get("candidate_role")
    if config.get("arm") != HPT_ARM or horizon not in HORIZONS or mode not in HPT_MODES:
        raise ValidityError(f"{HPT_ARM} recipes declare mode {HPT_MODES} at H{HORIZONS}")
    if (mode == "tuning") != (role in HPT_ROLES) or (mode == "formal" and "candidate_role" in config):
        raise ValidityError(f"tuning recipes declare candidate_role {HPT_ROLES}; formal recipes none")
    if config.get("n_features") != vf.expected_features(horizon, idp_local=True, acled_agg=True) or "region" in config:
        raise ValidityError(f"recipe n_features must be {vf.expected_features(horizon, idp_local=True, acled_agg=True)} (no region)")
    s = schedule_from_config(config, horizon)
    if ((s.scheme, s.sample_weights, s.calibration, s.providers) != ("expanding", "halving24", "identity", False)
            or (s.main_first, s.main_last, s.supplement, s.supplement_blocks, s.scoring_contexts)
            != (tuple(sorted(MAIN_FIRST.items())), MAIN_LAST, ACLED_SUPPLEMENT, ACLED_SUPPLEMENT_BLOCKS, ())):
        raise ValidityError(f"{HPT_ARM} keeps the {ACLED_ARM} calendar and its uncalibrated expanding backbone")
    if (config.get("model_card") or {}).get("arm_role") != "candidate":
        raise ValidityError(f"{HPT_ARM} has model_card.arm_role 'candidate'")
    base = config.get("baseline") or {}
    if not isinstance(base.get("equivalence"), dict) or sorted(base["equivalence"]) != sorted(EQUIVALENCE_KEYS) \
            or not isinstance(base.get("relation"), str) or not base["relation"].strip():
        raise ValidityError("tuned-arm recipes pin every no-fit digest of their mode's plans and state the relation")
    if mode == "tuning":
        fixed, space = (HPT_FIXED, HPT_SPACE) if role == "search" else ({**HPT_FIXED, **HPT_REFERENCE}, {})
        if config.get("fixed") != fixed or config.get("space") != space or config.get("objective") != HPT_OBJECTIVE:
            raise ValidityError(f"{role} recipes declare exactly their fixed settings, space and {HPT_OBJECTIVE}")
        if base.get("kind") != SELF_CONSISTENCY or config.get("cohort") != selection_cohort(horizon):
            raise ValidityError("tuning recipes pin self-consistency digests of the D7 selection cohort")
        if any(k in config for k in ("comparison", "frozen", "dataset_input", "corrected_input", "ch_correction")) or not isinstance(config.get("formal"), dict):
            raise ValidityError("tuning recipes carry the formal contract only under 'formal' (no corrected_input)")
        check_formal_contract(config["formal"], horizon)
        return
    fixed = config.get("fixed") or {}
    if {k: v for k, v in fixed.items() if k not in HPT_SPACE} != HPT_FIXED or config.get("space") != {} or "formal" in config:
        raise ValidityError("formal recipes fix HPT_FIXED plus the 12 frozen values, with no space")
    values = hpt_values({k: v for k, v in fixed.items() if k in HPT_SPACE})
    check_formal_contract(config, horizon)
    fr = config.get("frozen")
    if (not isinstance(fr, dict) or set(fr) != set(FROZEN_KEYS) or not is_sha256(fr["freeze_sha256"])
            or not is_sha256(fr["freeze_index_sha256"]) or fr["winner_role"] not in HPT_ROLES
            or not isinstance(fr["winner_trial_id"], str) or not fr["winner_trial_id"] or fr["params_sha256"] != digest(values)):
        raise ValidityError("formal fitting requires the frozen winner record of all-horizon freezes")
    if "ch_correction" in config:
        check_ch_correction(config["ch_correction"], config)
    elif "corrected_input" in config:
        check_corrected_input(config["corrected_input"], config)


def check_corrected_input(ci, config):
    """Structure of a formal recipe's corrected-input contract (task 10-27); ``corrected_gate`` checks the build."""
    if not isinstance(ci, dict) or set(ci) != set(CORRECTED_INPUT_KEYS):
        raise ValidityError(f"corrected_input declares exactly {list(CORRECTED_INPUT_KEYS)}")
    if (ci["kind"] != CORRECTED_INPUT_KIND or ci["replaced_role"] != "interim" or not isinstance(ci["data_version"], str)
            or not ci["data_version"].strip() or not isinstance(ci["relation"], str) or not ci["relation"].strip()):
        raise ValidityError(f"corrected_input is a {CORRECTED_INPUT_KIND} of the interim role with a data_version and relation")
    pins, orig = ci["inputs"], ci["original_inputs"]
    need = {"interim", "raw_panel", *FORMAL_ROLES}
    if (not isinstance(pins, dict) or not need <= set(pins) or not all(is_sha256(v) for v in pins.values())
            or not isinstance(orig, dict) or set(orig) != {"interim"} or not is_sha256(orig["interim"])
            or orig["interim"] == pins["interim"]):
        raise ValidityError("corrected_input pins every input role and replaces exactly the interim panel")
    fr, comp = config["frozen"], config["comparison"]
    if (pins["freeze"], pins["freeze_index"]) != (fr["freeze_sha256"], fr["freeze_index_sha256"]) \
            or any(pins[r] != comp[r] for r in comp):
        raise ValidityError("corrected_input input pins agree with the frozen and comparison pins")
    if list(ci["changed_columns"]) != list(GPP_INPUT_FEATURES):
        raise ValidityError("corrected_input changes exactly the GPP_mean-derived feature columns")
    corr, un, run = ci["corrected"], ci["unchanged_columns"], ci["original_run"]
    if not isinstance(corr, dict) or set(corr) != set(CORRECTED_REPINNED) or not all(is_sha256(v) for v in corr.values()):
        raise ValidityError(f"corrected_input re-pins exactly {list(CORRECTED_REPINNED)}")
    values = un.get("values") if isinstance(un, dict) else None
    if (set(un or {}) != {"order_sha256", "nan_mask_sha256", "values"} or not isinstance(values, dict)
            or len(values) != config["n_features"] - len(GPP_INPUT_FEATURES) or set(values) & set(GPP_INPUT_FEATURES)
            or not all(is_sha256(v) for v in (un["order_sha256"], un["nan_mask_sha256"], *values.values()))):
        raise ValidityError("corrected_input pins per-column digests and the NaN mask of every unchanged feature column")
    if (not isinstance(run, dict) or set(run) != {"run_id", "recipe_sha256", "journal_sha256"}
            or not isinstance(run["run_id"], str) or not run["run_id"] or not all(is_sha256(run[k]) for k in ("recipe_sha256", "journal_sha256"))):
        raise ValidityError("corrected_input names the original formal run (run_id, recipe and journal sha256)")
    rep = ci["report"]
    if (not isinstance(rep, dict) or set(rep) != {"role", "regions", "somalia_iso2"} or rep["role"] != REPORT_ROLE
            or REPORT_ROLE not in pins or pins[REPORT_ROLE] == comp["region_mapping"] or not isinstance(rep["regions"], dict)
            or not rep["regions"] or not all(str(k).isdigit() and isinstance(v, str) and v.strip() for k, v in rep["regions"].items())
            or rep["somalia_iso2"] != "SO"):
        raise ValidityError(f"corrected_input.report pins its own {REPORT_ROLE} (not the frozen pairing map), named regions and SO")


def corrected_gate(d: "ArmData", inputs, config, got):
    """(differing names, record) of a corrected-input formal build (task 10-27): every pinned input role's bytes, the
    eleven preserved digests against the original formal ``baseline.equivalence``, the two re-pinned feature digests,
    and the per-column digests / NaN mask of every column outside the declared GPP-derived columns."""
    from research_cloud.training.common import sha256_file
    ci = config["corrected_input"]
    roles = {r: bool(r in inputs and sha256_file(inputs[r]) == want) for r, want in sorted(ci["inputs"].items())}
    unpinned = sorted(set(inputs) - set(ci["inputs"]))
    base = config["baseline"]["equivalence"]
    preserved = [k for k in CORRECTED_PRESERVED if got[k] != base[k]]
    repinned = [k for k in CORRECTED_REPINNED if got[k] != ci["corrected"][k]]
    changed = list(ci["changed_columns"])
    missing = [c for c in changed if c not in d.order]
    names = [c for c in d.order if c not in changed]
    cols, mask = non_acled_digests(d.X, d.order, names)
    want = ci["unchanged_columns"]
    columns = sorted({c for c in names if cols[c] != want["values"].get(c)} | (set(want["values"]) - set(names)))
    order_ok, mask_ok = vf.list_sha256(names) == want["order_sha256"], mask == want["nan_mask_sha256"]
    differ = (preserved + repinned + [f"input:{r}" for r, ok in roles.items() if not ok] + [f"unpinned_input:{r}" for r in unpinned]
              + [f"missing_column:{c}" for c in missing] + ([] if not columns and order_ok and mask_ok else ["unchanged_columns"]))
    record = {"kind": ci["kind"], "data_version": ci["data_version"], "inputs_verified": roles, "unpinned_inputs": unpinned,
              "preserved_keys": list(CORRECTED_PRESERVED), "preserved_differing": preserved,
              "repinned_keys": list(CORRECTED_REPINNED), "repinned_differing": repinned,
              "changed_columns": changed, "unchanged_columns": len(names), "unchanged_columns_differing": columns[:50],
              "unchanged_columns_differing_count": len(columns), "unchanged_order_ok": order_ok, "unchanged_nan_mask_ok": mask_ok,
              "original_run": ci["original_run"], "passed": not differ}
    return differ, record


# --------------------------------------------------------------------------- CH validity correction (task 10-28)
#
# A formal refit of the tuned arm with the frozen parameters of the GOSIF-v3 corrected run on the same corrected inputs
# plus a keyed CH reference-window input (role ``ch_links``). Labels, report families, histories, cohort and fitting rows
# change by design, so the recipe's ``ch_correction`` block replaces the GPP-only ``corrected_input`` contract (never
# both): it pins every input role, links the GPP run (run, recipe, journal, retained predictions, frozen parameters),
# pins the reviewed local no-fit build's self-consistency digests (the 13 equivalence keys plus label and history lineage
# digests that include CH roles, aliases and storage months), the measured CH counts, and preservation digests on the
# common rows (every GPP row; the added CH copies are the only new rows): keys, exact targets/phases and every
# non-history feature column. Comparisons pair (context, admin_code, target_ord) with exact phase and q2..q5 truth;
# whole-population and common-support results are reported separately.

CH_CORRECTION_KIND = "ch_validity_correction"
CH_CORRECTION_KEYS = ("kind", "data_version", "inputs", "gpp_baseline", "preserved", "self_consistency", "ch_counts",
                      "relation", "report")
GPP_BASELINE_RUNS = {0: "8e07686349304eecb9a52ff36e41bc63", 6: "ac709d280d8a435bad7fb80266c051c7",
                     12: "0bc109fa7cfe4411a33fca47b907c0b1"}
CH_GPP_KEYS = ("run_id", "recipe_sha256", "journal_sha256", "predictions_sha256", "params_sha256")
CH_PRESERVED_KEYS = ("common_rows", "common_keys_sha256", "targets_sha256", "phase_sha256", "feature_order_sha256",
                     "non_history_columns", "non_history_nan_mask_sha256")
CH_LINEAGE_KEYS = ("labels_lineage_sha256", "observations_lineage_sha256")
CH_LABEL_LINEAGE = ("admin_code", "month_ord", "label_kind", "source_admin_code", "source_month_ord", "source_available_ord",
                    "source_family", "source_family_alias", "anl_id", "link_status", "valid_from_ord", "valid_to_ord", "ch_role",
                    "ch_report_id", "storage_month_ord")
CH_OBS_LINEAGE = ("admin_code", "month_ord", "reported_phase", "family", "family_alias", "storage_month_ord")
CH_COUNT_KEYS = ("added_copies", "reclassified_upstream_copies", "cross_country_aliases", "labels_after", "label_kind_after",
                 "relationship_dispositions", "family_renames", "history_events_moved_to_nominal_month", "history_aliased_events")
CH_PAIR_KEYS = ("context", "admin_code", "target_ord")
CH_TRUTH = ("phase_truth", "q2_truth", "q3_truth", "q4_truth", "q5_truth")


def check_ch_correction(cc, config):
    """Structure of a formal recipe's CH-correction contract (task 10-28); ``ch_gate`` checks the build."""
    h = int(config["horizon"])
    if "corrected_input" in config:
        raise ValidityError("ch_correction replaces the GPP-only corrected_input contract (never both)")
    if not isinstance(cc, dict) or set(cc) != set(CH_CORRECTION_KEYS):
        raise ValidityError(f"ch_correction declares exactly {list(CH_CORRECTION_KEYS)}")
    if (cc["kind"] != CH_CORRECTION_KIND or not isinstance(cc["data_version"], str) or not cc["data_version"].strip()
            or not isinstance(cc["relation"], str) or not cc["relation"].strip()):
        raise ValidityError(f"ch_correction is a {CH_CORRECTION_KIND} with a data_version and relation")
    pins = cc["inputs"]
    need = {"interim", "raw_panel", vf.CH_LINKS_ROLE, REPORT_ROLE, *FORMAL_ROLES}
    if not isinstance(pins, dict) or not need <= set(pins) or not all(is_sha256(v) for v in pins.values()):
        raise ValidityError(f"ch_correction pins every input role including {sorted(need)}")
    fr, comp = config["frozen"], config["comparison"]
    if (pins["freeze"], pins["freeze_index"]) != (fr["freeze_sha256"], fr["freeze_index_sha256"]) or any(pins[r] != comp[r] for r in comp):
        raise ValidityError("ch_correction input pins agree with the frozen and comparison pins")
    g = cc["gpp_baseline"]
    if (not isinstance(g, dict) or set(g) != set(CH_GPP_KEYS) or g["run_id"] != GPP_BASELINE_RUNS[h]
            or g["run_id"] != (config.get("baseline") or {}).get("run_id")
            or not all(is_sha256(g[k]) for k in CH_GPP_KEYS if k != "run_id")
            or g["predictions_sha256"] != comp["baseline_predictions"] or g["params_sha256"] != fr["params_sha256"]):
        raise ValidityError("ch_correction links the GOSIF-v3 run of this horizon (run, recipe, journal, retained predictions, "
                            "frozen parameters)")
    p = cc["preserved"]
    cols = p.get("non_history_columns") if isinstance(p, dict) else None
    if (not isinstance(p, dict) or set(p) != set(CH_PRESERVED_KEYS) or not isinstance(p["common_rows"], int) or p["common_rows"] < 1
            or not isinstance(cols, dict) or len(cols) != config["n_features"] - len(vf.HISTORY_FEATURES)
            or set(cols) & set(vf.HISTORY_FEATURES) or not all(is_sha256(v) for v in cols.values())
            or not all(is_sha256(p[k]) for k in CH_PRESERVED_KEYS if k not in ("common_rows", "non_history_columns"))):
        raise ValidityError("ch_correction pins the common rows, their keys/truths and every non-history feature column")
    sc = cc["self_consistency"]
    if not isinstance(sc, dict) or set(sc) != set(EQUIVALENCE_KEYS) | set(CH_LINEAGE_KEYS):
        raise ValidityError("ch_correction pins the 13 no-fit digests and the label/history lineage digests of the reviewed build")
    if not isinstance(cc["ch_counts"], dict) or set(cc["ch_counts"]) != set(CH_COUNT_KEYS):
        raise ValidityError(f"ch_correction pins the measured CH counts {list(CH_COUNT_KEYS)}")
    rep = cc["report"]
    if (not isinstance(rep, dict) or set(rep) != {"role", "regions", "somalia_iso2"} or rep["role"] != REPORT_ROLE
            or pins[REPORT_ROLE] == comp["region_mapping"] or not isinstance(rep["regions"], dict) or not rep["regions"]
            or not all(str(k).isdigit() and isinstance(v, str) and v.strip() for k, v in rep["regions"].items())
            or rep["somalia_iso2"] != "SO"):
        raise ValidityError(f"ch_correction.report pins its own {REPORT_ROLE}, named regions and SO")


def ch_lineage_digests(d: "ArmData"):
    """Label and history lineage digests of a CH build: CH roles, report ids, aliases, storage and source months."""
    return {"labels_lineage_sha256": frame_sha256(d.labels[list(CH_LABEL_LINEAGE)]),
            "observations_lineage_sha256": frame_sha256(d.obs[list(CH_OBS_LINEAGE)])}


def alias_exclusion_record(d: "ArmData", plans, overlays):
    """Per-context provenance checks (both family ids of every scored row are in S_E; no fitting label and no selected
    history event carries an excluded family or alias) and the exact changes the aliases cause against a family-only
    exclusion of the same plans: fitting rows and history sources removed only because of an alias."""
    out, bad = {}, []
    alias_rows = np.flatnonzero(d.family_alias >= 0)
    obs_alias = d.obs["family_alias"].to_numpy(np.int64) if "family_alias" in d.obs.columns else np.full(len(d.obs), -1, np.int64)
    for p in plans:
        E, score, train, S_E = p["block"], p["score"], p["train"], p["S_E"]
        ids = np.concatenate([d.family[score], d.family_alias[score][d.family_alias[score] >= 0]])
        checks = {"scored_ids_in_S_E": bool(np.isin(ids, S_E).all()),
                  "no_fitting_label_family_or_alias_excluded": bool(not in_families(d, S_E, train).any())}
        for key in (f"{E.block_id}|backbone|train", f"{E.block_id}|score"):
            fam, ali = overlays[f"{key}_fam"], overlays.get(f"{key}_alias")
            checks[f"{key.split('|', 1)[1]}_history_clean"] = bool(not np.isin(fam[fam >= 0], S_E).any()
                                                                  and (ali is None or not np.isin(ali[ali >= 0], S_E).any()))
        eligible = (d.target <= E.cutoff) & (d.avail <= E.cutoff)
        only_alias_rows = int((eligible & np.isin(d.family_alias, S_E) & ~np.isin(d.family, np.unique(d.family[score]))).sum())
        alias_only_events = int((np.isin(obs_alias, S_E) & ~np.isin(d.obs["family"].to_numpy(np.int64), S_E)).sum())
        out[E.block_id] = {"checks": checks, "S_E_ids": int(len(S_E)), "alias_ids_in_S_E": int(len(np.setdiff1d(S_E, np.unique(d.family[score])))),
                           "fitting_rows_excluded_only_by_alias": only_alias_rows,
                           "history_events_excluded_only_by_alias": alias_only_events}
        bad += [f"{E.block_id}:{k}" for k, v in checks.items() if not v]
    return {"alias_rows": int(len(alias_rows)), "aliased_events": int((obs_alias >= 0).sum()), "contexts": out}, bad


def ch_gate(d: "ArmData", inputs, config, got, plans, built):
    """(differing names, record) of a CH-correction formal build (task 10-28)."""
    from research_cloud.training.common import sha256_file
    cc = config["ch_correction"]
    roles = {r: bool(r in inputs and sha256_file(inputs[r]) == want) for r, want in sorted(cc["inputs"].items())}
    unpinned = sorted(set(inputs) - set(cc["inputs"]))
    sc, p = cc["self_consistency"], cc["preserved"]
    lineage = ch_lineage_digests(d)
    have = {**{k: got[k] for k in EQUIVALENCE_KEYS}, **lineage}
    self_diff = sorted(k for k in sc if have.get(k) != sc[k])
    if "ch_role" not in d.labels.columns:
        raise ValidityError("a CH-correction build lacks the CH label columns")
    common = np.flatnonzero(d.labels["ch_role"].to_numpy(dtype=object) != "added_copy")
    names = [c for c in d.order if c not in vf.HISTORY_FEATURES]
    cols, mask = non_acled_digests(d.X[common], d.order, names)
    want_cols = p["non_history_columns"]
    col_diff = sorted({c for c in names if cols[c] != want_cols.get(c)} | (set(want_cols) - set(names)))
    preserved = {"common_rows": int(len(common)), "common_keys_sha256": array_digest(np.column_stack([d.admin[common], d.target[common]])),
                 "targets_sha256": array_digest(d.Y[common]), "phase_sha256": array_digest(d.phase[common]),
                 "feature_order_sha256": vf.list_sha256(d.order), "non_history_nan_mask_sha256": mask}
    pres_diff = sorted(k for k, v in preserved.items() if v != p[k]) + (["non_history_columns"] if col_diff else [])
    overlays = history_overlay_arrays(d, plans)
    aliases, alias_bad = alias_exclusion_record(d, plans, overlays)
    counts = built.get("ch_correction") or {}
    count_diff = sorted(k for k in CH_COUNT_KEYS if json.dumps(counts.get(k), sort_keys=True, default=str)
                        != json.dumps(cc["ch_counts"][k], sort_keys=True, default=str))
    no_providers = sum(len(q["providers"]) for q in plans) == 0 and not any(reused(q) for q in plans)
    differ = ([f"self_consistency:{k}" for k in self_diff] + [f"preserved:{k}" for k in pres_diff]
              + [f"input:{r}" for r, ok in roles.items() if not ok] + [f"unpinned_input:{r}" for r in unpinned]
              + [f"ch_count:{k}" for k in count_diff] + [f"alias:{k}" for k in alias_bad] + ([] if no_providers else ["providers_or_shared_backbone_present"]))
    record = {"kind": cc["kind"], "data_version": cc["data_version"], "inputs_verified": roles, "unpinned_inputs": unpinned,
              "self_consistency": have, "self_consistency_differing": self_diff, "preserved": preserved,
              "preserved_differing": pres_diff, "non_history_columns": len(names), "non_history_columns_differing": col_diff[:50],
              "added_copy_rows": int(len(d.admin) - len(common)), "ch_counts": {k: counts.get(k) for k in CH_COUNT_KEYS},
              "ch_counts_differing": count_diff, "aliases": aliases, "gpp_baseline": cc["gpp_baseline"], "passed": not differ}
    return differ, record


def ch_pairing(new_pred, baseline_path, horizon, schedule):
    """(common rows, new-only rows, old-only rows, reclassification counts): one-to-one (context, admin_code, target_ord)
    keys on both sides; both files are this horizon and every row's context/period is the scheduled block of its target
    (origin = target - H by construction); on common keys the period and the exact phase and q2..q5 truths must be equal
    (a changed truth stops the job, it is never dropped). label_kind/source_family/iso2 may differ (old/new kept)."""
    h = int(horizon)
    cols = ["horizon", *CH_PAIR_KEYS, "period", "iso2", "label_kind", "source_family", *CH_TRUTH, "phase", *[f"{q}_star" for q in TARGETS]]
    base = pd.read_csv(baseline_path, float_precision="round_trip", keep_default_na=False, na_values=[""], dtype={"iso2": str},
                       usecols=cols)
    new = new_pred[cols].copy()
    blocks = scoring_blocks(h, schedule)
    for side, f in (("new", new), ("baseline", base)):
        if (f["horizon"].to_numpy() != h).any():
            raise ValidityError(f"{side} predictions are not all horizon {h}")
        if f.duplicated(list(CH_PAIR_KEYS)).any():
            raise ValidityError(f"{side} predictions have duplicate (context, admin_code, target_ord) keys")
        t = f["target_ord"].to_numpy(np.int64)
        want_ctx, want_role = np.full(len(f), "", dtype=object), np.full(len(f), "", dtype=object)
        for b in blocks:
            m = (t >= b.target_lo) & (t <= b.target_hi)
            want_ctx[m], want_role[m] = b.block_id, b.role
        if (want_ctx != f["context"].to_numpy(dtype=object)).any() or (want_role != f["period"].to_numpy(dtype=object)).any():
            raise ValidityError(f"{side} predictions have a row outside its scheduled context/period")
    m = new.merge(base, on=list(CH_PAIR_KEYS), how="outer", suffixes=("", "_old"), indicator=True)
    both = m[m["_merge"] == "both"].copy()
    for c in ("period", *CH_TRUTH):
        if not np.array_equal(both[c].to_numpy(), both[f"{c}_old"].to_numpy()):
            raise ValidityError(f"common keys differ in {c} (truth/period must be preserved)")
    reclass = {"label_kind": int((both["label_kind"] != both["label_kind_old"]).sum()),
               "source_family": int((both["source_family"] != both["source_family_old"]).sum()),
               "iso2": int((both["iso2"] != both["iso2_old"]).sum()),
               "label_kind_transitions": {f"{a}->{b}": int(n) for (a, b), n in
                                          both.loc[both["label_kind"] != both["label_kind_old"]].groupby(["label_kind_old", "label_kind"]).size().items()}}
    old_only = m[m["_merge"] == "right_only"]
    old_only = pd.DataFrame({**{k: old_only[k].to_numpy() for k in CH_PAIR_KEYS},
                             **{c: old_only[f"{c}_old"].to_numpy() for c in ("period", "iso2", "label_kind", "source_family", *CH_TRUTH,
                                                                              "phase", *[f"{q}_star" for q in TARGETS])}})
    return both, m[m["_merge"] == "left_only"][[c for c in new.columns]].copy(), old_only, reclass


def _ch_cell(f, old=False):
    """Six metrics of one common-support frame for the new (default) or the old (GOSIF-v3) outputs."""
    T, q3 = f["phase_truth"].to_numpy(np.int64), f["q3_truth"].to_numpy(np.float64)
    if old:
        return lean_metrics(T, f["phase_old"].to_numpy(np.int64), q3, f["q3_star_old"].to_numpy(np.float64), FORMAL_METRICS)
    return lean_metrics(T, f["phase"].to_numpy(np.int64), q3, f["q3_star"].to_numpy(np.float64), FORMAL_METRICS)


def _ch_compare(f, counts):
    new, old = _ch_cell(f), _ch_cell(f, old=True)
    delta, why = {}, {}
    for k in FORMAL_METRICS:
        delta[k] = None if new[k] is None or old[k] is None else float(new[k]) - float(old[k])
        if delta[k] is None:
            why[k] = "; ".join(f"{side} undefined: {b['na_reasons'][k]}" for side, b in (("baseline", old), ("new", new)) if b[k] is None)
    return {**counts, "n_rows": int(len(f)), "original_rows_new": int((f["label_kind"] == "original").sum()),
            "copy_rows_new": int((f["label_kind"] == "copy").sum()), "original_rows_old": int((f["label_kind_old"] == "original").sum()),
            "copy_rows_old": int((f["label_kind_old"] == "copy").sum()),
            "reclassified_rows": int((f["label_kind"] != f["label_kind_old"]).sum()),
            "new": new, "baseline": old, "delta": delta, "delta_na_reasons": why}


def ch_comparison(new_pred, baseline_path, schedule, horizon, baseline):
    """Common-support comparison per formal scope and per scheduled context: six metrics for the GOSIF-v3 run's delivered
    outputs (old) and this run (new) on the same keys and truths, the delta, and the whole-population / added / removed /
    reclassified row counts with old and new original/copy counts."""
    both, new_only, old_only, reclass = ch_pairing(new_pred, baseline_path, horizon, schedule)
    t_all, role_all = new_pred["target_ord"].to_numpy(np.int64), new_pred["period"].to_numpy()
    t, role = both["target_ord"].to_numpy(np.int64), both["period"].to_numpy()
    tn, rn = new_only["target_ord"].to_numpy(np.int64), new_only["period"].to_numpy()
    to, ro = old_only["target_ord"].to_numpy(np.int64), old_only["period"].to_numpy()
    cells = {}
    for s in hpt_scopes(schedule, horizon):
        within = lambda tt, rr: (rr == s["period"]) & (tt >= s["lo"]) & (tt <= s["hi"])
        cells[s["scope"]] = {"target_from": label(s["lo"]), "target_to": label(s["hi"]),
                             **_ch_compare(both[within(t, role)], {"new_population_rows": int(within(t_all, role_all).sum()),
                                                                   "added_rows": int(within(tn, rn).sum()), "removed_rows": int(within(to, ro).sum())})}
    contexts = {}
    for b in scoring_blocks(horizon, schedule):
        sel = lambda f: (f["context"] == b.block_id).to_numpy()
        contexts[b.block_id] = {"role": b.role, "target_from": label(b.target_lo), "target_to": label(b.target_hi), "cutoff": label(b.cutoff),
                                **_ch_compare(both[sel(both)], {"new_population_rows": int(sel(new_pred).sum()), "added_rows": int(sel(new_only).sum()),
                                                                "removed_rows": int(sel(old_only).sum())})}
    return {"kind": "ch_common_support_comparison", "arm": HPT_ARM, "horizon": int(horizon), "baseline": baseline,
            "pairing": {"keys": list(CH_PAIR_KEYS), "truth": list(CH_TRUTH), "horizon_checked": int(horizon),
                        "scheduled_context_checked": True, "common_rows": int(len(both)), "new_only_rows": int(len(new_only)),
                        "old_only_rows": int(len(old_only)), "truth_mismatches": 0, "reclassified": reclass},
            "scopes": [{**s, "lo": label(s["lo"]), "hi": label(s["hi"])} for s in hpt_scopes(schedule, horizon)],
            "metrics": list(FORMAL_METRICS), "definitions": {k: METRIC_DEFINITIONS[k] for k in (*FORMAL_METRICS, "n_rows")},
            "cells": cells, "contexts": contexts,
            "semantics": "common support = keys scored by both runs with identical phase and q2..q5 truth; old = the GOSIF-v3 run's "
                         "delivered (uncalibrated) outputs with its own label kinds; new = this run; unweighted rows; delta = new - "
                         "old; differing populations are reported separately and a delta is not an isolated model effect"}, (both, new_only, old_only)


def ch_common_report(frames, map_path, schedule, horizon, spec, new_pred):
    """Every inherited report cell (``corrected_report`` layout) on the common support for old and new, with deltas, the
    declared/observed windows, NA reasons and per-cell common / whole-population / added / removed / reclassified counts
    and old and new original/copy counts (old counts use the GOSIF-v3 run's own label kinds)."""
    both, new_only, old_only = frames
    old = both.drop(columns=["phase", "q3_star", "label_kind", "iso2"]).rename(
        columns={"phase_old": "phase", "q3_star_old": "q3_star", "label_kind_old": "label_kind", "iso2_old": "iso2"})
    rep = lambda f: corrected_report(f, map_path, schedule, horizon, spec)[0]
    new_rows, old_rows = rep(both), rep(old)
    count_rows = {name: rep(f) for name, f in (("population", new_pred), ("added", new_only), ("removed", old_only),
                                                ("reclassified", both[both["label_kind"] != both["label_kind_old"]]))}
    rows, scalars = [], {}
    for i, (n, o) in enumerate(zip(new_rows, old_rows)):
        cells = [n, o] + [count_rows[k][i] for k in count_rows]
        if len({(c["table"], c["subset"], c["scope"]) for c in cells}) != 1 or n["n_rows"] != o["n_rows"]:
            raise ValidityError("common-support report cells differ in layout")
        rec = {"horizon": n["horizon"], "table": n["table"], "subset": n["subset"], "scope": n["scope"],
               "declared_from": n["declared_from"], "declared_to": n["declared_to"], "observed_from": n["observed_from"],
               "observed_to": n["observed_to"], "common_rows": n["n_rows"],
               "original_rows_new": n["original_rows"], "copy_rows_new": n["copy_rows"],
               "original_rows_old": o["original_rows"], "copy_rows_old": o["copy_rows"],
               **{f"{k}_rows": count_rows[k][i]["n_rows"] for k in count_rows},
               "population_original_rows": count_rows["population"][i]["original_rows"],
               "population_copy_rows": count_rows["population"][i]["copy_rows"]}
        key = f"common.{n['table']}.{n['subset'].lower().replace(' ', '_')}.{n['scope']}"
        scalars[f"{key}.n_rows"] = float(n["n_rows"])
        for k in FORMAL_METRICS:
            a, b = n[k], o[k]
            rec[f"new.{k}"], rec[f"old.{k}"] = a, b
            rec[f"delta.{k}"] = None if a is None or b is None else float(a) - float(b)
            rec[f"new_na_reason.{k}"], rec[f"old_na_reason.{k}"] = n["na_reasons"].get(k), o["na_reasons"].get(k)
            for name, v in ((f"{key}.{k}", a), (f"{key}.baseline.{k}", b), (f"{key}.delta_vs_baseline.{k}", rec[f"delta.{k}"])):
                if isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v):
                    scalars[name] = float(v)
        rows.append(rec)
    return rows, scalars


CH_COUNT_FIELDS = ("n_rows", "new_population_rows", "added_rows", "removed_rows", "reclassified_rows", "original_rows_new",
                   "copy_rows_new", "original_rows_old", "copy_rows_old")


def write_ch_comparison(out, comp, common_rows):
    """ch_comparison.json (null for undefined), ch_comparison.csv (scope and context level x metric, with every count) and
    ch_common_report.csv (every inherited report cell on the common support)."""
    with open(out.path("ch_comparison.json"), "w") as f:
        f.write(json.dumps(comp, indent=1, allow_nan=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    rows = []
    for level, items in (("scope", comp["cells"]), ("context", comp["contexts"])):
        for name, c in items.items():
            for k in FORMAL_METRICS:
                rows.append({"horizon": comp["horizon"], "level": level, "name": name, "target_from": c["target_from"],
                             "target_to": c["target_to"], **{f: c[f] for f in CH_COUNT_FIELDS}, "metric": k,
                             "baseline": c["baseline"][k], "new": c["new"][k], "delta": c["delta"][k],
                             "baseline_na_reason": c["baseline"]["na_reasons"].get(k), "new_na_reason": c["new"]["na_reasons"].get(k),
                             "delta_na_reason": c["delta_na_reasons"].get(k)})
    pd.DataFrame(rows).to_csv(out.path("ch_comparison.csv"), index=False, float_format="%.17g")
    pd.DataFrame(common_rows).to_csv(out.path("ch_common_report.csv"), index=False, float_format="%.17g")
    return ["ch_comparison.json", "ch_comparison.csv", "ch_common_report.csv"]


def reference_recipe(tuning):
    """The fixed reference candidate of one horizon (D10), derived from its search recipe: the original quartet's 12
    values, no space; same cohort, gates and scoring."""
    if tuning.get("mode") != "tuning" or tuning.get("candidate_role") != "search":
        raise ValidityError("a reference recipe derives from a search recipe")
    return {**tuning, "candidate_role": "reference", "fixed": {**HPT_FIXED, **HPT_REFERENCE}, "space": {}}


def formal_recipe(tuning, freeze_sha256, index_sha256, winner):
    """The final refit recipe generated from freeze evidence: the search recipe's formal contract (including the final
    model card), the winner's 12 values as fixed settings and the frozen winner record; checked like a job before use."""
    fc = tuning["formal"]
    values = hpt_values(winner["params"])
    who = f"search trial {winner['trial_id']}" if winner["role"] == "search" else "fixed reference quartet"
    out = {k: v for k, v in tuning.items() if k not in ("formal", "candidate_role", "cohort", "baseline", "fixed", "space", "objective")}
    out.update(mode="formal", objective=fc["objective"], fixed={**HPT_FIXED, **values}, space={}, cohort=fc["cohort"],
               baseline=fc["baseline"], comparison=fc["comparison"], dataset_input=fc["dataset_input"], model_card=fc["model_card"],
               frozen={"freeze_sha256": freeze_sha256, "freeze_index_sha256": index_sha256, "winner_role": winner["role"],
                       "winner_trial_id": str(winner["trial_id"]), "params_sha256": digest(values)},
               provenance_tags={**(tuning.get("provenance_tags") or {}), "provenance.hpt_freeze_sha256": freeze_sha256,
                                "provenance.hpt_freeze_index_sha256": index_sha256, "provenance.hpt_winner": who})
    check_hpt_config(out, out["horizon"])
    return out


def verify_freeze_inputs(inputs, config, horizon):
    """Formal prerequisite (D14): the horizon's freeze and the three-horizon freeze index are exactly the recipe's
    pins, the index lists all three horizons and this freeze, and the freeze's winner parameters are the recipe's
    fixed values. Returns the freeze record. No 2026 outcome is read here."""
    from research_cloud.training.common import TrialError, sha256_file
    missing = [r for r in FORMAL_ROLES if r not in inputs]
    if missing:
        raise TrialError(f"formal manifest lacks the roles {missing}")
    fr = config["frozen"]
    pins = {"freeze": fr["freeze_sha256"], "freeze_index": fr["freeze_index_sha256"], **config["comparison"]}
    differ = [r for r in FORMAL_ROLES if sha256_file(inputs[r]) != pins[r]]
    if differ:
        raise TrialError(f"formal inputs differ from the recipe pins: {differ}")
    with open(inputs["freeze"]) as f:
        freeze = json.load(f)
    with open(inputs["freeze_index"]) as f:
        index = json.load(f)
    h, entries = int(horizon), index.get("freezes") or {}
    if (index.get("kind") != FREEZE_INDEX_KIND or index.get("arm") != HPT_ARM or set(entries) != {str(x) for x in HORIZONS}
            or not all(is_sha256((e or {}).get("sha256")) for e in entries.values())):
        raise TrialError("the freeze index must list the freezes of all three horizons")
    winner = freeze.get("winner") or {}
    if (entries[str(h)]["sha256"] != fr["freeze_sha256"] or freeze.get("kind") != FREEZE_KIND or freeze.get("arm") != HPT_ARM
            or freeze.get("horizon") != h or winner.get("role") != fr["winner_role"]
            or str(winner.get("trial_id")) != fr["winner_trial_id"] or winner.get("params") != tuned_values(config, {})):
        raise TrialError("the freeze record does not freeze this recipe's horizon, winner and parameters")
    return freeze


def hpt_prepare(inputs, config, out, schedule):
    """Stage 1 and the pre-fit gates of the tuned arm (never fits): formal freeze prerequisite, build, structure, D7
    resolution, the mode's plans, the pinned cohort counts and the self-consistency digests of exactly those plans
    (tuning: the D7 selection cohorts with their union exclusions; formal: the ordinary annual contexts, whose digests
    equal the selected ACLED baseline's). The tuning build stays in worker scratch (``inputs/``, never published)."""
    from research_cloud.training.common import TrialError
    h, mode = config["horizon"], config["mode"]
    formal = mode == "formal"
    ch = formal and "ch_correction" in config      # task 10-28: CH reference windows added to the label preparation
    freeze = verify_freeze_inputs(inputs, config, h) if formal else None
    built = vf.build_dataset(inputs, out.path("dataset" if formal else "inputs/selection-build/dataset"), horizons=(h,),
                             matrix_dir=out.path("gcs-only/dataset" if formal else "inputs/selection-build/matrices"),
                             keep=True, idp_local=True, acled_agg=True, **({"ch_links": True} if ch else {}))
    objs = built.pop("objects")
    labels, X = select_arm(objs["labels"], objs["horizons"][h]["X"], HPT_ARM)
    order = objs["horizons"][h]["order"]
    if len(order) != config["n_features"]:
        raise TrialError("feature order length differs from the recipe")
    d = ArmData(HPT_ARM, h, labels, X, order, objs["observations"], objs["horizons"][h]["rows"], None, schedule)
    del objs
    n = len(order)
    if (order[n - 3:] != list(vf.IDP_LOCAL_FEATURES) or order[n - 117:n - 3] != list(vf.ACLED_AGG_FEATURES)
            or set(order) & set(vf.OLD_ACLED_FEATURES) or d.core_idx):
        raise TrialError("aggregated-ACLED order: the 114 columns precede the local-IDP suffix, no compact conflict "
                         "column remains and no B2 dynamics are used")
    try:
        plans, excluded = hpt_plans(d, config)
        assertions = plan_assertions(d, plans)
    except ValidityError as e:
        raise TrialError(str(e)) from e
    cohort, scored = config["cohort"], int(sum(len(p["score"]) for p in plans))
    counts = {"scored_rows": scored, "selection_excluded_families": excluded.tolist()}
    if formal:
        counts["holdout_rows"] = int(sum(len(p["score"]) for p in plans if p["block"].role == "supplement"))
        cohort_ok = (scored, counts["holdout_rows"]) == (cohort["final_rows"], cohort["holdout_rows"])
    else:
        counts["removed_scored_rows"] = int(sum(p["removed_scored_rows"] for p in plans))
        cohort_ok = scored == cohort["selection_rows"] and all(
            not np.isin(d.family[p["score"]], excluded).any() and np.isin(excluded, p["S_E"]).all()
            and not np.isin(d.family[p["train"]], excluded).any() for p in plans)
    got = equivalence_digests(d, plans, n)
    corrected = ch_record = None
    if ch:      # task 10-28: CH-correction contract (self-consistency, preservation on common rows, aliases, counts)
        check_equivalence(got, config["baseline"]["equivalence"])     # the GOSIF-v3 reference must still list every key
        try:
            differ, ch_record = ch_gate(d, inputs, config, got, plans, built)
        except ValidityError as e:
            raise TrialError(str(e)) from e
    elif formal and "corrected_input" in config:      # task 10-27: explicit corrected-input contract, never old-feature equality
        check_equivalence(got, config["baseline"]["equivalence"])     # the reference must still list every key
        differ, corrected = corrected_gate(d, inputs, config, got)
    else:
        differ = check_equivalence(got, config["baseline"]["equivalence"])
    out.write_json("equivalence.json", {"arm": HPT_ARM, "horizon": h, "mode": mode, "candidate_role": config.get("candidate_role"),
                                        "kind": baseline_kind(config), "relation": config["baseline"]["relation"], "width": n,
                                        "treatment": got, "differing": differ, "cohort": counts, "cohort_pinned": cohort,
                                        "cohort_passed": bool(cohort_ok), "passed": not differ and bool(cohort_ok),
                                        "stage": "pre-fit", "schedule": schedule.record(),
                                        **({"corrected_input": corrected} if corrected is not None else {}),
                                        **({"ch_correction": ch_record} if ch_record is not None else {})})
    if not cohort_ok:
        raise TrialError(f"{mode} cohort {counts} differs from the pinned {cohort}")
    if differ:
        raise TrialError(f"self-consistency digests differ from the pinned build: {differ}")
    print(f"{mode} gates passed ({scored} scored rows; {len(EQUIVALENCE_KEYS)} digests; D7 families {excluded.tolist()})", flush=True)
    return {"d": d, "order": order, "built": built, "plans": plans, "excluded": excluded, "assertions": assertions,
            "freeze": freeze, "equivalence": got, "kind": baseline_kind(config), "idp": True, "hstack": False, "regional": False}


def lean_metrics(truth_phase, pred_phase, q3_truth, q3_pred, names=SELECTION_METRICS):
    """Only the approved metrics of one cohort (D15), from the pinned metric primitives: binary counts and the fixed
    four-class confusion (``metric_panel``) and the q3-share R2 (``r_squared``). Undefined values are None with their
    reason; negative R2 is kept; the counts are the support. No other metric block is built."""
    m = ae("metrics")
    out = {"n_rows": int(len(truth_phase)), "na_reasons": {}, "support": None}
    if not len(truth_phase):
        out.update({k: None for k in names})
        out["na_reasons"] = {k: "no scored rows" for k in names}
        return out
    panel = m.metric_panel(truth_phase, pred_phase)
    b, f = panel["binary"], panel["four_class"]
    r2, why = m.r_squared(q3_truth, q3_pred)
    values = {"binary_f1": (b["f1"], b["na_reasons"].get("f1")), "binary_f2": (b["f2"], b["na_reasons"].get("f2")),
              "binary_precision": (b["precision"], b["na_reasons"].get("precision")),
              "binary_recall": (b["recall"], b["na_reasons"].get("recall")),
              "macro_f1": (f["macro_f1"], f["na_reasons"].get("macro_f1")), "phase3plus_r2": (r2, why)}
    for k in names:
        v, reason = values[k]
        out[k] = v
        if v is None:
            out["na_reasons"][k] = reason
    out["support"] = {"binary_counts": b["counts"], "four_class_axis": list(FOUR_CLASSES),
                      "four_class_confusion": f["confusion_rows_truth_cols_pred"]}
    return out


SELECTION_KEY_COLUMNS = ("context", "row", "admin_code", "target_ord", "label_kind", "source_family", "phase_truth")


def selection_frame(d: ArmData, E: Block, rows, P, star, phase):
    """Keyed validation rows of one context: lineage, truths, raw backbone, projected uncalibrated quartet, decoded phase."""
    return pd.DataFrame({"horizon": d.horizon, "context": E.block_id, "period": E.role, "row": rows,
                         "admin_code": d.admin[rows], "iso2": d.labels["iso2"].to_numpy()[rows], "target_ord": d.target[rows],
                         "target_month": label(d.target[rows]), "label_kind": d.kind[rows], "source_family": d.family[rows],
                         "source_month_ord": d.labels["source_month_ord"].to_numpy()[rows], "source_available_ord": d.avail[rows],
                         "phase_truth": d.phase[rows], "binary_truth": (d.phase[rows] >= 3).astype(np.int64),
                         **{f"{q}_truth": d.Y[rows, k] for k, q in enumerate(TARGETS)},
                         **{f"{q}_backbone": P[:, k] for k, q in enumerate(TARGETS)},
                         **{f"{q}_star": star[:, k] for k, q in enumerate(TARGETS)},
                         "phase": phase, "binary_pred": (np.asarray(phase) >= 3).astype(np.int64)})


def read_selection_predictions(path):
    """A saved validation frame with exact floats and ISO2 text ('NA' is Namibia, never missing)."""
    return pd.read_csv(path, float_precision="round_trip", keep_default_na=False, na_values=[""], dtype={"iso2": str})


def selection_metrics(pred):
    """The four pooled selection metrics of concatenated annual validation predictions (D9; never annual means)."""
    return lean_metrics(pred["phase_truth"].to_numpy(np.int64), pred["phase"].to_numpy(np.int64),
                        pred["q3_truth"].to_numpy(np.float64), pred["q3_star"].to_numpy(np.float64), SELECTION_METRICS)


def hpt_tune(prep, config, values, quartet, out, t0, log=print):
    """One search/reference candidate: fit every main context once on its D7 plan with the resolved quartet, keep the
    keyed validation predictions and four pooled metrics (recomputed from the saved file), and no model."""
    d, plans, excluded = prep["d"], prep["plans"], prep["excluded"]
    frames, contexts = [], {}
    for p in plans:
        E, train, score = p["block"], p["train"], p["score"]
        fit = run_fit(d, "backbone", E, train, score, p["S_E"], E.cutoff, quartet=quartet)
        hs = fit["history"]
        hits = {"fitting_labels": int(np.isin(d.family[train], excluded).sum()), "scored_rows": int(np.isin(d.family[score], excluded).sum()),
                "fitting_history": int(np.isin(hs["train_fam"], excluded).sum()), "scoring_history": int(np.isin(hs["pred_fam"], excluded).sum())}
        if any(hits.values()):
            raise ValidityError(f"{E.block_id}: a selection-excluded family reaches the candidate {hits}")
        star, phase = ae("projection").project_and_decode(fit["P"])
        frames.append(selection_frame(d, E, score, fit["P"], star, phase))
        contexts[E.block_id] = {
            "block": E.record(), "cutoff": label(E.cutoff), "train_rows": int(len(train)), "score_rows": int(len(score)),
            "removed_scored_rows": p["removed_scored_rows"], "union_families": int(len(p["S_E"])),
            "union_sha256": array_digest(np.asarray(p["S_E"], np.int64)),
            "selected_families_sha256": array_digest(np.asarray(p["selected_families"], np.int64)),
            "train_keys_sha256": keys_sha256(d, train), "score_keys_sha256": keys_sha256(d, score),
            "history_sha256": {"train": digest([array_digest(hs["train_src"]), array_digest(hs["train_fam"])]),
                               "score": digest([array_digest(hs["pred_src"]), array_digest(hs["pred_fam"])])},
            "excluded_family_hits": hits, "fit": {k: v for k, v in fit["record"].items() if k != "block"}}
        log(f"[{time.time() - t0:7.0f}s] {E.block_id}: train {len(train)} scored {len(score)} (D7 removed {p['removed_scored_rows']})")
    pred = pd.concat(frames, ignore_index=True)
    path = out.path("cv/validation_predictions.csv.gz")
    pred.to_csv(path, index=False, float_format="%.17g")
    pooled, again = selection_metrics(pred), selection_metrics(read_selection_predictions(path))
    if any(again[k] != pooled[k] for k in (*SELECTION_METRICS, "n_rows")):
        raise ValidityError("selection metrics recomputed from the saved predictions differ")
    if pooled["n_rows"] != config["cohort"]["selection_rows"]:
        raise ValidityError(f"{pooled['n_rows']} selection rows, not the pinned {config['cohort']['selection_rows']}")
    role = config["candidate_role"]
    out.write_json("cv/metrics.json", {"objective": HPT_OBJECTIVE, "value": pooled["binary_f1"], "order": list(SELECTION_METRICS),
                                       "metrics": {k: pooled[k] for k in SELECTION_METRICS}, "n_rows": pooled["n_rows"],
                                       "na_reasons": pooled["na_reasons"], "support": pooled["support"],
                                       "definitions": {k: METRIC_DEFINITIONS[k] for k in (*SELECTION_METRICS, "n_rows")},
                                       "pooling": "concatenated annual validation predictions; one value per candidate",
                                       "candidate_role": role, "params": values, "quartet": quartet})
    out.write_json("cv/folds.json", {"kind": "D7 selection contexts (main years only; the 2026 supplement is never fitted or scored)",
                                     "arm": HPT_ARM, "horizon": d.horizon, "candidate_role": role,
                                     "selection_excluded": config["cohort"]["excluded_families"], "rows": pooled["n_rows"],
                                     "contexts": contexts, "assertions": prep["assertions"], "equivalence": prep["equivalence"],
                                     "schedule": d.schedule.record(), "feature_order_sha256": vf.list_sha256(d.order),
                                     "n_features": len(d.order), "dataset": prep["built"], "params": values, "quartet": quartet})
    metrics = {f"selection.{k}": float(pooled[k]) for k in SELECTION_METRICS if pooled[k] is not None}
    metrics["selection.n_rows"] = float(pooled["n_rows"])
    return {"metrics": metrics, "artifacts": ["cv", "equivalence.json"], "trial_code": code_identity(),
            "identity": {"family": FAMILY, "kind": "tracking-only selection candidate (no retained model)", "mode": "tuning",
                         "candidate_role": role, "arm": HPT_ARM, "horizon": d.horizon, "contexts": list(contexts),
                         "selection_rows": pooled["n_rows"], "scalar_fits": 4 * len(plans), "params": values,
                         "quartet_sha256": digest(quartet), "elapsed_seconds": round(time.time() - t0, 1)}}


def hpt_scopes(schedule, horizon):
    """Formal report scopes (D15): the pooled historical window, each historical year (partial windows respected) and
    the 2026-01..10 supplement once; 2026 never enters a historical scope."""
    h = int(horizon)
    first, last = parse_month(schedule.first(h)), parse_month(schedule.main_last)
    out = [{"scope": "historical_pooled", "period": "main", "lo": first, "hi": last}]
    out += [{"scope": f"historical_{y}", "period": "main", "lo": max(first, y * 12), "hi": min(last, y * 12 + 11)}
            for y in range(first // 12, last // 12 + 1)]
    s0, s1 = schedule.supplement
    return out + [{"scope": holdout_name(s0, s1), "period": "supplement", "lo": parse_month(s0), "hi": parse_month(s1)}]


def hpt_comparison(new_pred, baseline_path, region_path, schedule, horizon, baseline):
    """Six metrics + n for the new model, the selected ACLED baseline and their delta per scope, on exactly paired keys
    (``paired_rows``: one-to-one keys, equal truths/periods, mapped areas; never an intersection)."""
    m = paired_rows(new_pred, baseline_path, region_path)
    t, role = m["target_ord"].to_numpy(np.int64), m["period"].to_numpy()
    cells, scopes = {}, hpt_scopes(schedule, horizon)
    for s in scopes:
        f = m[(role == s["period"]) & (t >= s["lo"]) & (t <= s["hi"])]
        T, q3 = f["phase_truth"].to_numpy(np.int64), f["q3_truth"].to_numpy(np.float64)
        new = lean_metrics(T, f["phase"].to_numpy(np.int64), q3, f["q3_star"].to_numpy(np.float64), FORMAL_METRICS)
        old = lean_metrics(T, f["phase_uncal"].to_numpy(np.int64), q3, f["q3_star_uncal"].to_numpy(np.float64), FORMAL_METRICS)
        delta, why = {}, {}
        for k in FORMAL_METRICS:
            delta[k] = None if new[k] is None or old[k] is None else float(new[k]) - float(old[k])
            if delta[k] is None:
                why[k] = "; ".join(f"{side} undefined: {b['na_reasons'][k]}" for side, b in (("baseline", old), ("new", new)) if b[k] is None)
        cells[s["scope"]] = {"target_from": label(s["lo"]), "target_to": label(s["hi"]), "n_rows": int(len(f)),
                             "original_rows": int((f["label_kind"] == "original").sum()), "copy_rows": int((f["label_kind"] == "copy").sum()),
                             "new": new, "baseline": old, "delta": delta, "delta_na_reasons": why}
    years = sum(cells[s["scope"]]["n_rows"] for s in scopes if s["scope"].startswith("historical_2"))
    hist, hold = cells["historical_pooled"]["n_rows"], cells[scopes[-1]["scope"]]["n_rows"]
    if years != hist or hist + hold != len(m):
        raise ValidityError(f"scope rows do not add up: years {years}, historical {hist}, holdout {hold}, paired {len(m)}")
    return {"kind": "acledagg_hpt_comparison", "arm": HPT_ARM, "horizon": int(horizon), "baseline": baseline,
            "pairing": {"keys": list(PAIR_KEYS), "rows": int(len(m)), "unmatched": 0, "truth_mismatches": 0,
                        "originals": int((m["label_kind"] == "original").sum()), "copies": int((m["label_kind"] == "copy").sum())},
            "region_map": {"sha256": REGION_MAPPING_SHA256, "retained": "region_mapping.csv"},
            "scopes": [{**s, "lo": label(s["lo"]), "hi": label(s["hi"])} for s in scopes], "metrics": list(FORMAL_METRICS),
            "definitions": {k: METRIC_DEFINITIONS[k] for k in (*FORMAL_METRICS, "n_rows")}, "cells": cells,
            "semantics": "augmented rows, unweighted; baseline = the selected ACLED run's delivered (uncalibrated) outputs; "
                         "delta = new - baseline; undefined values are null with their reason"}


def hpt_comparison_metrics(comp):
    """Finite MLflow scalars: ``<scope>.<metric>``, ``<scope>.baseline.<metric>``, ``<scope>.delta_vs_baseline.<metric>``
    and ``<scope>.n_rows``."""
    out = {}
    for scope, cell in comp["cells"].items():
        out[f"{scope}.n_rows"] = float(cell["n_rows"])
        for k in FORMAL_METRICS:
            for key, v in ((f"{scope}.{k}", cell["new"][k]), (f"{scope}.baseline.{k}", cell["baseline"][k]),
                           (f"{scope}.delta_vs_baseline.{k}", cell["delta"][k])):
                if isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v):
                    out[key] = float(v)
    return out


def write_hpt_comparison(out, comp):
    """lean_comparison.json (null for undefined), lean_comparison.csv (scope x metric) and lean_confusion.csv (binary
    2x2 and four-class 4x4 per scope)."""
    with open(out.path("lean_comparison.json"), "w") as f:
        f.write(json.dumps(comp, indent=1, allow_nan=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    rows, conf = [], []
    for scope, c in comp["cells"].items():
        base = {"horizon": comp["horizon"], "scope": scope, "target_from": c["target_from"], "target_to": c["target_to"],
                "n_rows": c["n_rows"], "original_rows": c["original_rows"], "copy_rows": c["copy_rows"],
                "baseline_run_id": comp["baseline"]["run_id"]}
        for k in FORMAL_METRICS:
            rows.append({**base, "metric": k, "baseline": c["baseline"][k], "new": c["new"][k], "delta": c["delta"][k],
                         "baseline_na_reason": c["baseline"]["na_reasons"].get(k), "new_na_reason": c["new"]["na_reasons"].get(k),
                         "delta_na_reason": c["delta_na_reasons"].get(k)})
        sb, sn = c["baseline"]["support"] or {}, c["new"]["support"] or {}
        for name, (i, j) in (("tn", (0, 0)), ("fp", (0, 1)), ("fn", (1, 0)), ("tp", (1, 1))):
            o, n = (sb.get("binary_counts") or {}).get(name, 0), (sn.get("binary_counts") or {}).get(name, 0)
            conf.append({"horizon": comp["horizon"], "scope": scope, "matrix": "binary", "truth": i, "prediction": j,
                         "baseline": o, "new": n, "diff": n - o})
        zero = [[0] * 4 for _ in range(4)]
        co, cn = sb.get("four_class_confusion") or zero, sn.get("four_class_confusion") or zero
        for i, tc in enumerate(FOUR_CLASSES):
            for j, pc in enumerate(FOUR_CLASSES):
                conf.append({"horizon": comp["horizon"], "scope": scope, "matrix": "four_class", "truth": tc, "prediction": pc,
                             "baseline": co[i][j], "new": cn[i][j], "diff": cn[i][j] - co[i][j]})
    pd.DataFrame(rows).to_csv(out.path("lean_comparison.csv"), index=False, float_format="%.17g")
    pd.DataFrame(conf).to_csv(out.path("lean_confusion.csv"), index=False)
    return ["lean_comparison.json", "lean_comparison.csv", "lean_confusion.csv"]


REPORT_TEMPORAL_YEARS = (2023, 2024, 2025)


def corrected_report(pred, map_path, schedule, horizon, spec):
    """Task 10-27 report tables (PRD R6-R8, R10) from this run's keyed predictions and the pinned report-only region map
    (never a model input; the frozen map stays the inherited pairing artifact): every report region x {primary,
    holdout}, and all regions / the Somalia subset (country identity) x {2023, 2024, 2025, holdout}. Rows are pooled
    unweighted (originals and validity copies alike); declared windows are listed beside the observed first/last target
    months; an empty declared window (H12 2023) is NA with an explicit reason. Returns (rows, finite MLflow scalars)."""
    h = int(horizon)
    regions = pd.read_csv(map_path)
    names = {int(k): v for k, v in spec["regions"].items()}
    if list(regions.columns) != ["area_id", "region"] or regions["area_id"].duplicated().any() \
            or not regions["region"].isin(list(names)).all():
        raise ValidityError("report region map must be unique area_id -> a declared report region")
    f = pred[["admin_code", "iso2", "target_ord", "period", "label_kind", "phase_truth", "phase", "q3_truth", "q3_star"]].copy()
    f["report_region"] = f["admin_code"].map(regions.set_index("area_id")["region"])
    if f["report_region"].isna().any():
        raise ValidityError(f"{int(f['report_region'].isna().sum())} scored rows have no report region")
    t, per = f["target_ord"].to_numpy(np.int64), f["period"].to_numpy()
    first, last = parse_month(schedule.first(h)), parse_month(schedule.main_last)
    s0, s1 = (parse_month(m) for m in schedule.supplement)
    rows, scalars = [], {}

    def cell(table, subset, scope, sel, lo, hi, why=None):
        g = f[sel]
        m = lean_metrics(g["phase_truth"].to_numpy(np.int64), g["phase"].to_numpy(np.int64), g["q3_truth"].to_numpy(np.float64),
                         g["q3_star"].to_numpy(np.float64), FORMAL_METRICS)
        reasons = {k: why for k in FORMAL_METRICS} if why else m["na_reasons"]
        row = {"horizon": h, "table": table, "subset": subset, "scope": scope,
               "declared_from": label(lo) if lo is not None else None, "declared_to": label(hi) if hi is not None else None,
               "observed_from": label(int(g["target_ord"].min())) if len(g) else None,
               "observed_to": label(int(g["target_ord"].max())) if len(g) else None,
               "n_rows": int(len(g)), "original_rows": int((g["label_kind"] == "original").sum()),
               "copy_rows": int((g["label_kind"] == "copy").sum()),
               **{k: m[k] for k in FORMAL_METRICS}, "na_reasons": reasons}
        rows.append(row)
        key = f"report.{table}.{subset.lower().replace(' ', '_')}.{scope}"
        scalars[f"{key}.n_rows"] = float(len(g))
        for k in FORMAL_METRICS:
            v = m[k]
            if isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v):
                scalars[f"{key}.{k}"] = float(v)

    for p, (role, lo, hi) in (("primary", ("main", first, last)), ("holdout", ("supplement", s0, s1))):
        for r in sorted(names):
            cell("region", names[r], p, ((f["report_region"].to_numpy() == r) & (per == role) & (t >= lo) & (t <= hi)), lo, hi)
        if sum(x["n_rows"] for x in rows if x["table"] == "region" and x["scope"] == p) != int(((per == role) & (t >= lo) & (t <= hi)).sum()):
            raise ValidityError(f"report regions do not partition the {p} rows")
    somalia = f["iso2"].to_numpy() == spec["somalia_iso2"]
    for subset, base in (("All regions", np.ones(len(f), dtype=bool)), ("Somalia", somalia)):
        for y in REPORT_TEMPORAL_YEARS:
            lo, hi = max(first, y * 12), min(last, y * 12 + 11)
            if lo > hi:
                cell("temporal", subset, str(y), np.zeros(len(f), dtype=bool), None, None,
                     f"no evaluation rows: {y} precedes the H{h} historical window starting {label(first)}")
            else:
                cell("temporal", subset, str(y), base & (per == "main") & (t >= lo) & (t <= hi), lo, hi)
        cell("temporal", subset, "holdout", base & (per == "supplement") & (t >= s0) & (t <= s1), s0, s1)
    return rows, scalars


def write_corrected_report(out, rows, spec, map_path):
    """report_tables.json/.csv (one row per cell, NA reasons kept) and the pinned report map, distinct from the frozen
    pairing map ``region_mapping.csv``."""
    import shutil
    shutil.copyfile(map_path, out.path("report_region_mapping.csv"))
    with open(out.path("report_tables.json"), "w") as f:
        f.write(json.dumps({"kind": "corrected_input_report", "regions": spec["regions"], "somalia_iso2": spec["somalia_iso2"],
                            "metrics": list(FORMAL_METRICS), "definitions": {k: METRIC_DEFINITIONS[k] for k in (*FORMAL_METRICS, "n_rows")},
                            "region_map": "report_region_mapping.csv (report-only; region_mapping.csv is the frozen pairing map)",
                            "rows": rows}, indent=1, allow_nan=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    flat = [{**{k: v for k, v in r.items() if k != "na_reasons"},
             **{f"{k}_na_reason": r["na_reasons"].get(k) for k in FORMAL_METRICS}} for r in rows]
    pd.DataFrame(flat).to_csv(out.path("report_tables.csv"), index=False, float_format="%.17g")
    return ["report_tables.json", "report_tables.csv", "report_region_mapping.csv"]


def hpt_caveat(h, schedule, corrected=None):
    if corrected is not None:      # task 10-27: the frozen parameters on a corrected GPP input (never "every input equal")
        return (f"Corrected-input refit of the tuned aggregated-ACLED arm, lead {h} ({corrected['data_version']}): the q3 "
                "and shared q2/q4/q5 parameters are the ones frozen by the original search for this horizon, unchanged and "
                "not re-tuned. The interim panel's GPP_mean/GPP_std columns were replaced by zonal means of the official "
                "GOSIF-GPP v3 monthly Mean/SD rasters (all years and areas; no old-series fallback), so the 13 GPP_mean-derived "
                "features differ from the original run. Labels, validity copies, report families, histories, contexts, cutoffs, "
                "weights, every other feature column (values and missingness) and the identity calibration equal the original "
                "formal run (verified before fitting). Historical results were inspected during the original tuning and are "
                "descriptive, not an independent test; 2026-01..10 outcomes were already inspected; the inputs are retrospective "
                "vintages. One seed; no significance or causal claim.")
    return (f"Tuned candidate of the aggregated-ACLED arm, lead {h}: the q3 group and the shared q2/q4/q5 group of the "
            f"quartet were searched separately for this horizon (Vertex, binary-F1 objective) on {schedule.first(h)}.."
            f"{schedule.main_last} historical validation with two cross-window report families excluded, ranked by binary "
            "F1, phase3plus R2, macro F1 and "
            "binary F2 against the fixed quartet, and frozen for all three horizons before this refit. Every input, feature, "
            "context, cutoff, weight and the identity calibration equal the selected ACLED run (verified before fitting); "
            "only the quartet parameters differ. Historical results after tuning are descriptive, not an independent test, "
            "and 2026-01..10 outcomes were already inspected for the baseline. One seed; no significance or causal claim.")


def ch_caveat(h, cc):
    """Runtime caveat of a CH-correction refit (task 10-28); never the GPP-only feature-preservation sentence."""
    return (f"CH validity-correction refit of the tuned aggregated-ACLED arm, lead {h} ({cc['data_version']}): the q3 and shared "
            "q2/q4/q5 parameters, seed, weights, calendar, identity calibration and the GOSIF-v3 corrected inputs are those of the "
            f"GOSIF-v3 run {cc['gpp_baseline']['run_id']} (not re-tuned). Cadre Harmonise current reference windows (Jan-May, "
            "Jun-Aug, Sep-Dec; CAF and projected rows excluded) now fill existing blank area-months of the same country as copies "
            "of the existing CH label; 150 May-2026 rows stored raw are reclassified as copies of their Jan-May report; preserved "
            "cross-country labels are not expanded and carry their source report family for exclusions. Label support, report "
            "families, histories, cohorts and fitting rows therefore differ from the GOSIF-v3 run, while existing label values and "
            "every non-history feature value on the GOSIF-v3 rows are unchanged (verified before fitting). Copies use the "
            "reference-window start month as their nominal source/availability month - a retrospective modeling convention, not a "
            "verified publication date, so this is not a strict real-time forecast. Unresolved, ambiguous or cross-country source "
            "routes stay unexpanded. Historical results were inspected during the original tuning and are descriptive; "
            "2026-01..10 outcomes were already inspected; comparisons with the GOSIF-v3 run on common keys are descriptive, not "
            "an isolated model effect. One seed; no significance or causal claim.")


def ch_scope_metrics(pred, schedule, horizon):
    """This run's six metrics and counts per formal scope on its whole (augmented) scored population."""
    t, role = pred["target_ord"].to_numpy(np.int64), pred["period"].to_numpy()
    out, cells = {}, {}
    for s in hpt_scopes(schedule, horizon):
        f = pred[(role == s["period"]) & (t >= s["lo"]) & (t <= s["hi"])]
        m = lean_metrics(f["phase_truth"].to_numpy(np.int64), f["phase"].to_numpy(np.int64), f["q3_truth"].to_numpy(np.float64),
                         f["q3_star"].to_numpy(np.float64), FORMAL_METRICS)
        cells[s["scope"]] = {"n_rows": int(len(f)), "original_rows": int((f["label_kind"] == "original").sum()),
                             "copy_rows": int((f["label_kind"] == "copy").sum()), **{k: m[k] for k in FORMAL_METRICS},
                             "na_reasons": m["na_reasons"]}
        out[f"{s['scope']}.n_rows"] = float(len(f))
        for k in FORMAL_METRICS:
            if isinstance(m[k], (int, float)) and not isinstance(m[k], bool) and np.isfinite(m[k]):
                out[f"{s['scope']}.{k}"] = float(m[k])
    return out, cells


def ch_common_metrics(comp):
    """``common.<scope>.<metric>`` (new), ``common.<scope>.baseline.<metric>``, ``common.<scope>.delta_vs_baseline.<metric>``
    and ``common.<scope>.n_rows`` on the common support (never the unprefixed whole-population keys)."""
    out = {}
    for scope, cell in comp["cells"].items():
        out[f"common.{scope}.n_rows"] = float(cell["n_rows"])
        for k in FORMAL_METRICS:
            for key, v in ((f"common.{scope}.{k}", cell["new"][k]), (f"common.{scope}.baseline.{k}", cell["baseline"][k]),
                           (f"common.{scope}.delta_vs_baseline.{k}", cell["delta"][k])):
                if isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v):
                    out[key] = float(v)
    return out


def ch_formal(prep, inputs, manifest, config, values, quartet, out, t0):
    """Task 10-28 final refit with the CH correction: every annual context with the GOSIF-v3 run's frozen quartet, the
    whole-population scope metrics and inherited report tables, the common-support comparison and report cells against
    the GOSIF-v3 run's retained predictions, and the identity package (no B2 inputs)."""
    import shutil
    from research_cloud.packages import validity_pooled
    from research_cloud.training.common import runtime_identity
    from research_cloud.training.model_metadata import BASELINE_KEYS
    d, cc = prep["d"], config["ch_correction"]
    h = d.horizon
    result = run_contexts(d, out.local, quartet=quartet)
    pred = result["predictions"]
    if len(pred) != config["cohort"]["final_rows"]:
        raise ValidityError(f"{len(pred)} final rows, not the pinned {config['cohort']['final_rows']}")
    baseline = {k: config["baseline"][k] for k in BASELINE_KEYS}
    comp, frames = ch_comparison(pred, inputs["baseline_predictions"], d.schedule, h, baseline)
    common_rows, common_scalars = ch_common_report(frames, inputs[REPORT_ROLE], d.schedule, h, cc["report"], pred)
    files = write_ch_comparison(out, comp, common_rows)
    rows, report_scalars = corrected_report(pred, inputs[REPORT_ROLE], d.schedule, h, cc["report"])
    report_files = write_corrected_report(out, rows, cc["report"], inputs[REPORT_ROLE])
    shutil.copyfile(inputs["region_mapping"], out.path("region_mapping.csv"))
    metrics, scope_cells = ch_scope_metrics(pred, d.schedule, h)
    for extra in (ch_common_metrics(comp), report_scalars, common_scalars):
        clash = sorted(set(extra) & set(metrics))
        if clash:
            raise ValidityError(f"metric keys collide: {clash[:5]}")
        metrics.update(extra)
    metrics["scored_rows"], metrics["scalar_fits"] = float(len(pred)), float(4 * len(result["fit_ledger"]))
    info = {"kind": cc["kind"], "data_version": cc["data_version"], "relation": cc["relation"], "gpp_baseline": cc["gpp_baseline"],
            "report": cc["report"], "interim_sha256": cc["inputs"]["interim"], "ch_links_sha256": cc["inputs"][vf.CH_LINKS_ROLE],
            "counts": prep["built"].get("ch_correction"), "report_files": report_files, "comparison_files": files}
    out.write_json("metrics.json", {"arm": HPT_ARM, "horizon": h, "mode": "formal", "params": values, "quartet": quartet,
                                    "frozen": config["frozen"], "freeze": prep["freeze"], "schedule": d.schedule.record(),
                                    "assertions": result["assertions"], "dataset": prep["built"], "caveat": ch_caveat(h, cc),
                                    "scopes": scope_cells,
                                    "comparison": {"files": files, "pairing": comp["pairing"], "baseline": baseline, "scopes": comp["scopes"]},
                                    "ch_correction": info})
    identity = {"family": FAMILY, "arm": HPT_ARM, "horizon": h, "mode": "formal", "trial": os.environ.get("CLOUD_ML_TRIAL_ID"),
                "job": os.environ.get("CLOUD_ML_JOB_ID"), "fixed": config["fixed"], "quartet": quartet, "frozen": config["frozen"],
                "input_manifest": manifest, "trial_code": code_identity(), "ch_correction": info}
    meta = validity_pooled.build(out.path("package"), units=result["units"], order=d.order, identity=identity,
                                 runtime=runtime_identity(), ae_src=vf.ae_source(), core_inputs=d.core_inputs,
                                 calibration_note={"mode": "identity", "b2": "disabled by design (no B2 or provider fits)",
                                                   "raw": "equals the backbone quartet before projection and 0.20 decoding"})
    return {"metrics": metrics,
            "artifacts": ["dataset", "contexts", "predictions.csv.gz", "package", "gcs-only", "equivalence.json", "region_mapping.csv",
                          *files, *report_files],
            "trial_code": code_identity(),
            "package": {"path": "package", "content_sha256": meta["content_sha256"], "units": meta["fitted_units"]},
            "identity": {"family": FAMILY, "kind": "new Linux research run", "mode": "formal", "arm": HPT_ARM, "horizon": h,
                         "contexts": [u["context"].block_id for u in result["units"]], "scalar_fits": 4 * len(result["fit_ledger"]),
                         "params": values, "quartet_sha256": digest(quartet), "frozen": config["frozen"],
                         "data_version": cc["data_version"], "interim_sha256": cc["inputs"]["interim"],
                         "ch_links_sha256": cc["inputs"][vf.CH_LINKS_ROLE], "elapsed_seconds": round(time.time() - t0, 1)}}


def hpt_formal(prep, inputs, manifest, config, values, quartet, out, t0):
    """Final refit: every annual context of the ordinary plan (D7 selection mask restored, inherited exclusions kept)
    with the frozen quartet, lean six-metric comparison with the selected ACLED baseline, retained keyed predictions and
    region map, and the identity package (no B2 inputs)."""
    from research_cloud.packages import validity_pooled
    from research_cloud.training.common import runtime_identity
    from research_cloud.training.model_metadata import BASELINE_KEYS
    d = prep["d"]
    h = d.horizon
    result = run_contexts(d, out.local, quartet=quartet)
    pred = result["predictions"]
    baseline = {k: config["baseline"][k] for k in BASELINE_KEYS}
    comp = hpt_comparison(pred, inputs["baseline_predictions"], inputs["region_mapping"], d.schedule, h, baseline)
    files = write_hpt_comparison(out, comp)
    if comp["pairing"]["rows"] != config["cohort"]["final_rows"]:
        raise ValidityError(f"{comp['pairing']['rows']} final rows, not the pinned {config['cohort']['final_rows']}")
    import shutil
    shutil.copyfile(inputs["region_mapping"], out.path("region_mapping.csv"))
    metrics = hpt_comparison_metrics(comp)
    metrics["scored_rows"], metrics["scalar_fits"] = float(len(pred)), float(4 * len(result["fit_ledger"]))
    ci = config.get("corrected_input")
    report_files = []
    if ci is not None:      # task 10-27: report tables on the report-only map (MLflow-visible as report.* scalars)
        rows, scalars = corrected_report(pred, inputs[REPORT_ROLE], d.schedule, h, ci["report"])
        report_files = write_corrected_report(out, rows, ci["report"], inputs[REPORT_ROLE])
        metrics.update(scalars)
    corrected = None if ci is None else {k: ci[k] for k in ("kind", "data_version", "replaced_role", "original_inputs", "changed_columns",
                                                           "original_run", "relation", "report")} | {"interim_sha256": ci["inputs"]["interim"],
                                                                                                "report_files": report_files}
    out.write_json("metrics.json", {"arm": HPT_ARM, "horizon": h, "mode": "formal", "params": values, "quartet": quartet,
                                    "frozen": config["frozen"], "freeze": prep["freeze"], "schedule": d.schedule.record(),
                                    "assertions": result["assertions"], "dataset": prep["built"], "caveat": hpt_caveat(h, d.schedule, ci),
                                    "comparison": {"files": files, "pairing": comp["pairing"], "baseline": baseline,
                                                   "scopes": comp["scopes"]},
                                    **({"corrected_input": corrected} if corrected is not None else {})})
    identity = {"family": FAMILY, "arm": HPT_ARM, "horizon": h, "mode": "formal", "trial": os.environ.get("CLOUD_ML_TRIAL_ID"),
                "job": os.environ.get("CLOUD_ML_JOB_ID"), "fixed": config["fixed"], "quartet": quartet, "frozen": config["frozen"],
                "input_manifest": manifest, "trial_code": code_identity(), **({"corrected_input": corrected} if corrected is not None else {})}
    meta = validity_pooled.build(out.path("package"), units=result["units"], order=d.order, identity=identity,
                                 runtime=runtime_identity(), ae_src=vf.ae_source(), core_inputs=d.core_inputs,
                                 calibration_note={"mode": "identity", "b2": "disabled by design (no B2 or provider fits)",
                                                   "raw": "equals the backbone quartet before projection and 0.20 decoding"})
    return {"metrics": metrics,
            "artifacts": ["dataset", "contexts", "predictions.csv.gz", "package", "gcs-only", "equivalence.json", "region_mapping.csv", *files,
                          *report_files],
            "trial_code": code_identity(),
            "package": {"path": "package", "content_sha256": meta["content_sha256"], "units": meta["fitted_units"]},
            "identity": {"family": FAMILY, "kind": "new Linux research run", "mode": "formal", "arm": HPT_ARM, "horizon": h,
                         "contexts": [u["context"].block_id for u in result["units"]], "scalar_fits": 4 * len(result["fit_ledger"]),
                         "params": values, "quartet_sha256": digest(quartet), "frozen": config["frozen"],
                         **({"data_version": corrected["data_version"], "interim_sha256": corrected["interim_sha256"]}
                            if corrected is not None else {}),
                         "elapsed_seconds": round(time.time() - t0, 1)}}


def hpt_fit(inputs, manifest, config, params, out):
    """The tuned arm's job: gates, then one search/reference candidate (tuning) or the frozen final refit (formal)."""
    t0 = time.time()
    prep = prepare(inputs, config, out, manifest)
    values = tuned_values(config, params)
    quartet = hpt_quartet(values)
    if config["mode"] == "tuning":
        return hpt_tune(prep, config, values, quartet, out, t0)
    if "ch_correction" in config:      # task 10-28
        return ch_formal(prep, inputs, manifest, config, values, quartet, out, t0)
    return hpt_formal(prep, inputs, manifest, config, values, quartet, out, t0)


def fit(inputs, manifest, config, params, out):
    if config.get("arm") == HPT_ARM:
        return hpt_fit(inputs, manifest, config, params, out)
    t0 = time.time()
    prep = prepare(inputs, config, out, manifest)
    d, order, built = prep["d"], prep["order"], prep["built"]
    arm, h, idp, hstack, regional = d.arm, d.horizon, prep["idp"], prep["hstack"], prep["regional"]
    acled = arm in ACLED_ARMS
    result = run_contexts(d, out.local)
    ev = evaluate(result["predictions"], d.schedule)
    periods, prim = metric_periods(ev, d.schedule)
    metrics = mlflow_metrics(periods)
    if d.schedule.declared:      # the uncalibrated backbone's pooled primary crisis F1 (other blocks in metrics.json)
        f1 = ev["by_period_uncalibrated"].get(prim, {}).get("binary.f1")
        if isinstance(f1, (int, float)) and np.isfinite(f1):
            metrics["primary.all_scored_uncalibrated.binary.f1"] = float(f1)
    metrics["scored_rows"] = float(len(result["predictions"]))
    metrics["scalar_fits"] = float(4 * len(result["fit_ledger"]))
    comparison_files = []
    if acled:      # task 10-20: paired old/new/delta for all_scored and the nine regions, written before finalization
        with open(inputs["acled_baseline_reference"]) as f:
            baseline = json.load(f)["baseline"]
        comp = paired_comparison(result["predictions"], inputs["baseline_predictions"], inputs["region_mapping"], d.schedule, h, baseline)
        comparison_files = write_comparison(out, comp)
        extra = comparison_metrics(comp)
        clash = sorted(k for k in set(extra) & set(metrics) if extra[k] != metrics[k])
        if clash:
            raise ValidityError(f"comparison values differ from the run's own metrics: {clash[:5]}")
        metrics.update(extra)
    caveat = (acled_caveat(d.schedule) if acled else refresh_caveat(arm, d.schedule) if arm in REFRESH_ARMS else
              f"Regional local model: the {arm} arm restricted to {config['region']['name']} ({', '.join(config['region']['iso2'])}) "
              "for training, providers, calibration and scoring; rows and features equal the pooled baseline restricted to the "
              "region (verified before fitting). Fixed learner, retrospective data, one seed; no causal or significance claim."
              if regional else
              "Same keyed cohort as the validity_augmented_idp baseline (verified before fitting); a same-cohort ablation adding "
              "the same arm's longer-horizon origin blocks under a fixed learner, retrospective data and one seed; no causal or "
              "significance claim." if hstack else
              "Same keyed cohort as the validity_augmented baseline (verified before fitting); a same-cohort ablation of "
              "three local-IDP columns under a fixed learner, retrospective data and one seed; no causal or significance claim."
              if idp else "Samples differ between arms; metrics generally are not directly comparable. "
                          "This is a descriptive augmentation comparison, not an isolated augmentation effect.")
    out.write_json("metrics.json", {"arm": arm, "horizon": h, **ev, "dataset": built, "caveat": caveat,
                                    **({"schedule": d.schedule.record(), "assertions": result["assertions"],
                                        "metric_periods": {k: ("by_period", prim if k == "primary" else "supplement" if k == "holdout" else k)
                                                           for k in periods}} if d.schedule.declared else {}),
                                    **({"comparison": {"files": comparison_files, "pairing": comp["pairing"],
                                                       "accounting": comp["accounting"], "baseline": comp["baseline"]}} if acled else {})})
    from research_cloud.packages import validity_pooled
    from research_cloud.training.common import runtime_identity
    identity = {"family": FAMILY, "arm": arm, "horizon": h, "trial": os.environ.get("CLOUD_ML_TRIAL_ID"),
                "job": os.environ.get("CLOUD_ML_JOB_ID"), "fixed": fixed_settings(arm), "input_manifest": manifest,
                "trial_code": code_identity()}
    meta = validity_pooled.build(out.path("package"), units=result["units"], order=order, identity=identity,
                                 runtime=runtime_identity(), ae_src=vf.ae_source(), core_inputs=d.core_inputs,
                                 **({"calibration_note": {"mode": "identity", "b2": "disabled by design (no B2 or provider fits)",
                                                          "raw": "equals the backbone quartet before projection and 0.20 decoding"}}
                                    if acled else {}))
    return {"metrics": metrics, "artifacts": ["dataset", "contexts", "predictions.csv.gz", "package", "gcs-only"] + (["equivalence.json"] if idp or hstack or regional else [])
            + (["paired_gate.json", *comparison_files] if acled else []),
            "trial_code": code_identity(),
            "package": {"path": "package", "content_sha256": meta["content_sha256"], "units": meta["fitted_units"]},
            "identity": {"family": FAMILY, "kind": "new Linux research run", "arm": arm, "horizon": h,
                         "contexts": [u["context"].block_id for u in result["units"]],
                         "scalar_fits": 4 * len(result["fit_ledger"]), "elapsed_seconds": round(time.time() - t0, 1)}}

def code_identity():
    from research_cloud.training.common import adapter_identity, sha256_file
    src = vf.ae_source()
    files = {f"ipcch_alphaearth/{m}.py": sha256_file(os.path.join(src, "ipcch_alphaearth", f"{m}.py"))
             for m in ("__init__", "errors", "months", "compact", "targets", "correction", "projection", "metrics")}
    return {"ae_src": os.path.abspath(src), "files": files,
            "adapter": adapter_identity("research_cloud.training.ipcch_validity_pooled", "research_cloud.training.ipcch_validity_features",
                                        "research_cloud.packages.validity_pooled", "research_cloud.training.common")}


def plan_main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="No-fit context/provider enumeration for one arm/H from a built dataset.")
    ap.add_argument("--dataset", required=True, help="a build_dataset output directory (labels.csv.gz, base_X_hHH.npy)")
    ap.add_argument("--matrix-dir")
    ap.add_argument("--arm", choices=ARMS)
    ap.add_argument("--horizon", type=int, choices=HORIZONS)
    ap.add_argument("--config", help="a recipe: arm, horizon and schedule from it (checked like the job)")
    ap.add_argument("--digests", action="store_true",
                    help="also write the 13 pre-fit equivalence digests at the gate's width (exact q from q*_str)")
    ap.add_argument("--check", action="store_true", help="with --digests: exit 1 unless they equal the recipe's pinned digests")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    config = json.load(open(a.config)) if a.config else None
    if config is not None:
        for k in ("arm", "horizon"):
            if getattr(a, k) is not None and getattr(a, k) != config.get(k):
                raise SystemExit(f"--{k} differs from the recipe")
        a.arm, a.horizon = config.get("arm"), config.get("horizon")
        check_config(config, a.horizon, a.arm)
        schedule = schedule_from_config(config, a.horizon)
    elif a.arm is None or a.horizon is None:
        raise SystemExit("give --arm and --horizon, or --config")
    elif a.arm == HPT_ARM:
        raise SystemExit(f"{HPT_ARM} plans need its tuning or formal recipe (--config)")
    else:
        schedule = DEFAULT_SCHEDULE
    if (a.digests or a.check) and a.arm == HSTACK_ARM:
        raise SystemExit("digests of the stacked arm need the stacked matrix (use the gate command)")
    if a.check and not (a.digests and config is not None):
        raise SystemExit("--check needs --digests and --config")
    exact = {f"{q}_str": str for q in TARGETS} if a.digests else {}
    labels = pd.read_csv(os.path.join(a.dataset, "labels.csv.gz"), dtype={"anl_id": str, **exact}, keep_default_na=False, na_values=[""])
    if a.digests:      # the in-memory job holds float(q_str); a default float parse can differ in the last bit
        for q in TARGETS:
            labels[q] = np.array([np.nan if v == "" else float(v) for v in labels[f"{q}_str"]], dtype=np.float64)
    X = np.load(os.path.join(a.matrix_dir or a.dataset, f"base_X_h{a.horizon:02d}.npy"), mmap_mode="r")
    order = pd.read_csv(os.path.join(a.dataset, f"feature_order_h{a.horizon:02d}.csv"))["name"].tolist()
    obs = pd.read_csv(os.path.join(a.dataset, "history_observations.csv.gz"))
    L, Xa = select_arm(labels, X, a.arm)
    d = ArmData(a.arm, a.horizon, L, Xa, order, obs, pd.DataFrame(), None, schedule)
    plans = hpt_plans(d, config)[0] if a.arm == HPT_ARM else plan_contexts(d)
    s = plan_summary(d, plans)
    os.makedirs(a.out, exist_ok=True)
    s.to_csv(os.path.join(a.out, f"plan_{a.arm}_h{a.horizon:02d}.csv"), index=False)
    print(s[["context", "fit", "fit_block", "fit_cutoff", "train_rows", "excluded_eligible_rows", "predicted_rows", "scalar_fits"]].to_string())
    if schedule.declared:
        rec = plan_assertions(d, plans)
        with open(os.path.join(a.out, f"assertions_{a.arm}_h{a.horizon:02d}.json"), "w") as f:
            json.dump({"schedule": schedule.record(), "contexts": rec}, f, indent=1, default=str)
    if a.digests:
        kind = baseline_kind(config or {})
        width = len(order) if a.arm == HPT_ARM else equivalence_width(a.arm, a.horizon, kind, order)
        got = equivalence_digests(d, plans, width)
        want = ((config or {}).get("baseline") or {}).get("equivalence")
        differ = check_equivalence(got, want) if want else None
        rec = {"arm": a.arm, "horizon": a.horizon, "kind": kind, "width": width, "rows": got["rows"], "digests": got,
               "pinned": want, "differing": differ, "dataset": os.path.abspath(a.dataset),
               "recipe": os.path.abspath(a.config) if a.config else None}
        with open(os.path.join(a.out, f"digests_{a.arm}_h{a.horizon:02d}.json"), "w") as f:
            json.dump(rec, f, indent=1)
        print(json.dumps({"digests": got, "differing": differ}, indent=1))
        if a.check and (differ is None or differ):
            print(f"pinned digests differ or are absent: {differ}", file=sys.stderr)
            sys.exit(1)


def gate_main(argv):
    """No-fit run of the job's own stage 1 and pre-fit gates (``prepare``) on a manifest and recipe; exit 1 when a
    gate refuses. Writes the dataset build, equivalence.json and gate.json under a new local directory."""
    import argparse
    from research_cloud.training.common import Output, TrialError, resolve_inputs
    ap = argparse.ArgumentParser(description="Pre-fit gate only (no model fitting).")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True, help="new local directory")
    a = ap.parse_args(argv)
    if a.out.startswith("gs://") or os.path.exists(a.out):
        raise SystemExit("--out must be a new local directory")
    config = json.load(open(a.config))
    out = Output(a.out)
    inputs, manifest = resolve_inputs(a.manifest, out.local)
    t0 = time.time()
    try:
        prep = prepare(inputs, config, out, manifest)
    except TrialError as e:
        out.write_json("gate.json", {"passed": False, "error": str(e), "recipe": os.path.abspath(a.config),
                                     "seconds": round(time.time() - t0, 1)})
        print(f"gate refused: {e}", file=sys.stderr)
        sys.exit(1)
    d = prep["d"]
    rec = {"passed": True, "arm": d.arm, "horizon": d.horizon, "kind": prep["kind"], "rows": int(len(d.admin)),
           "features": len(prep["order"]), "recipe": os.path.abspath(a.config), "seconds": round(time.time() - t0, 1)}
    if d.schedule.declared:
        rec["assertions"] = plan_assertions(d, prep.get("plans") or plan_contexts(d))
    if d.arm in ACLED_ARMS:
        with open(out.path("paired_gate.json")) as f:
            paired = json.load(f)
        rec["paired_gate"] = {k: paired[k] for k in ("passed", "failed", "baseline")}
    out.write_json("gate.json", rec)
    print(json.dumps({k: rec[k] for k in ("passed", "arm", "horizon", "kind", "rows", "features")}))


def reference_main(argv):
    """Gate A reference of one retained production trial directory (task 10-20); writes a new JSON file."""
    import argparse
    from research_cloud.training.common import sha256_file
    ap = argparse.ArgumentParser(description="Paired-baseline reference from a retained trial (no fit, no new build).")
    ap.add_argument("--trial", required=True, help=f"retained {ACLED_BASELINE_ARM} trial directory")
    ap.add_argument("--horizon", type=int, choices=HORIZONS, required=True)
    ap.add_argument("--run-id", required=True, help="the trial's published MLflow run (must equal trial.json mlflow_run_id)")
    ap.add_argument("--out", required=True, help="new JSON file")
    a = ap.parse_args(argv)
    if os.path.exists(a.out):
        raise SystemExit("--out must be a new file")
    ref = paired_reference(a.trial, a.horizon, a.run_id)
    with open(a.out, "w") as f:
        json.dump(ref, f, indent=1, sort_keys=True)
    print(json.dumps({"out": a.out, "sha256": sha256_file(a.out), "rows": ref["digests"]["rows"],
                      "non_acled_columns": len(ref["non_acled_order"]), "predictions": ref["predictions"]}))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "plan":
        plan_main(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == "gate":
        gate_main(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == "reference":
        reference_main(sys.argv[2:])
    else:
        from research_cloud.training.common import run_trial
        # the arm's own contract (check_config) binds the objective; the tuned arm reports its selection/formal key
        sys.exit(run_trial(fit, objective=(OBJECTIVE, HPT_OBJECTIVE, HPT_FORMAL_OBJECTIVE)))
