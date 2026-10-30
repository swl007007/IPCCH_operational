"""Validity-augmented IPCCH datasets: share-only targets, report validity lineage, augmentation and origin-safe features.

Task ``10-16-ipcch-validity-augmented-pooled`` (prd.md R1-R4, design.md sections 2-5). Pure data functions: nothing
here fits a model or touches the network. The pinned scientific primitives are imported from the AlphaEarth
experiment source (``IPCCH_AE_SRC``, default ``/app/sources/IPCCHAlphaEarthExperiment`` in the image; read-only):
``ipcch_alphaearth.compact`` (compact296 recipe), ``targets`` (exact decimal helpers) and ``months``.

Targets. Both arms use exact-decimal share QC without ``estimated_population``: P1-P4 observed, missing P5 = 0, every
share finite in [0, 1], exact total in [0.90, 1.10]; q_k = sum(P_j, j >= k) / total; phase = greatest k with
5 * Q_k >= total (inclusive 0.20), else 1. Raw ``overall_phase`` is provenance and a history input, never truth.

Augmentation. A share-valid original (donor) at country/month links to the unique current analysis
(``condition=A``, ``ipc_period=C``) whose validity starts that month; its inclusive window fills existing raw
monthly rows of the same admin whose six raw label fields are all blank. Existing raw observations win; among
competing donors the latest original month wins; equal-date conflicting targets stay unfilled. Copies inherit the
donor's targets, source month (availability) and source-round family ``(country, original month)``.

Features. compact296 (frozen order) + 128 AlphaEarth 2017 descriptors + realized monthly precipitation/temperature
anomalies at O+1..O+min(H, 6) (H0: none). Every row is built at its own origin O = T - H. The five reported-phase
history columns are context dependent (``history_block``): original reports only, excluded source-round families
removed before the latest-three selection, upper bound T-1 at H0 and O otherwise.

Local IDP (task ``10-17-ipcch-idp-augmented-pooled``, optional): ``idp_ffill6`` current/strict MA3/MA6 at O from
``idp_ipcch_monthly.parquet``, appended after every existing column (424/436 -> 427/439).

Aggregated ACLED (task ``10-20-ipcch-acled-retrain``, optional): the 14 compact296 conflict columns are replaced by 114
columns of the 18 staged ``acled_agg_*`` interim series, all evaluated at A = O - 1 and placed before the local-IDP
suffix (427/439 -> 527/539).
"""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal

import numpy as np
import pandas as pd

HORIZONS = (0, 6, 12)
TARGETS = ("q2", "q3", "q4", "q5")
PHASE_COLUMNS = ("phase1_percent", "phase2_percent", "phase3_percent", "phase4_percent", "phase5_percent")
LABEL_FIELDS = ("overall_phase",) + PHASE_COLUMNS
BLANK = frozenset({"", "na", "nan", "none", "null", "<na>"})
ORACLE_VARIABLES = ("prcp_anom_month_ensmean", "tmean_anom_month_ensmean")
MAX_ORACLE_MONTHS = 6
COMPACT296_SHA256 = "e97388f848e7095bf0535f0cfee1a2d798e0c1863dee843462e60cf6a36f9909"
AE_PREFIXES = ("ae2017_mean_A", "ae2017_sd_A")
AE_BANDS = 64
SCALE = 1 << 20          # admin_code * SCALE + month ordinal packs a key into one int64
REGIONAL_CODES = frozenset({"LAC"})
EXPECTED_FEATURES = {0: 424, 6: 436, 12: 436}


class DataContractError(RuntimeError):
    """A pinned identity, source format or temporal/report contract check failed; the job stops."""


# --------------------------------------------------------------------------- pinned scientific source


def ae_source():
    return os.environ.get("IPCCH_AE_SRC", "/app/sources/IPCCHAlphaEarthExperiment")


def ae_modules():
    """(compact, targets, months) from the pinned AlphaEarth source tree; never writes bytecode into it."""
    src = ae_source()
    if src not in sys.path:
        sys.dont_write_bytecode = True
        sys.path.insert(0, src)
    import importlib
    return tuple(importlib.import_module(f"ipcch_alphaearth.{m}") for m in ("compact", "targets", "months"))


def month_ord(year, month):
    return np.asarray(year, dtype=np.int64) * 12 + np.asarray(month, dtype=np.int64) - 1


def month_label(o):
    if np.isscalar(o):
        o = int(o)
        return f"{o // 12:04d}-{o % 12 + 1:02d}"
    return np.array([f"{x // 12:04d}-{x % 12 + 1:02d}" for x in np.asarray(o, dtype=np.int64)], dtype=object)


def list_sha256(names):
    """Newline-joined UTF-8 (the compact contract's feature-list digest convention)."""
    import hashlib
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- share-only targets (R2)


def is_blank(text) -> bool:
    return text is None or str(text).strip().lower() in BLANK


INVALID = "invalid"   # a nonempty share cell that is not a finite decimal (parse failure, NaN/sNaN, infinity)


def parse_share(text):
    """Explicit missing marker (blank/NA token) -> None; finite decimal -> Decimal; anything else -> INVALID.

    Only an explicit missing marker counts as missing: ``sNaN``, ``inf`` or garbage are invalid shares, never a
    missing P5 that would be zero-filled."""
    if is_blank(text):
        return None
    try:
        value = Decimal(str(text).strip())
    except ArithmeticError:
        return INVALID
    return value if value.is_finite() else INVALID


def share_verdict(phases):
    """Exact share QC and truth for one row's five parsed shares (None = missing, INVALID = invalid cell).
    Population is never read. Returns (valid, reason, p5_filled, total, (q2..q5 normalized Decimal), phase)."""
    _, t, _ = ae_modules()
    p1, p2, p3, p4, p5 = phases
    if any(v is None for v in (p1, p2, p3, p4)):
        return 0, "missing_phase_1_to_4", False, None, None, None
    if any(v is INVALID for v in phases):
        return 0, "phase_share_invalid", False, None, None, None
    filled_p5 = p5 is None
    filled = (p1, p2, p3, p4, t.ZERO if filled_p5 else p5)
    for v in filled:
        if v < t.ZERO or v > t.ONE:
            return 0, "phase_share_out_of_bounds", filled_p5, None, None, None
    total = t.exact_sum(filled)
    if total < t.SUM_LOWER or total > t.SUM_UPPER:
        return 0, "sum_out_of_bounds", filled_p5, total, None, None
    phase, cumulative = 1, []
    for k in range(2, 6):
        q = t.exact_sum(filled[k - 1:])
        if t.reaches_threshold(q, total):
            phase = k
        cumulative.append(t._NORMALIZATION_CONTEXT.divide(q, total))
    return 1, "", filled_p5, total, tuple(cumulative), phase


def build_label_ledger(raw_panel_path) -> pd.DataFrame:
    """Every raw area-month with its untouched label strings, blank flag, share-only verdict and targets."""
    cols = ["admin_code", "year", "month", *LABEL_FIELDS, "estimated_population"]
    raw = pd.read_csv(raw_panel_path, dtype=str, keep_default_na=False, na_filter=False, usecols=cols)
    for c in ("admin_code", "year", "month"):
        if (raw[c].str.strip() == "").any():
            raise DataContractError(f"raw panel {c} has blank keys")
    out = pd.DataFrame({"admin_code": raw["admin_code"].astype(np.int64), "year": raw["year"].astype(np.int64),
                        "month": raw["month"].astype(np.int64)})
    if not out["month"].between(1, 12).all() or out.duplicated(["admin_code", "year", "month"]).any():
        raise DataContractError("raw panel keys are not unique valid admin/year/month")
    out["month_ord"] = month_ord(out["year"], out["month"])
    for c in LABEL_FIELDS:
        out[f"raw_{c}"] = raw[c].to_numpy(dtype=object)
    out["raw_estimated_population"] = raw["estimated_population"].to_numpy(dtype=object)
    blank = np.ones(len(raw), dtype=bool)
    for c in LABEL_FIELDS:
        blank &= raw[c].str.strip().str.lower().isin(BLANK).to_numpy()
    out["label_blank"] = blank
    shares = [raw[c].to_numpy(dtype=object) for c in PHASE_COLUMNS]
    n = len(raw)
    valid = np.zeros(n, dtype=np.int64)
    reason = np.full(n, "label_blank", dtype=object)
    p5f = np.zeros(n, dtype=np.int64)
    total_s = np.full(n, "", dtype=object)
    qs = [np.full(n, "", dtype=object) for _ in TARGETS]
    phase = np.zeros(n, dtype=np.int64)
    for i in np.flatnonzero(~blank):
        v = share_verdict([parse_share(s[i]) for s in shares])
        valid[i], reason[i], p5f[i] = v[0], v[1], int(v[2])
        if v[3] is not None:
            total_s[i] = str(v[3])
        if v[0]:
            for k in range(4):
                qs[k][i] = str(v[4][k])
            phase[i] = v[5]
    out["target_valid"], out["target_reason"], out["p5_missing_filled"], out["phase_sum_str"] = valid, reason, p5f, total_s
    for k, q in enumerate(TARGETS):
        out[f"{q}_str"] = qs[k]
        out[q] = np.array([np.nan if s == "" else float(s) for s in qs[k]], dtype=np.float64)
    out["phase_truth"] = phase
    out["crisis_truth"] = (phase >= 3).astype(np.int64)
    rp = pd.to_numeric(raw["overall_phase"], errors="coerce")
    out["reported_phase"] = np.where(rp.isin([1, 2, 3, 4, 5]), rp, np.nan)
    return out.sort_values(["admin_code", "month_ord"], kind="mergesort").reset_index(drop=True)


# --------------------------------------------------------------------------- countries (Namibia ISO2 "NA")


def country_table(lookup_path) -> pd.DataFrame:
    raw = pd.read_csv(lookup_path, dtype=str, keep_default_na=False, na_filter=False)
    for c in ("area_id", "iso3", "country", "country_code", "country_en"):
        if c not in raw.columns:
            raise DataContractError(f"country lookup lacks {c}")
    out = pd.DataFrame({"admin_code": raw["area_id"].astype(np.int64)})
    if out["admin_code"].duplicated().any():
        raise DataContractError("country lookup has duplicate area_id")
    code, iso3 = raw["country_code"].str.strip(), raw["iso3"].str.strip()
    iso2 = np.where(code.ne(""), code, np.where(iso3.eq("NAM"), "NA", ""))
    if (iso2 == "").any():
        raise DataContractError(f"{int((iso2 == '').sum())} admins have no ISO2 code (only NAM -> NA is mapped)")
    out["iso2"] = iso2.astype(object)
    out["iso3"] = np.where(iso3.ne(""), iso3, None)
    en, fallback = raw["country_en"].str.strip(), raw["country"].str.strip()
    out["country_key"] = np.where(en.ne(""), en, fallback)
    return out.sort_values("admin_code", kind="mergesort").reset_index(drop=True)


# --------------------------------------------------------------------------- validity dictionary (design section 2)


def parse_validity_month(text):
    """``%b %Y`` (e.g. ``Jul 2025``) -> month ordinal, else None."""
    import datetime
    try:
        d = datetime.datetime.strptime(str(text).strip(), "%b %Y")
    except (TypeError, ValueError):
        return None
    return d.year * 12 + d.month - 1


def validity_reports(areas_path, analyses_path):
    """(reports, start_index): one row per anl_id with its status; (country, from_ord) -> eligible anl_ids.

    Reads only GeoJSON feature properties. A report is eligible when it joins an analyses record of the same
    country, every area row agrees on one (country, condition, ipc_period, from, to) tuple, condition=A,
    ipc_period=C, both months parse and from <= to, and the country is not regional (LAC)."""
    with open(analyses_path) as f:
        analyses = {str(r["id"]): r for r in json.load(f)["records"]}
    with open(areas_path) as f:
        features = json.load(f)["features"]
    props = {}
    for feat in features:
        p = feat.get("properties") or {}
        key = str(p.get("anl_id"))
        props.setdefault(key, set()).add(tuple(str(p.get(k, "")) for k in ("country", "condition", "ipc_period", "from", "to")))
    del features
    rows = []
    for anl, tuples in sorted(props.items()):
        status, rec = "eligible", None
        if len(tuples) != 1:
            status = "inconsistent_area_rows"
        else:
            rec = next(iter(tuples))
        country, condition, period, frm, to = rec if rec else ("", "", "", "", "")
        lo, hi = parse_validity_month(frm), parse_validity_month(to)
        a = analyses.get(anl)
        if status == "eligible":
            if a is None:
                status = "no_analysis_record"
            elif str(a.get("country", "")) != country:
                status = "analysis_country_mismatch"
            elif country in REGIONAL_CODES:
                status = "regional_code"
            elif condition != "A":
                status = "condition_not_A"
            elif period != "C":
                status = "period_not_C"
            elif lo is None or hi is None:
                status = "malformed_window"
            elif lo > hi:
                status = "reversed_window"
        rows.append({"anl_id": anl, "country": country, "condition": condition, "ipc_period": period, "from": frm, "to": to,
                     "from_ord": -1 if lo is None else lo, "to_ord": -1 if hi is None else hi, "status": status})
    reports = pd.DataFrame(rows)
    ok = reports[reports["status"] == "eligible"]
    index = {}
    for r in ok.itertuples(index=False):
        index.setdefault((r.country, int(r.from_ord)), []).append(r.anl_id)
    return reports, {k: sorted(v) for k, v in index.items()}


# --------------------------------------------------------------------------- augmentation (R2, design section 3)


def family_code(country_index, month):
    """Integer source-round family id for (country, original month)."""
    return np.asarray(country_index, dtype=np.int64) * SCALE + np.asarray(month, dtype=np.int64)


def augment(ledger: pd.DataFrame, countries: pd.DataFrame, reports: pd.DataFrame, start_index: dict) -> dict:
    """Donor, relationship and recipient dispositions plus the keyed label rows of both arms.

    Returns {"labels": original + copy label rows, "donors", "relationships", "recipients", "counts",
    "country_codes"}. ``labels.label_kind`` is ``original`` or ``copy``; the original arm uses the originals only."""
    led = ledger.reset_index(drop=True)
    by_admin = countries.set_index("admin_code")
    missing = sorted(set(led.loc[led["target_valid"] == 1, "admin_code"]) - set(by_admin.index))
    if missing:
        raise DataContractError(f"{len(missing)} share-valid admins lack a country")
    codes = sorted(set(countries["iso2"]))
    cidx = {c: i for i, c in enumerate(codes)}
    led_iso2 = by_admin["iso2"].reindex(led["admin_code"].to_numpy()).to_numpy(dtype=object)
    led_key = led["admin_code"].to_numpy(np.int64) * SCALE + led["month_ord"].to_numpy(np.int64)
    key_pos = pd.Series(np.arange(len(led)), index=led_key)
    if key_pos.index.duplicated().any():
        raise DataContractError("duplicate raw keys")

    donors = led[led["target_valid"] == 1].copy()
    donors["iso2"] = led_iso2[donors.index]
    win = reports.set_index("anl_id")
    status, anl, lo, hi = [], [], [], []
    for c, m in zip(donors["iso2"], donors["month_ord"]):
        ids = start_index.get((c, int(m)), [])
        if not ids:
            status.append("no_report"); anl.append(""); lo.append(-1); hi.append(-1)
        elif len(ids) > 1:
            status.append("ambiguous_report"); anl.append(",".join(ids)); lo.append(-1); hi.append(-1)
        else:
            status.append("linked"); anl.append(ids[0])
            lo.append(int(win.at[ids[0], "from_ord"])); hi.append(int(win.at[ids[0], "to_ord"]))
    donors["link_status"], donors["anl_id"] = status, anl
    donors["valid_from_ord"], donors["valid_to_ord"] = np.array(lo, np.int64), np.array(hi, np.int64)
    donors["source_family"] = family_code([cidx[c] for c in donors["iso2"]], donors["month_ord"])

    linked = donors[donors["link_status"] == "linked"]
    span = (linked["valid_to_ord"] - linked["valid_from_ord"] + 1).to_numpy(np.int64)
    rel = pd.DataFrame({
        "donor_row": np.repeat(linked.index.to_numpy(), span),
        "admin_code": np.repeat(linked["admin_code"].to_numpy(np.int64), span),
        "donor_month_ord": np.repeat(linked["month_ord"].to_numpy(np.int64), span),
        "anl_id": np.repeat(linked["anl_id"].to_numpy(dtype=object), span),
    })
    offsets = np.concatenate([np.arange(s) for s in span]) if len(span) else np.zeros(0, np.int64)
    rel["recipient_month_ord"] = np.repeat(linked["valid_from_ord"].to_numpy(np.int64), span) + offsets
    rkey = rel["admin_code"].to_numpy(np.int64) * SCALE + rel["recipient_month_ord"].to_numpy(np.int64)
    pos = key_pos.reindex(rkey).to_numpy()
    has_row = ~np.isnan(pos)
    disp = np.full(len(rel), "candidate", dtype=object)
    disp[~has_row] = "no_raw_row"
    rpos = np.where(has_row, pos, 0).astype(np.int64)
    rblank = led["label_blank"].to_numpy()[rpos]
    rvalid = led["target_valid"].to_numpy()[rpos]
    self_month = rel["recipient_month_ord"].to_numpy() == rel["donor_month_ord"].to_numpy()
    disp[has_row & ~rblank & self_month] = "existing_label_donor_month"
    disp[has_row & ~rblank & ~self_month & (rvalid == 1)] = "existing_label_valid"
    disp[has_row & ~rblank & ~self_month & (rvalid == 0)] = "existing_label_not_valid"
    rel["recipient_row"] = np.where(has_row, rpos, -1)
    rel["disposition"] = disp

    # overlap priority among candidate donors of one recipient (latest original month; equal-date conflict unfilled)
    cand = rel[rel["disposition"] == "candidate"].copy()
    qstr = led[[f"{q}_str" for q in TARGETS]].to_numpy(dtype=object)
    cand["target_sig"] = ["|".join(qstr[d]) for d in cand["donor_row"]]
    selected, recipient_rows = np.zeros(len(rel), dtype=bool), []
    for rrow, g in cand.groupby("recipient_row", sort=True):
        latest = g["donor_month_ord"].max()
        top = g[g["donor_month_ord"] == latest]
        if top["target_sig"].nunique() > 1:
            outcome, chosen = "equal_date_conflict", None
        else:
            outcome, chosen = ("single_donor" if len(g) == 1 else "latest_donor"), top.index[0]
        for i in g.index:
            if i != chosen:
                rel.at[i, "disposition"] = "overlap_not_selected" if chosen is not None else "equal_date_conflict"
        if chosen is not None:
            selected[rel.index.get_loc(chosen)] = True
        recipient_rows.append({"recipient_row": int(rrow), "candidates": int(len(g)), "outcome": outcome,
                               "selected_donor_row": -1 if chosen is None else int(rel.at[chosen, "donor_row"])})
    rel.loc[selected, "disposition"] = "copied"
    recipients = pd.DataFrame(recipient_rows, columns=["recipient_row", "candidates", "outcome", "selected_donor_row"])

    keep = ["admin_code", "year", "month", "month_ord", *[f"{q}_str" for q in TARGETS], *TARGETS, "phase_truth", "crisis_truth",
            *[f"raw_{c}" for c in LABEL_FIELDS], "raw_estimated_population"]
    orig = donors[keep].copy()
    orig["label_kind"] = "original"
    orig["source_admin_code"], orig["source_month_ord"] = orig["admin_code"], orig["month_ord"]
    orig["source_family"], orig["anl_id"], orig["link_status"] = donors["source_family"], donors["anl_id"], donors["link_status"]
    orig["valid_from_ord"], orig["valid_to_ord"] = donors["valid_from_ord"], donors["valid_to_ord"]
    cp = rel[rel["disposition"] == "copied"]
    rec = led.loc[cp["recipient_row"].to_numpy(), ["admin_code", "year", "month", "month_ord",
                                                   *[f"raw_{c}" for c in LABEL_FIELDS], "raw_estimated_population"]].reset_index(drop=True)
    don = donors.loc[cp["donor_row"].to_numpy()].reset_index(drop=True)
    copies = rec.copy()
    for c in [*[f"{q}_str" for q in TARGETS], *TARGETS, "phase_truth", "crisis_truth"]:
        copies[c] = don[c].to_numpy()
    copies["label_kind"] = "copy"
    copies["source_admin_code"], copies["source_month_ord"] = don["admin_code"].to_numpy(), don["month_ord"].to_numpy()
    copies["source_family"], copies["anl_id"], copies["link_status"] = don["source_family"].to_numpy(), don["anl_id"].to_numpy(), "linked"
    copies["valid_from_ord"], copies["valid_to_ord"] = don["valid_from_ord"].to_numpy(), don["valid_to_ord"].to_numpy()
    for c in LABEL_FIELDS:
        if not copies[f"raw_{c}"].map(is_blank).all():
            raise DataContractError("a copy recipient has a nonblank raw label field")
    labels = pd.concat([orig, copies], ignore_index=True)[keep[:4] + ["label_kind"] + keep[4:] + [
        "source_admin_code", "source_month_ord", "source_family", "anl_id", "link_status", "valid_from_ord", "valid_to_ord"]]
    labels = labels.sort_values(["admin_code", "month_ord"], kind="mergesort").reset_index(drop=True)
    if labels.duplicated(["admin_code", "month_ord"]).any():
        raise DataContractError("an original and a copy (or two copies) share one area-month")
    labels["source_available_ord"] = labels["source_month_ord"]   # original observation-month end (design section 4)
    labels["iso2"] = by_admin["iso2"].reindex(labels["admin_code"].to_numpy()).to_numpy(dtype=object)
    labels["country_key"] = by_admin["country_key"].reindex(labels["admin_code"].to_numpy()).to_numpy(dtype=object)

    counts = {
        "raw_rows": int(len(led)), "share_valid_originals": int(len(donors)),
        "original_countries": int(donors["iso2"].nunique()),
        "invalid_reasons": led.loc[led["target_valid"] == 0, "target_reason"].value_counts().to_dict(),
        "donors": donors["link_status"].value_counts().to_dict(),
        "relationships": int(len(rel)), "relationship_dispositions": rel["disposition"].value_counts().to_dict(),
        "candidate_relationships": int(len(cand)), "candidate_recipients": int(cand["recipient_row"].nunique()),
        "candidate_countries": int(pd.Series(led_iso2[cand["recipient_row"].to_numpy()], dtype=object).nunique()),
        "overlap_recipients": int((recipients["candidates"] > 1).sum()),
        "recipient_outcomes": recipients["outcome"].value_counts().to_dict(),
        "copies": int(len(copies)), "copy_countries": int(copies.merge(countries, on="admin_code")["iso2"].nunique()),
        "cross_year_copies": int((copies["year"].to_numpy() != (copies["source_month_ord"].to_numpy() // 12)).sum()),
        "copies_by_year": copies["year"].value_counts().sort_index().astype(int).to_dict(),
        "originals_by_year": donors["year"].value_counts().sort_index().astype(int).to_dict(),
    }
    return {"labels": labels, "donors": donors, "relationships": rel, "recipients": recipients, "counts": counts,
            "country_codes": codes}


# --------------------------------------------------------------------------- CH validity correction (task 10-28)
#
# Task ``10-28-ipcch-ch-validity-refits`` (prd.md R2-R5, design.md sections 2-4). An optional keyed input (role
# ``ch_links``, one row per nonempty raw label row attributed to a Cadre Harmonise source route) adds CH current
# reference windows to the existing preparation; without it nothing here runs and every output is unchanged.
#
# * Only ``linked`` rows (current, source country == destination country, not CAF) expand: their window
#   (Jan-May 1-5, Jun-Aug 6-8, Sep-Dec 9-12 of reference_year) fills existing raw rows of the same admin whose six raw
#   label fields are blank. Every new row is a copy; existing nonempty rows (QC-invalid included) keep their values.
# * ``storage_role = upstream_copy`` rows (the 150 May-2026 copies stored raw) become copies of their own report, with
#   nominal source/availability = window start, the report family (source country, window start) by a verified pure
#   rename of their old (country, storage month) family, and ONE history event per area moved to the nominal month
#   with its storage month retained. No synthetic original is created.
# * ``cross_country`` rows keep every value and their old family and gain the evidenced source-report family as a
#   non-transitive alias (``source_family_alias``; also on their history events). ``caf_excluded`` / ``unresolved``
#   rows are untouched. No row of these statuses donates a copy or adds a history event.
# * A CH candidate on a recipient the IPC route already tries, or an eligible CH row the IPC route already links,
#   stops the build (no silent cross-framework replacement).

CH_LINKS_ROLE = "ch_links"
CH_REF_MONTHS = {"Jan-May": (1, 5), "Jun-Aug": (6, 8), "Sep-Dec": (9, 12)}
CH_STATUSES = ("linked", "cross_country", "caf_excluded", "unresolved")
CH_STORAGE_ROLES = ("reference_start", "upstream_copy")
CH_CAF = "CF"
CH_LINK_COLUMNS = ("admin_code", "month_ord", "dest_iso2", "route", "source_record", "source_iso2", "reference_year",
                   "reference_label", "start_ord", "end_ord", "nominal_source_ord", "storage_role", "link_status", "reason",
                   "eligible_new_copies")
CH_LABEL_COLUMNS = ("ch_role", "ch_report_id", "ch_source_record", "source_family_alias", "storage_month_ord")


def ch_report_id(source_iso2, reference_label, reference_year):
    return f"CH:{source_iso2}:{reference_label} {int(reference_year)}"


def ch_link_table(path, ledger: pd.DataFrame, countries: pd.DataFrame) -> pd.DataFrame:
    """Validated CH link rows. Every row is a nonempty raw key with the lookup's destination ISO2; every evidenced row
    (linked / cross_country / caf_excluded) has a reference window containing its storage month; ``linked`` implies
    source == destination country and not CAF; ``eligible_new_copies`` is exactly ``linked``."""
    t = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    missing = [c for c in CH_LINK_COLUMNS if c not in t.columns]
    if missing:
        raise DataContractError(f"ch_links lacks {missing}")
    t = t[list(CH_LINK_COLUMNS)].copy()
    for c in ("admin_code", "month_ord", "reference_year", "start_ord", "end_ord", "nominal_source_ord"):
        t[c] = t[c].astype(np.int64)
    t["eligible_new_copies"] = t["eligible_new_copies"].map({"True": True, "False": False})
    if t["eligible_new_copies"].isna().any():
        raise DataContractError("ch_links eligible_new_copies must be True/False")
    key = t["admin_code"].to_numpy(np.int64) * SCALE + t["month_ord"].to_numpy(np.int64)
    if pd.Series(key).duplicated().any():
        raise DataContractError("ch_links has duplicate raw keys")
    lk = ledger.assign(_k=ledger["admin_code"].to_numpy(np.int64) * SCALE + ledger["month_ord"].to_numpy(np.int64)).set_index("_k")
    if not pd.Index(key).isin(lk.index).all() or lk.loc[key, "label_blank"].to_numpy().any():
        raise DataContractError("every ch_links row must be a nonempty raw label row")
    dest = countries.set_index("admin_code")["iso2"].reindex(t["admin_code"].to_numpy()).to_numpy(dtype=object)
    if (dest != t["dest_iso2"].to_numpy(dtype=object)).any():
        raise DataContractError("ch_links destination country differs from the country lookup")
    if not t["link_status"].isin(CH_STATUSES).all() or not t["storage_role"].isin(CH_STORAGE_ROLES).all():
        raise DataContractError("ch_links has an unknown link_status or storage_role")
    if not (t["eligible_new_copies"] == (t["link_status"] == "linked")).all():
        raise DataContractError("ch_links eligibility must be exactly the linked status")
    ev = t["link_status"] != "unresolved"
    for r in t[ev].itertuples(index=False):
        if r.reference_label not in CH_REF_MONTHS:
            raise DataContractError(f"ch_links unknown reference label {r.reference_label!r}")
        lo, hi = CH_REF_MONTHS[r.reference_label]
        s, e = r.reference_year * 12 + lo - 1, r.reference_year * 12 + hi - 1
        if (r.start_ord, r.end_ord, r.nominal_source_ord) != (s, e, s) or not s <= r.month_ord <= e:
            raise DataContractError(f"ch_links window of {r.admin_code}/{r.month_ord} is not its reference window")
        if (r.storage_role == "reference_start") != (r.month_ord == s):
            raise DataContractError(f"ch_links storage role of {r.admin_code}/{r.month_ord} contradicts its window start")
    linked = t["link_status"] == "linked"
    if ((t.loc[linked, "source_iso2"] != t.loc[linked, "dest_iso2"]) | (t.loc[linked, "source_iso2"] == CH_CAF)).any():
        raise DataContractError("a linked CH row must have source country == destination country and not be CAF")
    cross = t["link_status"] == "cross_country"
    if (t.loc[cross, "source_iso2"] == t.loc[cross, "dest_iso2"]).any():
        raise DataContractError("a cross_country CH row must have different source and destination countries")
    if (t.loc[t["link_status"] == "caf_excluded", "source_iso2"] != CH_CAF).any():
        raise DataContractError("caf_excluded CH rows must have the CAF source")
    if ((t["storage_role"] == "upstream_copy") & ~linked).any():
        raise DataContractError("only linked rows may be upstream copies")
    return t.sort_values(["admin_code", "month_ord"], kind="mergesort").reset_index(drop=True)


def ch_augment(aug: dict, ledger: pd.DataFrame, countries: pd.DataFrame, ch: pd.DataFrame) -> dict:
    """The IPC-route ``augment`` result plus CH copies, reclassified upstream copies, family renames and aliases.

    Returns {"labels", "ch_relationships", "reclassified_keys", "renames" {old: new}, "aliases" {packed key: alias},
    "counts"}; the IPC labels/relationships are never rewritten except the explicit provenance fields of CH rows."""
    labels = aug["labels"].copy()
    codes = aug["country_codes"]
    cidx = {c: i for i, c in enumerate(codes)}
    lkey = ledger["admin_code"].to_numpy(np.int64) * SCALE + ledger["month_ord"].to_numpy(np.int64)
    lpos = pd.Series(np.arange(len(ledger)), index=lkey)
    ckey = ch["admin_code"].to_numpy(np.int64) * SCALE + ch["month_ord"].to_numpy(np.int64)
    labkey = labels["admin_code"].to_numpy(np.int64) * SCALE + labels["month_ord"].to_numpy(np.int64)
    lab_pos = pd.Series(np.arange(len(labels)), index=labkey)
    valid = ledger["target_valid"].to_numpy()[lpos.loc[ckey].to_numpy()] == 1
    ch = ch.assign(target_valid=valid, key=ckey)
    ch["src_family"] = [family_code(cidx[s], o) if s in cidx else -1 for s, o in zip(ch["source_iso2"], ch["start_ord"])]
    ch["old_family"] = family_code([cidx[d] for d in ch["dest_iso2"]], ch["month_ord"])
    if (ch.loc[ch["link_status"] != "unresolved", "src_family"] < 0).any():
        raise DataContractError("a CH source country has no country index")
    # an eligible CH row must not be a donor the IPC route already links (no double donor)
    don = aug["donors"]
    dkey = don["admin_code"].to_numpy(np.int64) * SCALE + don["month_ord"].to_numpy(np.int64)
    ipc_linked = set(dkey[(don["link_status"] == "linked").to_numpy()])
    elig = ch[ch["link_status"] == "linked"]
    if any(k in ipc_linked for k in elig["key"]):
        raise DataContractError("an eligible CH row is already linked by the IPC route")
    # family renames: an upstream copy's old (country, storage month) family must hold exactly these rows
    renames = {}
    up = elig[elig["storage_role"] == "upstream_copy"]
    for old, g in up.groupby("old_family"):
        new = set(g["src_family"])
        if len(new) != 1:
            raise DataContractError(f"upstream copies of family {old} map to several report families")
        members = set(labkey[labels["source_family"].to_numpy(np.int64) == old])
        if members != set(g.loc[g["target_valid"], "key"]):
            raise DataContractError(f"family {old} is not exactly its upstream copies; a rename would split it")
        new = new.pop()
        if (labels["source_family"].to_numpy(np.int64) == new).any():
            raise DataContractError(f"report family {new} already exists; a rename would merge")
        renames[int(old)] = int(new)
    same = elig[elig["storage_role"] == "reference_start"]
    if (same["src_family"].to_numpy() != same["old_family"].to_numpy()).any():
        raise DataContractError("a same-country reference-start CH row must already carry its report family")
    # CH relationships of eligible, share-valid donors
    donors = elig[elig["target_valid"]]
    span = (donors["end_ord"] - donors["start_ord"] + 1).to_numpy(np.int64)
    rel = pd.DataFrame({"admin_code": np.repeat(donors["admin_code"].to_numpy(np.int64), span),
                        "donor_month_ord": np.repeat(donors["month_ord"].to_numpy(np.int64), span),
                        "nominal_source_ord": np.repeat(donors["nominal_source_ord"].to_numpy(np.int64), span),
                        "report_id": np.repeat([ch_report_id(s, l, y) for s, l, y in zip(donors["source_iso2"], donors["reference_label"],
                                                                                          donors["reference_year"])], span),
                        "storage_role": np.repeat(donors["storage_role"].to_numpy(dtype=object), span)})
    rel["recipient_month_ord"] = (np.repeat(donors["start_ord"].to_numpy(np.int64), span)
                                  + (np.concatenate([np.arange(s) for s in span]) if len(span) else np.zeros(0, np.int64)))
    rel = rel[rel["recipient_month_ord"] != rel["donor_month_ord"]].reset_index(drop=True)
    rkey = rel["admin_code"].to_numpy(np.int64) * SCALE + rel["recipient_month_ord"].to_numpy(np.int64)
    pos = lpos.reindex(rkey).to_numpy()
    has = ~np.isnan(pos)
    rp = np.where(has, pos, 0).astype(np.int64)
    blank, rvalid = ledger["label_blank"].to_numpy()[rp], ledger["target_valid"].to_numpy()[rp]
    disp = np.full(len(rel), "candidate", dtype=object)
    disp[~has] = "no_raw_row"
    disp[has & ~blank & (rvalid == 1)] = "existing_label_valid"
    disp[has & ~blank & (rvalid == 0)] = "existing_label_not_valid"
    rel["recipient_row"] = np.where(has, rp, -1)
    rel["disposition"] = disp
    # cross-framework collision: the IPC route already tries this recipient (any candidate outcome) or copied into it
    irel = aug["relationships"]
    tried = set(irel.loc[(irel["recipient_row"] >= 0) & irel["disposition"].isin(
        ["candidate", "copied", "overlap_not_selected", "equal_date_conflict"]), "recipient_row"].astype(np.int64))
    ipc_copy = set(labkey[(labels["label_kind"] == "copy").to_numpy()])
    cand = rel["disposition"] == "candidate"
    clash = cand & (rel["recipient_row"].isin(tried) | pd.Series(rkey).isin(ipc_copy).to_numpy())
    if clash.any():
        raise DataContractError(f"{int(clash.sum())} CH candidates collide with the IPC route (cross-framework recipient)")
    # overlap among CH candidates: latest nominal source month; equal-date conflicting truths stay unfilled
    qstr = ledger[[f"{q}_str" for q in TARGETS]].to_numpy(dtype=object)
    donor_row = lpos.loc[rel["admin_code"].to_numpy(np.int64) * SCALE + rel["donor_month_ord"].to_numpy(np.int64)].to_numpy()
    rel["donor_row"] = donor_row
    sig = ["|".join(qstr[d]) for d in donor_row]
    for rrow, g in rel[cand].groupby("recipient_row"):
        if len(g) == 1:
            continue
        top = g[g["nominal_source_ord"] == g["nominal_source_ord"].max()]
        sigs = {sig[i] for i in top.index}
        keep = top.index[0] if len(sigs) == 1 else None
        for i in g.index:
            if i != keep:
                rel.at[i, "disposition"] = "overlap_not_selected" if keep is not None else "equal_date_conflict"
    copied = rel["disposition"] == "candidate"
    rel.loc[copied, "disposition"] = "copied"
    # new CH copy rows
    keep = ["admin_code", "year", "month", "month_ord", *[f"{q}_str" for q in TARGETS], *TARGETS, "phase_truth", "crisis_truth",
            *[f"raw_{c}" for c in LABEL_FIELDS], "raw_estimated_population"]
    cp = rel[copied]
    rec = ledger.iloc[cp["recipient_row"].to_numpy()][["admin_code", "year", "month", "month_ord", *[f"raw_{c}" for c in LABEL_FIELDS],
                                                        "raw_estimated_population"]].reset_index(drop=True)
    don_rows = ledger.iloc[cp["donor_row"].to_numpy()].reset_index(drop=True)
    for c in LABEL_FIELDS:
        if not rec[f"raw_{c}"].map(is_blank).all():
            raise DataContractError("a CH copy recipient has a nonblank raw label field")
    new = rec.copy()
    for c in [*[f"{q}_str" for q in TARGETS], *TARGETS, "phase_truth", "crisis_truth"]:
        new[c] = don_rows[c].to_numpy()
    by_key = ch.set_index("key")
    dk = cp["admin_code"].to_numpy(np.int64) * SCALE + cp["donor_month_ord"].to_numpy(np.int64)
    fam = by_key.loc[dk, "src_family"].to_numpy(np.int64)
    new["label_kind"] = "copy"
    new["source_admin_code"], new["source_month_ord"] = cp["admin_code"].to_numpy(np.int64), cp["nominal_source_ord"].to_numpy(np.int64)
    new["source_family"], new["anl_id"], new["link_status"] = fam, cp["report_id"].to_numpy(dtype=object), "linked_ch"
    new["valid_from_ord"], new["valid_to_ord"] = by_key.loc[dk, "start_ord"].to_numpy(np.int64), by_key.loc[dk, "end_ord"].to_numpy(np.int64)
    new["source_available_ord"] = new["source_month_ord"]
    by_admin = countries.set_index("admin_code")
    new["iso2"] = by_admin["iso2"].reindex(new["admin_code"].to_numpy()).to_numpy(dtype=object)
    new["country_key"] = by_admin["country_key"].reindex(new["admin_code"].to_numpy()).to_numpy(dtype=object)
    new["ch_role"], new["ch_report_id"] = "added_copy", new["anl_id"]
    new["ch_source_record"] = by_key.loc[dk, "source_record"].to_numpy(dtype=object)
    new["source_family_alias"], new["storage_month_ord"] = np.int64(-1), np.int64(-1)
    # provenance of existing CH rows (values untouched)
    for c, v in (("ch_role", ""), ("ch_report_id", ""), ("ch_source_record", "")):
        labels[c] = v
    labels["source_family_alias"], labels["storage_month_ord"] = np.int64(-1), np.int64(-1)
    # aliases of EVERY evidenced cross-country raw row, share-valid or not: a share-invalid row is no label but its
    # reported phase can still be a history event, which must carry the alias too (no new event is created)
    cross = ch[ch["link_status"] == "cross_country"]
    aliases = {int(k): int(f) for k, f in zip(cross["key"], cross["src_family"])}
    for r in ch[ch["key"].isin(lab_pos.index)].itertuples(index=False):
        i = int(lab_pos[r.key])
        if labels.at[i, "label_kind"] != "original":
            raise DataContractError("a CH link row is not an original label")
        rid = ch_report_id(r.source_iso2, r.reference_label, r.reference_year) if r.link_status != "unresolved" else ""
        if r.link_status == "linked":
            labels.at[i, "anl_id"], labels.at[i, "ch_report_id"], labels.at[i, "ch_source_record"] = rid, rid, r.source_record
            labels.at[i, "valid_from_ord"], labels.at[i, "valid_to_ord"] = r.start_ord, r.end_ord
            if r.storage_role == "upstream_copy":
                labels.at[i, "label_kind"], labels.at[i, "ch_role"] = "copy", "reclassified_upstream_copy"
                labels.at[i, "link_status"] = "linked_ch_upstream_copy"
                labels.at[i, "source_month_ord"], labels.at[i, "source_available_ord"] = r.nominal_source_ord, r.nominal_source_ord
                labels.at[i, "storage_month_ord"] = r.month_ord
            else:
                labels.at[i, "ch_role"], labels.at[i, "link_status"] = "linked_original", "linked_ch"
        else:
            labels.at[i, "ch_role"], labels.at[i, "ch_report_id"], labels.at[i, "ch_source_record"] = r.link_status, rid, r.source_record
            if r.link_status == "cross_country":
                labels.at[i, "source_family_alias"] = r.src_family
    if renames:
        labels["source_family"] = labels["source_family"].map(lambda f: renames.get(int(f), int(f))).astype(np.int64)
    out = pd.concat([labels, new[list(labels.columns)]], ignore_index=True)
    out = out.sort_values(["admin_code", "month_ord"], kind="mergesort").reset_index(drop=True)
    if out.duplicated(["admin_code", "month_ord"]).any():
        raise DataContractError("a CH copy shares an area-month with another label")
    if (out["source_available_ord"].to_numpy() > out["month_ord"].to_numpy()).any():
        raise DataContractError("a CH label is available after its target month")
    reclassified = set(int(k) for k in up.loc[up["target_valid"], "key"])
    counts = {"link_rows": int(len(ch)), "link_status": ch["link_status"].value_counts().to_dict(),
              "eligible_rows": int(len(elig)), "eligible_share_invalid_rows": int((~elig["target_valid"]).sum()),
              "relationships": int(len(rel)), "relationship_dispositions": rel["disposition"].value_counts().to_dict(),
              "added_copies": int(len(new)), "reclassified_upstream_copies": len(reclassified),
              "added_copies_by_year": new["year"].value_counts().sort_index().astype(int).to_dict(),
              "added_copies_by_iso2": new["iso2"].value_counts().to_dict(),
              "cross_country_aliases": len(aliases),
              "cross_country_alias_labels": int((labels["source_family_alias"].to_numpy(np.int64) >= 0).sum()),
              "family_renames": {str(k): v for k, v in renames.items()},
              "labels_before": int(len(labels)), "labels_after": int(len(out)),
              "label_kind_after": out["label_kind"].value_counts().to_dict()}
    return {"labels": out, "ch_relationships": rel, "reclassified_keys": reclassified, "renames": renames, "aliases": aliases,
            "counts": counts}


def ch_history_observations(obs: pd.DataFrame, ch: pd.DataFrame, renames: dict, aliases: dict):
    """Raw reported-phase events with the CH corrections: an upstream copy's event moves to its nominal source month
    (one event per area; ``storage_month_ord`` keeps the raw month) under its renamed report family; a cross-country
    row's event keeps its family and gains the alias. No event is created for a row without a raw reported phase.
    Returns (observations with ``family_alias`` and ``storage_month_ord``, number of moved events)."""
    o = obs.copy()
    o["family_alias"], o["storage_month_ord"] = np.int64(-1), o["month_ord"].to_numpy(np.int64)
    okey = o["admin_code"].to_numpy(np.int64) * SCALE + o["month_ord"].to_numpy(np.int64)
    opos = pd.Series(np.arange(len(o)), index=okey)
    up = ch[(ch["link_status"] == "linked") & (ch["storage_role"] == "upstream_copy")]
    moved = 0
    for r in up.itertuples(index=False):
        k = int(r.admin_code) * SCALE + int(r.month_ord)
        if k not in opos.index:
            continue
        i = int(opos[k])
        target = int(r.admin_code) * SCALE + int(r.nominal_source_ord)
        if target in opos.index:
            raise DataContractError(f"admin {r.admin_code}: an event already exists at the nominal source month")
        o.iat[i, o.columns.get_loc("month_ord")] = int(r.nominal_source_ord)
        moved += 1
    if renames:
        o["family"] = o["family"].map(lambda f: renames.get(int(f), int(f))).astype(np.int64)
    if aliases:
        k2 = o["admin_code"].to_numpy(np.int64) * SCALE + o["storage_month_ord"].to_numpy(np.int64)
        o["family_alias"] = np.array([aliases.get(int(k), -1) for k in k2], dtype=np.int64)
    o = o.sort_values(["admin_code", "month_ord"], kind="mergesort").reset_index(drop=True)
    if o.duplicated(["admin_code", "month_ord"]).any():
        raise DataContractError("two history events share one area-month after the CH relocation")
    return o, moved


# --------------------------------------------------------------------------- reported-phase history (context dependent)


HISTORY_VALUES =("overall_phase_history_1", "overall_phase_history_2", "overall_phase_history_3")
HISTORY_FEATURES = HISTORY_VALUES + ("overall_phase_history_change_1_2", "overall_phase_history_change_1_3")


def history_observations(ledger: pd.DataFrame, countries: pd.DataFrame, codes) -> pd.DataFrame:
    """Original reported phases 1-5 from the raw panel with their source-round family (copies never appear)."""
    obs = ledger.loc[ledger["reported_phase"].notna(), ["admin_code", "month_ord", "reported_phase"]].copy()
    iso2 = countries.set_index("admin_code")["iso2"].reindex(obs["admin_code"].to_numpy())
    if iso2.isna().any():
        raise DataContractError("a reported-phase observation has no country")
    cidx = {c: i for i, c in enumerate(codes)}
    obs["family"] = family_code([cidx[c] for c in iso2], obs["month_ord"])
    return obs.sort_values(["admin_code", "month_ord"], kind="mergesort").reset_index(drop=True)


def history_bound(target_ord, horizon):
    """Latest usable reported-phase month: T-1 at H0, O = T-H otherwise."""
    return np.asarray(target_ord, dtype=np.int64) - max(int(horizon), 1)


def history_block(admin, target_ord, horizon, obs: pd.DataFrame, excluded_families=None, return_alias=False):
    """Latest three original reported phases with month <= bound after removing excluded families.

    Returns (block (n, 5) in HISTORY_FEATURES order, source months (n, 3), source families (n, 3); -1 = none). An
    observation table with a ``family_alias`` column (task 10-28 CH correction: the evidenced source-report family of a
    preserved cross-country label, -1 = none) drops an event when its family OR its alias is excluded; with
    ``return_alias`` the selected events' aliases (n, 3) are returned fourth. Without the column nothing changes."""
    o = obs
    aliased = "family_alias" in obs.columns
    if excluded_families is not None and len(excluded_families):
        ex = np.asarray(list(excluded_families), dtype=np.int64)
        drop = np.isin(obs["family"].to_numpy(), ex)
        if aliased:
            drop |= np.isin(obs["family_alias"].to_numpy(np.int64), ex)
        o = obs[~drop]
    okey = o["admin_code"].to_numpy(np.int64) * SCALE + o["month_ord"].to_numpy(np.int64)
    admin = np.asarray(admin, dtype=np.int64)
    bound = history_bound(target_ord, horizon)
    slot = np.searchsorted(okey, admin * SCALE + bound, side="right") - 1
    vals, srcs, fams = np.full((len(admin), 3), np.nan), np.full((len(admin), 3), -1, np.int64), np.full((len(admin), 3), -1, np.int64)
    oadmin, omonth = o["admin_code"].to_numpy(np.int64), o["month_ord"].to_numpy(np.int64)
    ophase, ofam = o["reported_phase"].to_numpy(np.float64), o["family"].to_numpy(np.int64)
    oalias = o["family_alias"].to_numpy(np.int64) if aliased else None
    aliases = np.full((len(admin), 3), -1, np.int64)
    for k in range(3):
        s = slot - k
        ok = s >= 0
        sc = np.clip(s, 0, None)
        ok &= (oadmin[sc] == admin) if len(o) else np.zeros(len(admin), bool)
        vals[ok, k], srcs[ok, k], fams[ok, k] = ophase[sc[ok]], omonth[sc[ok]], ofam[sc[ok]]
        if aliased:
            aliases[ok, k] = oalias[sc[ok]]
    if (srcs[srcs >= 0] > np.repeat(bound[:, None], 3, axis=1)[srcs >= 0]).any():
        raise DataContractError("history source after its bound")
    block = np.column_stack([vals, vals[:, 0] - vals[:, 1], vals[:, 0] - vals[:, 2]])
    return (block, srcs, fams, aliases) if return_alias else (block, srcs, fams)


def reference_history_check(admin, target_ord, horizon, obs: pd.DataFrame, excluded_families, block, sources) -> dict:
    """Independent pure-Python replay of ``history_block`` (latest three allowed original reports per row);
    raises on any disagreement in source month, value or change column."""
    excluded = set(int(f) for f in (excluded_families or ()))
    records = {}
    alias = obs["family_alias"].to_numpy(np.int64) if "family_alias" in obs.columns else np.full(len(obs), -1, np.int64)
    for (a, m, p, f), al in zip(obs.loc[:, ["admin_code", "month_ord", "reported_phase", "family"]].itertuples(index=False, name=None), alias):
        if int(f) not in excluded and int(al) not in excluded:
            records.setdefault(int(a), []).append((int(m), float(p)))
    for a in records:
        records[a].sort()
    present = 0
    for i, (a, t) in enumerate(zip(np.asarray(admin, dtype=np.int64), np.asarray(target_ord, dtype=np.int64))):
        bound = int(t) - max(int(horizon), 1)
        allowed = [r for r in records.get(int(a), []) if r[0] <= bound]
        want = list(reversed(allowed[-3:]))
        for k in range(3):
            if k < len(want):
                if sources[i, k] != want[k][0] or block[i, k] != want[k][1]:
                    raise DataContractError(f"row {i} history_{k + 1}: got ({sources[i, k]}, {block[i, k]}), expected {want[k]}")
                present += 1
            elif sources[i, k] != -1 or not np.isnan(block[i, k]):
                raise DataContractError(f"row {i} history_{k + 1}: expected no history")
        for got, x, y in ((block[i, 3], block[i, 0], block[i, 1]), (block[i, 4], block[i, 0], block[i, 2])):
            if not ((np.isnan(got) and np.isnan(x - y)) or got == x - y):
                raise DataContractError(f"row {i}: history change mismatch")
    return {"rows_checked": int(len(block)), "history_values_present": present}


# --------------------------------------------------------------------------- sources and base features


def load_sources(src: dict, acled_agg=False) -> dict:
    """Read and verify the pinned feature sources. ``src`` maps input roles to local paths. With ``acled_agg`` the 18
    aggregated-ACLED series are also read from the same interim panel (``sources["acled_agg"]``)."""
    cp, _, _ = ae_modules()
    manifest = json.load(open(src["compact_manifest"]))
    frozen = manifest["horizons"]["0"]["arms"]["compact_baseline"]["features"]
    if list_sha256(frozen) != COMPACT296_SHA256:
        raise DataContractError("compact manifest feature order differs from the frozen compact296 digest")
    groups = cp.feature_groups(frozen)
    members = manifest["commodity_members"]
    header = pd.read_csv(src["interim"], nrows=0).columns
    if cp.commodity_members(header) != members:
        raise DataContractError("interim commodity member columns differ from the pinned compact members")
    member_cols = [c for cols in members.values() for c in cols]
    acled_cols = list(ACLED_AGG_SOURCES) if acled_agg else []
    if sorted(set(acled_cols) - set(header)):
        raise DataContractError(f"interim panel lacks aggregated ACLED columns {sorted(set(acled_cols) - set(header))}")
    panel = pd.read_csv(src["interim"], usecols=["admin_code", "year", "month", *cp.INTERIM_SOURCES[:7], *member_cols, *acled_cols])
    panel = panel.rename(columns={"admin_code": "area_id"})
    if panel.duplicated(list(cp.KEYS)).any():
        raise DataContractError("interim panel has duplicate keys")
    interim = cp.interim_grid(panel, members)
    acled = acled_agg_grid(panel) if acled_agg else None
    del panel
    monthly = pd.read_csv(src["climate_monthly"], usecols=["admin_code", "year", "month", *cp.CLIMATE_SOURCES]).rename(columns={"admin_code": "area_id"})
    climate = cp.Grid.from_long(monthly, cp.CLIMATE_SOURCES)
    del monthly
    for grid in (interim, climate):
        for v, arr in grid.values.items():
            if np.isinf(arr).any():
                raise DataContractError(f"{v}: infinite source values")
    seasons = pd.read_csv(src["climate_seasonal"], usecols=["admin_code", "season_year", "season", "gs_start_date",
                                                            "gs_end_date_exclusive", *cp.SEASON_METRICS])
    coords = pd.read_csv(src["raw_panel"], usecols=["admin_code", "year", "month", "lat", "lon"]).rename(columns={"admin_code": "area_id"})
    static = pd.read_csv(src["static29"]).set_index("admin_code")
    if list(static.columns) != groups["static"]:
        raise DataContractError("static29 table columns differ from the frozen static block")
    idp = cp.idp_observations(pd.read_csv(src["idp_admin0_monthly"]))
    ae = pd.read_csv(src["descriptors"], float_precision="round_trip")
    ae_names = [f"{p}{j:02d}" for p in AE_PREFIXES for j in range(AE_BANDS)]
    if list(ae.columns) != ["admin_code", *ae_names] or ae["admin_code"].duplicated().any():
        raise DataContractError("descriptor table columns differ from admin_code + 128 AlphaEarth 2017 descriptors")
    D = ae.set_index("admin_code")[ae_names]
    fin = np.isfinite(D.to_numpy())
    if not (fin.all(axis=1) | (~fin).all(axis=1)).all():
        raise DataContractError("descriptor rows must be all finite or all missing")
    return {"frozen": list(frozen), "groups": groups, "interim": interim, "climate": climate, "seasons": seasons,
            "coords": coords, "static": static, "idp": idp, "ae": D, "ae_names": ae_names,
            **({"acled_agg": acled} if acled_agg else {})}


def oracle_names(horizon):
    m = min(int(horizon), MAX_ORACLE_MONTHS)
    return [f"oracle_{v}_o{k}" for k in range(1, m + 1) for v in ORACLE_VARIABLES]


def feature_order(frozen, ae_names, horizon, idp_local=False, acled_agg=False):
    """Frozen compact296 + 128 AlphaEarth + oracle; with ``acled_agg`` the 14 compact conflict columns are removed (every
    other column keeps its relative order) and the 114 aggregated-ACLED columns follow; with ``idp_local`` the three
    local-IDP columns follow everything."""
    order = list(frozen) + list(ae_names) + oracle_names(horizon)
    if acled_agg:
        missing = [c for c in OLD_ACLED_FEATURES if c not in order]
        if missing:
            raise DataContractError(f"H{horizon}: the frozen order lacks compact conflict columns {missing}")
        order = [c for c in order if c not in OLD_ACLED_FEATURES] + list(ACLED_AGG_FEATURES)
    order += list(IDP_LOCAL_FEATURES) if idp_local else []
    want = expected_features(horizon, idp_local, acled_agg)
    if len(order) != want or len(set(order)) != len(order):
        raise DataContractError(f"H{horizon}: feature order has {len(order)} names, expected {want}")
    return order


def oracle_block(climate, admin, origin, horizon):
    """Realized monthly anomalies at calendar months O+1..O+min(H,6) (looked up by calendar month), NaN kept."""
    m = min(int(horizon), MAX_ORACLE_MONTHS)
    cols, obs = {}, {}
    for k in range(1, m + 1):
        ai, mi, ok = climate.index_of(admin, origin + k)
        for v in ORACLE_VARIABLES:
            cols[f"oracle_{v}_o{k}"] = np.where(ok, climate.values[v][ai, mi], np.nan)
        obs[k] = origin + k
    return pd.DataFrame(cols, index=None), obs


def idp_block(idp_obs, iso3, origin):
    """Latest observed national IDP stock with report month <= O and its age O - report (origin_safe semantics)."""
    stock, report = np.full(len(origin), np.nan), np.full(len(origin), np.nan)
    groups = idp_obs.groupby("iso3", sort=False).indices
    oo, os_ = idp_obs["report_ord"].to_numpy(np.int64), idp_obs["stock"].to_numpy(float)
    codes = pd.Series(list(iso3), dtype=object)
    for code, idx in pd.Series(np.arange(len(origin))).groupby(codes.to_numpy(), dropna=True).indices.items():
        if code not in groups:
            continue
        av = groups[code]
        p = np.searchsorted(oo[av], origin[idx], side="right") - 1
        ok = p >= 0
        stock[idx[ok]] = os_[av[p[ok]]]
        report[idx[ok]] = oo[av[p[ok]]]
    return pd.DataFrame({"idp_admin0_latest_stock": stock, "idp_admin0_latest_age_months": origin - report}), report


# --------------------------------------------------------------------------- local IPCCH-area IDP suffix (task 10-17)
#
# Task ``10-17-ipcch-idp-augmented-pooled`` (prd.md R2-R3, design.md section 3): the supplied capped-fill stock
# x(a, m) = ``idp_ffill6`` of ``idp_ipcch_monthly.parquet``, joined by admin_code and calendar month (never by its
# nullable ISO3). At O = T - H: x(O), mean x(O-2..O) and mean x(O-5..O), each window requiring every calendar month
# nonmissing (else NaN). Computed on the complete source calendar; missing internal months are NaN, never the previous
# record. No further fill, scaling or missingness predictor; coverage/staleness columns are QC only.

IDP_LOCAL_ROLE = "idp_ipcch_monthly"
IDP_LOCAL_VALUE = "idp_ffill6"
IDP_LOCAL_FEATURES = ("idp_ipcch_ffill6_current", "idp_ipcch_ffill6_ma3", "idp_ipcch_ffill6_ma6")
IDP_LOCAL_WINDOWS = (1, 3, 6)
IDP_LOCAL_QC = ("pct_area_ffill6", "n_dtm_units_ffill6", "months_since_round_mean", "months_since_round_max")


def expected_features(horizon, idp_local=False, acled_agg=False):
    return (EXPECTED_FEATURES[int(horizon)] + (len(IDP_LOCAL_FEATURES) if idp_local else 0)
            + (len(ACLED_AGG_FEATURES) - len(OLD_ACLED_FEATURES) if acled_agg else 0))


def invariant_feature_names(order):
    """Columns identical across horizons for the same target row (task 10-17-ipcch-idp-horizon-stacking): the frozen
    static29 block (per admin), the identifier block (lat/lon at the target + target-calendar dummies) and the 128
    AlphaEarth 2017 descriptors. Every other column depends on the origin O = T - H."""
    cp, _, _ = ae_modules()
    static = list(order[:29])
    if not all(cp.is_static_name(c) for c in static):
        raise DataContractError("the first 29 feature names are not the frozen static block")
    return set(static) | set(cp.IDENTIFIER_FEATURES) | {c for c in order if c.startswith(AE_PREFIXES)}


def idp_local_grid(df: pd.DataFrame):
    """Validated admin x calendar-month grid of ``idp_ffill6`` (+ QC columns present) and a source summary.

    Keys must be unique nonnull integers with valid months; the value must be finite and nonnegative or missing."""
    cp, _, _ = ae_modules()
    for c in ("admin_code", "year", "month", IDP_LOCAL_VALUE):
        if c not in df.columns:
            raise DataContractError(f"local IDP source lacks {c}")
    for c in ("admin_code", "year", "month"):
        if df[c].isna().any() or not pd.api.types.is_integer_dtype(df[c].dtype):
            raise DataContractError(f"local IDP {c} must be a nonnull integer key")
    if not df["month"].between(1, 12).all():
        raise DataContractError("local IDP months must be 1-12")
    if df.duplicated(["admin_code", "year", "month"]).any():
        raise DataContractError("local IDP source has duplicate admin_code/year/month keys")
    x = pd.to_numeric(df[IDP_LOCAL_VALUE], errors="raise").to_numpy(np.float64)
    if np.isinf(x).any() or (x[np.isfinite(x)] < 0).any():
        raise DataContractError("local IDP values must be finite and nonnegative or missing")
    qc = [c for c in IDP_LOCAL_QC if c in df.columns]
    admin = df["admin_code"].to_numpy(np.int64)
    ords = month_ord(df["year"], df["month"])
    area_ids = np.unique(admin)
    first, last = int(ords.min()), int(ords.max())
    n_months = last - first + 1
    ai, mi = np.searchsorted(area_ids, admin), ords - first
    values = {}
    for v, col in [(IDP_LOCAL_VALUE, x)] + [(c, pd.to_numeric(df[c], errors="raise").to_numpy(np.float64)) for c in qc]:
        arr = np.full((len(area_ids), n_months), np.nan)      # absent calendar months stay NaN
        arr[ai, mi] = col
        values[v] = arr
    summary = {"rows": int(len(df)), "admins": int(len(area_ids)), "first_month": month_label(first),
               "last_month": month_label(last), "calendar_complete": bool(len(df) == len(area_ids) * n_months),
               "nonmissing_value": int(np.isfinite(x).sum()), "qc_columns": qc,
               "missing_iso3_admins": int(df.loc[df["iso3"].isna(), "admin_code"].nunique()) if "iso3" in df.columns else None}
    return cp.Grid(area_ids, first, n_months, values), summary


def load_idp_local(path):
    return idp_local_grid(pd.read_parquet(path))


def idp_local_arrays(grid):
    """{feature: (n_admins, n_months)} strict calendar windows ending at each month, and their valid-month counts."""
    cp, _, _ = ae_modules()
    x = grid.values[IDP_LOCAL_VALUE]
    finite = np.isfinite(x).astype(np.int64)
    out, counts = {}, {}
    for name, k in zip(IDP_LOCAL_FEATURES, IDP_LOCAL_WINDOWS):
        out[name] = x.copy() if k == 1 else cp.trailing(x, k, k, "mean")
        padded = np.concatenate([np.zeros((x.shape[0], k - 1), np.int64), finite], axis=1)
        counts[name] = np.lib.stride_tricks.sliding_window_view(padded, k, axis=1).sum(axis=2)
    return out, counts


def idp_local_block(grid, admin, origin):
    """The three suffix columns at each row's origin (NaN outside the source grid) and a keyed QC ledger frame."""
    feats, counts = idp_local_arrays(grid)
    ai, mi, ok = grid.index_of(np.asarray(admin, dtype=np.int64), np.asarray(origin, dtype=np.int64))
    block = pd.DataFrame({n: np.where(ok, feats[n][ai, mi], np.nan) for n in IDP_LOCAL_FEATURES})
    led = pd.DataFrame({"idp_local_in_source": ok})
    for n, k in zip(IDP_LOCAL_FEATURES, IDP_LOCAL_WINDOWS):
        led[f"{n}_window_lo_ord"] = np.asarray(origin, dtype=np.int64) - (k - 1)
        led[f"{n}_valid_months"] = np.where(ok, counts[n][ai, mi], 0).astype(np.int64)
    for c in grid.values:
        if c != IDP_LOCAL_VALUE:
            led[f"qc_{c}_at_origin"] = np.where(ok, grid.values[c][ai, mi], np.nan)
    return block, led


def idp_local_completeness(labels, block, horizon):
    """Rows, per-feature nonmissing and all-three-present counts by label kind, target year and country."""
    present = np.isfinite(block[list(IDP_LOCAL_FEATURES)].to_numpy())
    frame = pd.DataFrame({"horizon": int(horizon), "label_kind": labels["label_kind"].to_numpy(), "target_year": labels["year"].to_numpy(),
                          "iso2": labels["iso2"].to_numpy(dtype=object), "rows": 1,
                          **{f"nonmissing.{n}": present[:, j].astype(np.int64) for j, n in enumerate(IDP_LOCAL_FEATURES)},
                          "all_three_present": present.all(axis=1).astype(np.int64), "all_three_missing": (~present).all(axis=1).astype(np.int64)})
    return frame.groupby(["horizon", "label_kind", "target_year", "iso2"], sort=True).sum().reset_index()


# --------------------------------------------------------------------------- aggregated ACLED replacement (task 10-20)
#
# Task ``10-20-ipcch-acled-retrain`` (prd.md D1-D4, design.md section 3): the 18 staged ``acled_agg_*`` monthly series of
# the augmented interim replace the 14 compact296 conflict columns. Every raw series gives x(A), trailing MA3/MA6/MA12
# (>= 2/3/6 observed months) and sample SD12 (>= 6) with the pinned compact primitives; the six event series also give
# share12/months_since/longest_run12/any12 of the explicit NaN-preserving signal x > 0 (never the compact price-shock
# fallback). All 114 columns are gathered at A = O - 1 = T - H - 1, so no window reaches the origin month (a weekly total
# split into month A can contain days of O, never later months). Missing source values stay missing; no fill or scaling.

ACLED_AGG_GROUPS = ("events", "fatalities", "exposure", "exposure_share", "spill_events", "spill_fatalities")
ACLED_AGG_TYPES = ("battles", "erv", "vac")
ACLED_AGG_SOURCES = tuple(f"acled_agg_{g}_{t}" for g in ACLED_AGG_GROUPS for t in ACLED_AGG_TYPES)
ACLED_AGG_EVENT_SOURCES = tuple(f"acled_agg_{g}_{t}" for g in ("events", "spill_events") for t in ACLED_AGG_TYPES)
ACLED_AGG_LAG = 1
ORDINARY_STATS = ("value", "ma3", "ma6", "ma12", "sd12")
STRESS_STATS = ("share12", "months_since", "longest_run12", "any12")
ACLED_AGG_FEATURES = tuple([f"{s}__{k}_at_origin_lag1" for s in ACLED_AGG_SOURCES for k in ORDINARY_STATS]
                           + [f"{s}__nonzero_stress__{k}_at_origin_lag1" for s in ACLED_AGG_EVENT_SOURCES for k in STRESS_STATS])
OLD_ACLED_FEATURES = tuple([f"{s}__{k}_at_origin" for s in ("event_count_violence", "sum_fatalities_violence") for k in ORDINARY_STATS]
                           + [f"event_count_violence__nonzero_stress__{k}_at_origin" for k in STRESS_STATS])


def acled_agg_grid(panel: pd.DataFrame):
    """Area x calendar-month grid of the 18 series from the interim panel (keys area_id/year/month, already unique).
    Values must be numeric, finite and nonnegative or missing; a missing value is never read as zero."""
    cp, _, _ = ae_modules()
    bad = [c for c in ACLED_AGG_SOURCES if not pd.api.types.is_numeric_dtype(panel[c].dtype)]
    if bad:
        raise DataContractError(f"aggregated ACLED columns are not numeric: {bad}")
    if panel.duplicated(list(cp.KEYS)).any():
        raise DataContractError("aggregated ACLED source has duplicate area-month keys")
    grid = cp.Grid.from_long(panel.loc[:, [*cp.KEYS, *ACLED_AGG_SOURCES]], ACLED_AGG_SOURCES, require_complete=False)
    for v, arr in grid.values.items():
        if np.isinf(arr).any() or (arr[np.isfinite(arr)] < 0).any():
            raise DataContractError(f"{v}: aggregated ACLED values must be finite and nonnegative or missing")
    return grid


def acled_lag_name(name):
    if not name.endswith("_at_origin"):
        raise DataContractError(f"unexpected compact feature name {name!r}")
    return name + "_lag1"


def acled_agg_arrays(grid):
    """(name, (n_admins, n_months) array) of the 114 columns in ACLED_AGG_FEATURES order; month u uses months <= u."""
    cp, _, _ = ae_modules()
    for s in ACLED_AGG_SOURCES:
        for name, arr in cp.ordinary_arrays(s, grid.values[s]):
            yield acled_lag_name(name), arr
    for s in ACLED_AGG_EVENT_SOURCES:
        x = grid.values[s]
        signal = np.where(np.isnan(x), np.nan, (np.nan_to_num(x, nan=0.0) > 0).astype(np.float64))
        for name, arr in cp.stress_arrays(f"{s}__nonzero_stress", signal):
            yield acled_lag_name(name), arr


def acled_agg_block(grid, admin, origin):
    """The 114 columns of each row at its ACLED cutoff A = O - 1 (NaN outside the grid) and the cutoff months."""
    cp, _, _ = ae_modules()
    cutoff = np.asarray(origin, dtype=np.int64) - ACLED_AGG_LAG
    index = grid.index_of(np.asarray(admin, dtype=np.int64), cutoff)
    cols = {name: cp.gather(arr, index) for name, arr in acled_agg_arrays(grid)}
    if tuple(cols) != ACLED_AGG_FEATURES:
        raise DataContractError("aggregated ACLED columns differ from the declared order")
    return pd.DataFrame(cols), cutoff


def acled_agg_completeness(labels, block, horizon):
    """Rows and per-column nonmissing counts of the 114 columns by label kind and target year."""
    present = np.isfinite(block[list(ACLED_AGG_FEATURES)].to_numpy())
    frame = pd.DataFrame({"horizon": int(horizon), "label_kind": labels["label_kind"].to_numpy(), "target_year": labels["year"].to_numpy(),
                          "rows": 1, **{f"nonmissing.{n}": present[:, j].astype(np.int64) for j, n in enumerate(ACLED_AGG_FEATURES)}})
    return frame.groupby(["horizon", "label_kind", "target_year"], sort=True).sum().reset_index()


def base_features(sources: dict, rows: pd.DataFrame, countries: pd.DataFrame, horizon: int):
    """Context-free matrix for keyed rows (admin_code, year, month) at origin O = T - H; history columns are NaN
    placeholders filled per context by ``history_block``. Returns (X float64, order, ledger DataFrame)."""
    cp, _, _ = ae_modules()
    h = int(horizon)
    if h not in HORIZONS:
        raise DataContractError(f"horizon {h} is not one of {HORIZONS}")
    keys = pd.DataFrame({"area_id": rows["admin_code"].to_numpy(np.int64), "year": rows["year"].to_numpy(np.int64),
                         "month": rows["month"].to_numpy(np.int64)})
    target = month_ord(keys["year"], keys["month"])
    origin = target - h
    admin = keys["area_id"].to_numpy(np.int64)
    g = sources["groups"]
    monthly = cp.monthly_block(sources["interim"], sources["climate"], keys, [h])[h]
    season, season_ledger = cp.completed_seasons(sources["seasons"], admin, origin)
    cp.assert_season_ledger(season, season_ledger, origin)
    ident = cp.identifier_block(keys, sources["coords"])
    static = sources["static"].reindex(admin).reset_index(drop=True)[g["static"]]
    iso3 = countries.set_index("admin_code")["iso3"].reindex(admin).to_numpy(dtype=object)
    idp, idp_report = idp_block(sources["idp"], iso3, origin)
    history = pd.DataFrame(np.full((len(keys), 5), np.nan), columns=list(HISTORY_FEATURES))
    frame = pd.concat([static, monthly, season, ident, history, idp], axis=1)
    if list(frame.columns) != sources["frozen"]:
        raise DataContractError(f"H{h}: assembled compact block differs from the frozen compact296 order")
    acled = sources.get("acled_agg")
    if acled is not None:      # task 10-20: the compact conflict columns are not model inputs of this arm
        frame = frame.drop(columns=list(OLD_ACLED_FEATURES))
    ae = sources["ae"].reindex(admin)
    if ae.index.isna().any() or len(ae) != len(admin):
        raise DataContractError("cohort admin missing from the descriptor table")
    oracle, obs_months = oracle_block(sources["climate"], admin, origin, h)
    local = sources.get("idp_local")
    order = feature_order(sources["frozen"], sources["ae_names"], h, idp_local=local is not None, acled_agg=acled is not None)
    parts = [frame.to_numpy(np.float64), ae.to_numpy(np.float64),
             oracle.to_numpy(np.float64) if len(oracle.columns) else np.zeros((len(keys), 0))]
    if acled is not None:
        acled_block, acled_cutoff = acled_agg_block(acled, admin, origin)
        parts.append(acled_block[list(ACLED_AGG_FEATURES)].to_numpy(np.float64))
    if local is not None:
        local_block, local_ledger = idp_local_block(local, admin, origin)
        parts.append(local_block[list(IDP_LOCAL_FEATURES)].to_numpy(np.float64))
    X = np.ascontiguousarray(np.hstack(parts))
    if X.shape[1] != len(order) or np.isinf(X).any():
        raise DataContractError(f"H{h}: matrix shape/infinite values")
    ledger = pd.DataFrame({"admin_code": admin, "target_ord": target, "origin_ord": origin, "horizon": h,
                           "history_bound_ord": history_bound(target, h), "idp_report_ord": idp_report,
                           "season_cutoff_date": season_ledger["season_cutoff_date"].to_numpy()})
    for k, o in obs_months.items():
        ledger[f"oracle_o{k}_observation_ord"] = o
    ledger["oracle_assumed_available_ord"] = origin
    if local is not None:
        ledger = pd.concat([ledger, local_ledger], axis=1)
        ledger["idp_local_assumed_available_ord"] = origin
    if acled is not None:
        ledger["acled_agg_cutoff_ord"] = acled_cutoff
    return X, order, ledger


def history_columns(order):
    return [order.index(c) for c in HISTORY_FEATURES]


def oracle_completeness(X, order, horizon):
    """Per-row count of finite oracle values and whether all expected oracle columns are present (None at H0)."""
    names = oracle_names(horizon)
    if not names:
        return None, None
    idx = [order.index(c) for c in names]
    finite = np.isfinite(X[:, idx])
    return finite.sum(axis=1), finite.all(axis=1)


# --------------------------------------------------------------------------- dataset build (cloud stage 1; also local no-fit)


INPUT_ROLES = ("raw_panel", "country_lookup", "areas", "analyses", "interim", "climate_monthly", "climate_seasonal",
               "idp_admin0_monthly", "static29", "descriptors", "compact_manifest")


def raw_qc_ledger(ledger: pd.DataFrame, labels: pd.DataFrame, relationships: pd.DataFrame, countries: pd.DataFrame, codes,
                  reclassified_keys=None) -> pd.DataFrame:
    """One compact row per raw area-month: target-QC verdict/reason, missing-P5 fill, reported phase, the raw row's
    own round family and augmentation role. Full source values stay in the hashed raw input (not duplicated).

    ``raw_row_family`` is the (country, this raw month) family of the raw row itself. For a copy recipient it is NOT
    the donor family: the copy's report family is ``labels.source_family`` (donor country/original month).
    ``reclassified_keys`` (task 10-28): packed keys of nonempty share-valid raw rows that are verified upstream copies
    (role ``upstream_copy_reclassified``); the valid raw keys must then equal the originals plus exactly these keys."""
    iso2 = countries.set_index("admin_code")["iso2"].reindex(ledger["admin_code"].to_numpy()).to_numpy(dtype=object)
    cidx = {c: i for i, c in enumerate(codes)}
    fam = np.array([family_code(cidx[c], m) if isinstance(c, str) else -1
                    for c, m in zip(iso2, ledger["month_ord"].to_numpy())], dtype=np.int64)
    out = pd.DataFrame({"admin_code": ledger["admin_code"].to_numpy(np.int64), "year": ledger["year"].to_numpy(np.int64),
                        "month": ledger["month"].to_numpy(np.int64), "month_ord": ledger["month_ord"].to_numpy(np.int64),
                        "iso2": iso2, "raw_row_family": fam, "label_blank": ledger["label_blank"].to_numpy(),
                        "target_valid": ledger["target_valid"].to_numpy(np.int64), "target_reason": ledger["target_reason"].to_numpy(dtype=object),
                        "p5_missing_filled": ledger["p5_missing_filled"].to_numpy(np.int64),
                        "phase_sum_str": ledger["phase_sum_str"].to_numpy(dtype=object),
                        "reported_phase": ledger["reported_phase"].to_numpy(np.float64)})
    key = out["admin_code"].to_numpy(np.int64) * SCALE + out["month_ord"].to_numpy(np.int64)
    copied = labels.loc[labels["label_kind"] == "copy"]
    ckey = copied["admin_code"].to_numpy(np.int64) * SCALE + copied["month_ord"].to_numpy(np.int64)
    role = np.where(out["target_valid"].to_numpy() == 1, "original_label", "none").astype(object)
    role[np.isin(key, ckey)] = "copy_recipient"
    tried = relationships.loc[relationships["recipient_row"] >= 0]
    tkey = tried["admin_code"].to_numpy(np.int64) * SCALE + tried["recipient_month_ord"].to_numpy(np.int64)
    blocked = np.isin(key, tkey) & (role == "none")
    role[blocked] = "candidate_recipient_not_filled"
    reclassified = np.zeros(0, np.int64) if reclassified_keys is None else np.asarray(sorted(reclassified_keys), dtype=np.int64)
    if len(reclassified):
        rk = np.isin(key, reclassified)
        if int(rk.sum()) != len(reclassified) or (out["target_valid"].to_numpy()[rk] != 1).any():
            raise DataContractError("reclassified upstream copies must be share-valid raw rows")
        role[rk] = "upstream_copy_reclassified"
    out["augmentation_role"] = role
    if len(out) != len(ledger) or out.duplicated(["admin_code", "month_ord"]).any():
        raise DataContractError("raw-QC ledger rows differ from the raw input")
    orig = labels.loc[labels["label_kind"] == "original"]
    if set(key[out["target_valid"].to_numpy() == 1]) != set(orig["admin_code"].to_numpy(np.int64) * SCALE + orig["month_ord"].to_numpy(np.int64)) | set(reclassified.tolist()):
        raise DataContractError("raw-QC valid keys differ from the original-arm labels")
    return out


def oracle_completeness_table(labels, X, order, horizon):
    """Rows, all-oracle-present share and per-column nonmissing counts by arm and target year (H0: not applicable)."""
    n_finite, complete = oracle_completeness(X, order, horizon)
    out = []
    names = oracle_names(horizon)
    for arm, mask in (("original", (labels["label_kind"] == "original").to_numpy()), ("validity_augmented", np.ones(len(labels), bool))):
        for year in sorted(set(labels.loc[mask, "year"])):
            m = mask & (labels["year"].to_numpy() == year)
            rec = {"arm": arm, "horizon": int(horizon), "target_year": int(year), "rows": int(m.sum())}
            if not names:
                rec.update(oracle_status="not_applicable_h0", all_oracle_present_rows=None, all_oracle_present_share=None)
            else:
                rec.update(oracle_status="incomplete_rows_present" if not complete[m].all() else "complete",
                           all_oracle_present_rows=int(complete[m].sum()), all_oracle_present_share=float(complete[m].mean()))
                for j, c in enumerate(names):
                    rec[f"nonmissing.{c}"] = int(np.isfinite(X[m, order.index(c)]).sum())
            out.append(rec)
    return pd.DataFrame(out)


def source_support_check(sources: dict, labels, countries, horizon, cutoff_ord, seed=20261017, row_groups=None) -> pd.DataFrame:
    """Post-cutoff perturbation of the context-free sources: every interim/climate value after ``cutoff_ord``, every
    season ending after the first day of cutoff+1, every national IDP report and (when present) every local IDP month
    after the cutoff. Rows with origin <= cutoff must keep every non-oracle feature; an oracle column may change only where its observation month is
    after the cutoff. Rows with origin == cutoff are counted separately (own-origin boundary); changed rows with
    origin > cutoff are the power control. Reported-phase history is NOT covered here (base_features leaves it as a
    placeholder); history timing/exclusion is checked by ``reference_history_check`` and its tests.
    Aggregated ACLED (task 10-20, when present) is perturbed from the cutoff month itself (every month after A = O - 1):
    for rows with origin == cutoff that month is their own origin O, which must not reach their 114 columns.
    ``row_groups`` ({name: row mask}, e.g. original/copy or fitting/scoring rows) adds per-group counts."""
    cp, _, _ = ae_modules()
    rng = np.random.default_rng(seed)

    def perturbed(grid, after=cutoff_ord):
        cols = (np.arange(grid.n_months) + grid.first_ord) > after
        values = {}
        for v, arr in grid.values.items():
            arr = arr.copy()
            arr[:, cols] = arr[:, cols] + rng.normal(100.0, 10.0, arr[:, cols].shape)
            values[v] = arr
        return cp.Grid(grid.area_ids, grid.first_ord, grid.n_months, values)

    seasons = sources["seasons"].copy()
    first_after = pd.Timestamp(year=(cutoff_ord + 1) // 12, month=(cutoff_ord + 1) % 12 + 1, day=1)
    late = (pd.to_datetime(seasons["gs_end_date_exclusive"]) > first_after).to_numpy()
    for m in cp.SEASON_METRICS:
        seasons.loc[late, m] = seasons.loc[late, m] + 100.0
    idp = sources["idp"].copy()
    late_idp = idp["report_ord"].to_numpy() > cutoff_ord
    idp.loc[late_idp, "stock"] = idp.loc[late_idp, "stock"] + 1e6
    alt = {**sources, "interim": perturbed(sources["interim"]), "climate": perturbed(sources["climate"]), "seasons": seasons, "idp": idp}
    if sources.get("idp_local") is not None:      # local IDP months after the cutoff (task 10-17)
        alt["idp_local"] = perturbed(sources["idp_local"])
    if sources.get("acled_agg") is not None:      # aggregated ACLED from the cutoff month on (task 10-20)
        alt["acled_agg"] = perturbed(sources["acled_agg"], cutoff_ord - ACLED_AGG_LAG)
    A, order, rows = base_features(sources, labels, countries, horizon)
    B, _, _ = base_features(alt, labels, countries, horizon)
    same = (A == B) | (np.isnan(A) & np.isnan(B))
    origin = rows["origin_ord"].to_numpy()
    early, at = origin <= cutoff_ord, origin == cutoff_ord
    out = []
    for j, name in enumerate(order):
        allowed = np.zeros(len(rows), bool)
        if name.startswith("oracle_"):
            k = int(name.rsplit("_o", 1)[1])
            allowed = rows[f"oracle_o{k}_observation_ord"].to_numpy() > cutoff_ord
        changed = ~same[:, j]
        out.append({"horizon": int(horizon), "cutoff": month_label(cutoff_ord), "feature": name,
                    **({"perturbed_from": month_label(cutoff_ord + (name not in ACLED_AGG_FEATURES))}
                       if sources.get("acled_agg") is not None else {}),
                    "history_placeholder": name in HISTORY_FEATURES,
                    "rows_origin_le_cutoff": int(early.sum()), "rows_origin_eq_cutoff": int(at.sum()),
                    "violations": int((changed & early & ~allowed).sum()),
                    "violations_origin_eq_cutoff": int((changed & at & ~allowed).sum()),
                    "oracle_changed_after_cutoff": int((changed & early & allowed).sum()),
                    "power_changed_origin_gt_cutoff": int((changed & ~early).sum())})
        for g, m in (row_groups or {}).items():
            m = np.asarray(m, dtype=bool)
            out[-1].update({f"rows_origin_le_cutoff.{g}": int((early & m).sum()), f"rows_origin_eq_cutoff.{g}": int((at & m).sum()),
                            f"violations.{g}": int((changed & early & ~allowed & m).sum()),
                            f"power_changed_origin_gt_cutoff.{g}": int((changed & ~early & m).sum())})
    return pd.DataFrame(out)


def build_dataset(inputs: dict, out_dir, horizons=HORIZONS, log=print, matrix_dir=None, keep=False, idp_local=False,
                  acled_agg=False, ch_links=False) -> dict:
    """Targets, lineage, augmentation and context-free features from pinned inputs into a new directory.

    ``inputs`` maps every INPUT_ROLES role to a verified local path. Writes keyed ledgers, per-H base matrices
    (labels order, history columns filled with the no-exclusion raw history for inspection only; fitting contexts
    rebuild them), feature orders, row ledgers and oracle completeness. Returns the summary also saved as
    ``dataset-summary.json``. ``matrix_dir`` (default ``out_dir``) receives the large ``base_X_hHH.npy`` matrices;
    with ``keep`` the in-memory objects are returned under ``objects`` (labels, countries, observations, X, order,
    rows per H). With ``idp_local`` the ``idp_ipcch_monthly`` role is required and the three local-IDP columns are
    appended after every existing feature, with a keyed ledger and completeness table per H. With ``acled_agg`` (task
    10-20) the interim must carry the 18 aggregated-ACLED series: the 14 compact conflict columns are replaced by the
    114 lag-1 columns before the local-IDP suffix, with a completeness table per H. With ``ch_links`` (task 10-28) the
    ``ch_links`` role is required and the CH validity correction (``ch_augment`` / ``ch_history_observations``) is
    applied after the IPC route; ``ch_links.csv.gz`` (validated) and ``ch_relationships.csv.gz`` are added."""
    import time
    t0 = time.time()
    missing = sorted(set(INPUT_ROLES + ((IDP_LOCAL_ROLE,) if idp_local else ()) + ((CH_LINKS_ROLE,) if ch_links else ())) - set(inputs))
    if missing:
        raise DataContractError(f"inputs lack roles {missing}")
    os.makedirs(out_dir, exist_ok=False)
    path = lambda n: os.path.join(out_dir, n)
    matrix_dir = matrix_dir or out_dir
    os.makedirs(matrix_dir, exist_ok=True)
    kept = {}
    ledger = build_label_ledger(inputs["raw_panel"])
    countries = country_table(inputs["country_lookup"])
    reports, index = validity_reports(inputs["areas"], inputs["analyses"])
    aug = augment(ledger, countries, reports, index)
    labels = aug["labels"]
    log(f"[{time.time() - t0:6.0f}s] labels {aug['counts']['share_valid_originals']} originals + {aug['counts']['copies']} copies")
    cha = None
    if ch_links:      # task 10-28: CH reference windows after the unchanged IPC route
        ch = ch_link_table(inputs[CH_LINKS_ROLE], ledger, countries)
        cha = ch_augment(aug, ledger, countries, ch)
        labels = cha["labels"]
        ch.to_csv(path("ch_links.csv.gz"), index=False)
        cha["ch_relationships"].to_csv(path("ch_relationships.csv.gz"), index=False)
        log(f"[{time.time() - t0:6.0f}s] CH: {cha['counts']['added_copies']} added copies, "
            f"{cha['counts']['reclassified_upstream_copies']} reclassified upstream copies, {cha['counts']['cross_country_aliases']} aliases")
    labels.to_csv(path("labels.csv.gz"), index=False)
    aug["donors"].drop(columns=[c for c in aug["donors"].columns if c.startswith("p") and c[1:].isdigit()], errors="ignore") \
        .to_csv(path("donors.csv.gz"), index=False)
    aug["relationships"].to_csv(path("relationships.csv.gz"), index=False)
    aug["recipients"].to_csv(path("recipients.csv.gz"), index=False)
    reports.to_csv(path("reports.csv.gz"), index=False)
    ambiguous = {f"{c}/{month_label(m)}": ids for (c, m), ids in index.items() if len(ids) > 1}
    obs = history_observations(ledger, countries, aug["country_codes"])
    moved = None
    if cha is not None:
        obs, moved = ch_history_observations(obs, ch, cha["renames"], cha["aliases"])
    obs.to_csv(path("history_observations.csv.gz"), index=False)
    if cha is None:
        qc = raw_qc_ledger(ledger, labels, aug["relationships"], countries, aug["country_codes"])
    else:
        tried = pd.concat([aug["relationships"][["admin_code", "recipient_month_ord", "recipient_row"]],
                           cha["ch_relationships"][["admin_code", "recipient_month_ord", "recipient_row"]]], ignore_index=True)
        qc = raw_qc_ledger(ledger, labels, tried, countries, aug["country_codes"], reclassified_keys=cha["reclassified_keys"])
    qc.to_csv(path("raw_qc_ledger.csv.gz"), index=False)
    qc_summary = {"rows": int(len(qc)), "raw_rows": int(len(ledger)), "valid": int(qc["target_valid"].sum()),
                  "reasons": qc["target_reason"].value_counts().to_dict(), "augmentation_role": qc["augmentation_role"].value_counts().to_dict()}
    pd.DataFrame({"country_index": np.arange(len(aug["country_codes"])), "iso2": aug["country_codes"]}).to_csv(path("country_codes.csv"), index=False)
    by_country = labels.groupby(["iso2", "label_kind"]).size().unstack(fill_value=0).reset_index()
    by_country.to_csv(path("labels_by_country.csv"), index=False)
    del ledger
    sources = load_sources(inputs, acled_agg=acled_agg)
    local_summary = None
    if idp_local:
        sources["idp_local"], local_summary = load_idp_local(inputs[IDP_LOCAL_ROLE])
    log(f"[{time.time() - t0:6.0f}s] feature sources loaded")
    per_h = {}
    for h in horizons:
        X, order, rows = base_features(sources, labels, countries, h)
        block, src, _ = history_block(labels["admin_code"].to_numpy(), labels["month_ord"].to_numpy(), h, obs)
        X[:, history_columns(order)] = block
        ref = reference_history_check(labels["admin_code"].to_numpy(), labels["month_ord"].to_numpy(), h, obs, None, block, src)
        np.save(os.path.join(matrix_dir, f"base_X_h{h:02d}.npy"), X)
        if keep:
            kept[h] = {"X": X, "order": order, "rows": rows}
        pd.DataFrame({"position": np.arange(len(order)), "name": order}).to_csv(path(f"feature_order_h{h:02d}.csv"), index=False)
        rows.to_csv(path(f"row_ledger_h{h:02d}.csv.gz"), index=False)
        comp = oracle_completeness_table(labels, X, order, h)
        comp.to_csv(path(f"oracle_completeness_h{h:02d}.csv"), index=False)
        per_h[str(h)] = {"rows": int(X.shape[0]), "features": int(X.shape[1]), "feature_order_sha256": list_sha256(order),
                         "nan_fraction": float(np.isnan(X).mean()), "history_reference_check": ref,
                         "all_nan_columns": [c for j, c in enumerate(order) if np.isnan(X[:, j]).all()]}
        if idp_local:
            n0 = order.index(IDP_LOCAL_FEATURES[0])      # by name: 424/436, or 524/536 with aggregated ACLED
            if order[n0:] != list(IDP_LOCAL_FEATURES):
                raise DataContractError(f"H{h}: the local-IDP columns are not the final suffix")
            local = pd.DataFrame(X[:, n0:], columns=order[n0:])
            led = pd.concat([pd.DataFrame({"row": np.arange(len(labels)), "admin_code": rows["admin_code"].to_numpy(),
                                           "target_ord": rows["target_ord"].to_numpy(), "origin_ord": rows["origin_ord"].to_numpy(),
                                           "label_kind": labels["label_kind"].to_numpy(), "iso2": labels["iso2"].to_numpy(dtype=object)}),
                             local, rows[[c for c in rows.columns if c.startswith(("idp_ipcch_", "qc_", "idp_local_"))]]], axis=1)
            led.to_csv(path(f"idp_local_ledger_h{h:02d}.csv.gz"), index=False)
            idp_local_completeness(labels, local, h).to_csv(path(f"idp_local_completeness_h{h:02d}.csv"), index=False)
            present = np.isfinite(local.to_numpy())
            per_h[str(h)]["idp_local"] = {"prefix_features": n0, "feature_prefix_order_sha256": list_sha256(order[:n0]),
                                          "suffix": list(order[n0:]),
                                          "nonmissing": {c: int(present[:, j].sum()) for j, c in enumerate(order[n0:])},
                                          "all_three_present": int(present.all(axis=1).sum()),
                                          "all_three_missing": int((~present).all(axis=1).sum())}
        if acled_agg:
            idx = [order.index(c) for c in ACLED_AGG_FEATURES]
            block = pd.DataFrame(X[:, idx], columns=list(ACLED_AGG_FEATURES))
            acled_agg_completeness(labels, block, h).to_csv(path(f"acled_agg_completeness_h{h:02d}.csv"), index=False)
            present = np.isfinite(block.to_numpy())
            per_h[str(h)]["acled_agg"] = {"removed": list(OLD_ACLED_FEATURES), "first_position": idx[0],
                                          "positions_contiguous": idx == list(range(idx[0], idx[0] + len(idx))),
                                          "old_columns_present": [c for c in OLD_ACLED_FEATURES if c in order],
                                          "nonmissing": {c: int(present[:, j].sum()) for j, c in enumerate(ACLED_AGG_FEATURES)},
                                          "all_nan_columns": [c for j, c in enumerate(ACLED_AGG_FEATURES) if not present[:, j].any()],
                                          "cutoff_lag_months": ACLED_AGG_LAG}
        log(f"[{time.time() - t0:6.0f}s] H{h}: {X.shape}")
    summary = {"stage": "ipcch-validity-dataset", "counts": aug["counts"], "raw_qc": qc_summary, "ambiguous_country_starts": ambiguous,
               "reports": reports["status"].value_counts().to_dict(), "horizons": per_h,
               "history_source": "raw panel overall_phase 1-5 (original reports only); interim corrected labels are not used",
               "availability": "original reports available at their observation-month end; copies inherit it",
               **({"idp_local_source": local_summary,
                   "idp_local_time_convention": "retrospective: local IDP assumed available at report-month end; x(O), "
                                                "strict mean x(O-2..O) and x(O-5..O); never after O"} if idp_local else {}),
               **({"acled_agg_time_convention": "aggregated ACLED at A = O - 1 for every fitting and scoring row: x(A), "
                                                "trailing MA3/6/12 (>= 2/3/6 observed) and sample SD12 (>= 6) ending at A; "
                                                "persistence of x > 0 ending at A; never month O or later; retrospective "
                                                "2026-10-20 export vintage"} if acled_agg else {}),
               **({"ch_correction": {**cha["counts"], "history_events_moved_to_nominal_month": moved,
                                     "history_events": int(len(obs)), "history_aliased_events": int((obs["family_alias"] >= 0).sum()),
                                     "time_convention": "CH copies and reclassified upstream copies: nominal source and availability "
                                                        "= reference-window start month end (a retrospective modeling convention, not "
                                                        "a verified publication date)"}} if cha is not None else {}),
               "elapsed_seconds": round(time.time() - t0, 1)}
    with open(path("dataset-summary.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    if keep:
        summary = {**summary, "objects": {"labels": labels, "countries": countries, "observations": obs, "horizons": kept}}
    return summary


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Build the validity-augmented IPCCH dataset (no model fitting).")
    ap.add_argument("--manifest", required=True, help="input manifest: files.{role}.{uri,sha256}")
    ap.add_argument("--out", required=True, help="new output directory")
    ap.add_argument("--horizon", type=int, action="append")
    ap.add_argument("--idp-local", action="store_true", help="append the three local-IDP columns (needs idp_ipcch_monthly)")
    ap.add_argument("--acled-agg", action="store_true", help="replace the compact conflict columns by the 114 lag-1 "
                                                             "aggregated-ACLED columns (interim with acled_agg_*)")
    args = ap.parse_args(argv)
    from research_cloud.training.common import resolve_inputs
    work = args.out + ".inputs"
    inputs, manifest = resolve_inputs(args.manifest, work)
    summary = build_dataset(inputs, args.out, tuple(args.horizon or HORIZONS), idp_local=args.idp_local, acled_agg=args.acled_agg)
    print(json.dumps({k: summary[k] for k in ("counts", "horizons")}, default=str)[:4000])


if __name__ == "__main__":
    main()
