"""IPCCH feature generation for one validated v2 request (task 10-29; design.md "Monthly flow" step 2-4).

``generate`` runs, in order, on the store of the request's mode (R48) that is paired with the bound combination:

1. input choices, each saved as soon as it validates (a later failure never undoes it, R29/R41):
   ACLED keep/refresh (R24-R29, R44, R53, R55, R56; keep without saved history is refused, R44), research-prepared
   families keep/refresh by declared interval (R59), reported-phase snapshot keep/refresh (R62), WFP_Price keep/refresh
   (R64 as corrected 2026-10-30);
2. climate: every base's months through O and completed seasons through the ported shared-script providers (R1, R13,
   R33, R34, R40, R43; ``ClimateSourceMissing`` for O blocks);
3. GPP v3 append + ledger (R9, R49, R54) and VIIRS nightlight append (R64) on the fixed roster geometry (R32);
4. assembly per horizon (T = O + H) on the full roster from the stores (R13, R32, R58, R65), the ACLED monthly series
   at A = O - 1 from the weekly store, output population at O (no future period);
5. one immutable batch (R52) whose manifest records methods, coverage ends, source-level gaps, warnings, acceptance
   records consumed and retained-input references.

Any processing failure raises ``GenerationFailure`` carrying the step and the report of everything already saved.
The bundle (fixed geometry and ACLED tables) must be the one the store was initialised from: real -> the envelope's
accepted bundle (``verify_handoff``); smoke -> the admitted fixture bundle (R48).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

from cloud.batch import remote_sources as rs
from cloud.common.object_store import ObjectStore
from cloud.ipcch import acled as ac
from cloud.ipcch import assembly as asm
from cloud.ipcch import batch as bt
from cloud.ipcch import binding as bd
from cloud.ipcch import climate as cl
from cloud.ipcch import climate_run, geography, gpp, initial, nightlight, retained, wfp
from cloud.ipcch.stores import AcceptanceManifest, StoreError, StoreRoot, VersionedTable

ACLED_TABLE = "acled_agg_weekly"
ACLED_FILES = {"mapping": "fixed/acled/acled_admin1_to_poly.csv", "population": "fixed/acled/admin1_population.csv",
               "neighbours": "fixed/acled/admin1_neighbours.csv", "coverage_start": "fixed/acled/coverage_start.csv",
               "unit_weights": "fixed/acled/unit_admin1_weights.csv", "unit_iso3": "fixed/acled/unit_iso3.csv"}
SERIES_FAMILIES = {"nino34_anom": "history__nino34_anom",
                   "bbg_staple_food": "history__bbg_staple_food__composite_mean",
                   "bbg_oilgas": "history__bbg_oilgas__composite_mean",
                   "bbg_soybean_oil": "history__bbg_soybean_oil__composite_mean",
                   "bbg_global_food": "history__bbg_global_food__composite_mean",
                   "food_price_index_WB": "history__food_price_index_WB", "idp_local": "history__idp_local"}
NATIONAL_TABLE = "history__idp_national"
SNAPSHOT_TABLE = "history__history_snapshot"
ACLED_METHOD = "regional-aggregate converter (research build_acled_agg.py conventions; delivered fixed tables)"


class GenerationFailure(RuntimeError):
    """A blocking failure; ``report`` lists every step already saved (never undone)."""

    def __init__(self, step: str, cause: BaseException, report: Mapping[str, Any]):
        super().__init__(f"IPCCH generation stopped at {step}: {type(cause).__name__}: {cause}")
        self.step, self.cause, self.report = step, cause, dict(report)


@dataclass
class Generation:
    store: ObjectStore
    root: StoreRoot
    binding: bd.Binding
    bundle_dir: str
    request: Mapping[str, Any]                       # validated v2 request (validate_request_v2 output)
    read_ref: Callable[[Mapping[str, str]], bytes]   # exact-generation read + sha256 check (prepare.read_pinned)
    batch_root: str
    # (windows, origin) -> climate_run.ClimateProviders, called with the derived season windows so the seasonal
    # providers, the climate scheduling and assembly use the SAME frame (real: climate_run.real_providers over a transport)
    climate_providers: Callable[[pd.DataFrame, str], Any]
    gpp_acquirer: Any
    nightlight_acquirer: Any
    workdir: str
    now: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))
    report: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ helpers

    def _verified(self, rel: str) -> str:
        """Path of a bundle file whose bytes equal the bound manifest (smoke: admitted inside the fixture root)."""
        path = bd.fixture_file(self.binding, self.bundle_dir, rel) if self.root.mode == "smoke" \
            else os.path.join(self.bundle_dir, rel)
        if bd.sha256_file(path) != self.manifest["files"][rel]["sha256"]:
            raise StoreError(f"{rel}: bytes differ from the bound bundle manifest")
        return path

    def _table(self, name: str) -> VersionedTable:
        return VersionedTable(self.store, self.root, name)

    def _tracked(self) -> list[str]:
        """The retained tables generation may change (each saved change gets a runtime acceptance record, R45)."""
        return sorted({*SERIES_FAMILIES.values(), NATIONAL_TABLE, SNAPSHOT_TABLE, ACLED_TABLE, gpp.HISTORY_TABLE,
                       gpp.LEDGER_TABLE, nightlight.HISTORY_TABLE, wfp.HISTORY_TABLE,
                       *[cl.table_name(b, t) for b in cl.BASES for t in (cl.MONTHLY, cl.SEASONAL)]})

    def _record_runtime(self, step: str) -> None:
        """R45: one ``runtime`` acceptance record per saved VERSION of every tracked table (name = the immutable version
        content path, sha256 = its content), enumerated from the HEAD lineage (no listing, no content read). Idempotent
        by version identity: versions already recorded are skipped, so a record lost to a failed acceptance write is
        repaired by the next reconcile without recomputing or rewriting anything. Initialisation versions carry their
        delivered records (R45 bundle acceptance) and are not re-recorded."""
        acceptance = AcceptanceManifest(self.store, self.root)
        have = acceptance.records()
        known = set(zip(have["name"], have["sha256"]))
        entries = []
        for name in self._tracked():
            head, _ = self._table(name).head()
            if head is None:
                continue
            lineage = head.get("lineage") or [{"version": head["version"], "content": head["content"],
                                               "sha256": head["sha256"], "action": head["record"].get("action")}]
            for v in lineage:
                if v.get("action") == "initialise" or (v["content"], v["sha256"]) in known:
                    continue
                entries.append({"name": v["content"], "sha256": v["sha256"], "kind": "runtime",
                                "source": f"runtime {self.request['run_id']} {step} {name} version {v['version']}",
                                "acceptor": f"ipcch-runtime:{self.request['run_id']}",
                                "accepted_at": self.now().strftime("%Y-%m-%d")})
                known.add((v["content"], v["sha256"]))
        if entries:
            acceptance.append(entries)
            self.report.setdefault("runtime_acceptance", []).extend(e["name"] for e in entries)

    def _step(self, name: str, fn, summary=None):
        try:
            out = fn()
        except GenerationFailure:
            raise
        except Exception as exc:
            self.report.setdefault("failed", {"step": name, "error": f"{type(exc).__name__}: {exc}"})
            for attr in ("climate_run_report", "gpp_report", "nightlight_report"):
                if hasattr(exc, attr):
                    self.report["steps"][name] = getattr(exc, attr)
            try:
                self._record_runtime(name)
            except Exception as rexc:                         # reported, never masks the original failure
                self.report["runtime_acceptance_error"] = f"{type(rexc).__name__}: {rexc}"
            raise GenerationFailure(name, exc, self.report) from exc
        self._record_runtime(name)
        self.report["steps"][name] = summary(out) if summary else out
        return out

    # ------------------------------------------------------------------ run

    def run(self) -> dict[str, Any]:
        req = self.request
        mode, M = req["mode"], req["execution_month"]
        O = bt.add_months(M, -2)
        if not (mode == self.binding.mode == self.root.mode):
            raise StoreError(f"request mode {mode}, binding {self.binding.mode} and store {self.root.mode} must agree (R48)")
        if not req["operations"]["ipcch_generation"]:
            raise StoreError("the request does not select IPCCH feature generation")
        try:                                                  # before any store access or mutation
            bd.require_selection(self.binding, req["ipcch"]["model_combination"])
        except bd.BindingError as exc:
            raise StoreError(str(exc)) from exc
        self.report = {"run_id": req["run_id"], "mode": mode, "execution_month": M, "feature_origin": O, "steps": {},
                       "warnings": []}
        pairing = bd.require_store_pairing(self.store, self.root, self.binding)
        self._record_runtime("reconcile")                 # repairs receipts lost by an earlier interrupted run (R45)
        ident = bd.verify_handoff(self.binding, self.bundle_dir) if mode == "real" \
            else bd.verify_fixture_bundle(self.binding, self.bundle_dir)
        if ident["manifest_sha256"] != pairing["bundle_manifest_sha256"]:
            raise StoreError("the bundle is not the one this store was initialised from (R32/R55)")
        self.manifest = ident["_manifest"]
        roster = [str(a) for a in initial._read(self.store, self.root, "fixed/roster.csv")["admin_code"]]
        declared = geography.declared_extras(self.manifest)
        ipcch = req["ipcch"]

        tables = self._step("acled_tables", lambda: ac.AcledTables.from_files(
            {k: self._verified(rel) for k, rel in ACLED_FILES.items()}),
            summary=lambda t: {"mapped_admin1": int(len(t.mapping)), "polygons": int(len(t.polygons))})
        self._step("acled", lambda: self._acled(ipcch["acled"], tables, O, mode))
        self._step("research_inputs", lambda: self._research(ipcch["research_inputs"], roster))
        self._step("history_snapshot", lambda: self._snapshot(ipcch["history_snapshot"], O))
        self._step("wfp", lambda: wfp.apply(self.store, self.root, ipcch["wfp"], roster=roster,
                                            text=self._text(ipcch["wfp"])))
        windows = self._step("season_windows", lambda: self._season_windows(roster, O),
                             summary=lambda w: {"rows": int(len(w)), "through_season_year": int(w["season_year"].max()),
                                                **self.report.get("season_windows_extension", {})})
        self.windows = windows
        self._step("climate", lambda: climate_run.update_all(
            lambda b, t: self._table(cl.table_name(b, t)), origin=O, roster=roster, windows=windows,
            providers=self.climate_providers(windows, O), declared_extra=declared))
        fc, georep = geography.roster_geometries(self.bundle_dir, self.manifest, roster) if mode == "real" else \
            self._smoke_geometries(roster)
        geoms = rs.native_geometries(fc, roster=roster)
        self.report["geometry"] = georep
        stamp = self.now().strftime("%Y-%m-%d")
        self._step("gpp", lambda: gpp.update_gpp(self.store, self.root, origin=O, roster=roster, geometries=geoms,
                                                 acquirer=self.gpp_acquirer, run_id=req["run_id"],
                                                 workdir=self.workdir, checked_at=stamp))
        self._step("nightlight", lambda: nightlight.update_nightlight(self.store, self.root, origin=O, roster=roster,
                                                                      geometries=geoms, acquirer=self.nightlight_acquirer,
                                                                      run_id=req["run_id"], workdir=self.workdir))
        self._coverage_warnings(O)
        horizons = self._step("assembly", lambda: self._assemble(tables, roster, O),
                              summary=lambda f: {str(h): {"rows": int(len(x)), "columns": int(x.shape[1])} for h, x in f.items()})
        return self._step("batch", lambda: self._write(horizons, roster, M))

    # ------------------------------------------------------------------ inputs

    def _text(self, choice: Mapping[str, Any]) -> str | None:
        if choice.get("action") != "refresh":
            return None
        return self.read_ref(choice["file"]).decode("utf-8")

    def _acled(self, choice, tables, O, mode):
        table = self._table(ACLED_TABLE)
        if choice["action"] == "refresh":
            frame = retained.strict_csv(self._text(choice), "ipcch.acled export", ac.EXPORT_COLUMNS)
            rows, parsed = ac.parse_export(frame, start=choice["start"], end=choice["end"], regions=choice["regions"],
                                           tables=tables)
            ac.refresh(table, rows, start=choice["start"], end=choice["end"], regions=choice["regions"],
                       source_ref=choice["file"], feature_origin=O, tables=tables)
        _, records, _ = ac.saved_weekly(table)
        if not records:
            raise ac.AcledRefreshError(f"{mode} ACLED keep needs saved regional-aggregate history; the first run must "
                                       "refresh (R44)")
        end = ac.coverage_end(records, tables, O)
        if end is None or end < O:
            self.report["warnings"].append(f"ACLED coverage ends {end}, before O {O} (R53)")
        return {"action": choice["action"], "method": ACLED_METHOD, "coverage_end": end,
                **({"source": dict(choice["file"]), "interval": [choice["start"], choice["end"]],
                    "regions": list(choice["regions"])} if choice["action"] == "refresh" else {})}

    def _research(self, choices, roster):
        out = self.report["steps"].setdefault("research_inputs", {})     # per family, visible in a failure report
        for family, choice in choices.items():
            if family == "idp_national":
                out[family] = self._national(choice)
                continue
            table = self._table(SERIES_FAMILIES[family])
            retained.require_initialised(table)
            if choice["action"] == "refresh":
                rows = wfp.parse_refresh(self._text(choice), f"ipcch.research_inputs.{family}")
                retained.refresh_interval(table, rows, start=choice["start"], end=choice["end"],
                                          roster=set(roster), source_ref=choice["file"])
            frame, _ = retained.read_series(table)
            out[family] = {"action": choice["action"], "coverage_end": retained.coverage_end(frame),
                           **({"source": dict(choice["file"]), "interval": [choice["start"], choice["end"]]}
                              if choice["action"] == "refresh" else {}),
                           "method": "research-prepared retained input (delivered history / declared-interval refresh)"}
        return out

    def _national(self, choice):
        table = self._table(NATIONAL_TABLE)
        frame, _, generation = table.read({"iso3": str, "report_month": str})
        if frame is None:
            raise StoreError(f"{NATIONAL_TABLE} is not initialised (R45)")
        if choice["action"] == "refresh":
            new = retained.strict_csv(self._text(choice), "ipcch.research_inputs.idp_national",
                                      ("iso3", "report_month", "stock"))
            asm.validate_idp_national(new)
            if not new["iso3"].str.fullmatch(r"[A-Z]{3}").all():
                raise StoreError("idp_national refresh: iso3 must be three upper-case letters")
            inside = (new["report_month"] >= choice["start"]) & (new["report_month"] <= choice["end"])
            if not inside.all():
                raise StoreError(f"idp_national refresh: {int((~inside).sum())} rows outside {choice['start']}..{choice['end']}")
            kept = frame[(frame["report_month"] < choice["start"]) | (frame["report_month"] > choice["end"])]
            merged = pd.concat([kept, new], ignore_index=True).sort_values(["report_month", "iso3"], kind="mergesort")
            asm.validate_idp_national(merged.reset_index(drop=True))
            table.commit(merged.reset_index(drop=True), {"action": "refresh", "start": choice["start"], "end": choice["end"],
                                                         "source": dict(choice["file"]), "rows": int(len(new))},
                         expected_generation=generation)
            frame = merged
        return {"action": choice["action"], "coverage_end": str(frame["report_month"].max()) if len(frame) else None}

    def _snapshot(self, choice, O):
        table = self._table(SNAPSHOT_TABLE)
        if choice["action"] == "refresh":
            snap = retained.strict_csv(self._text(choice), "ipcch.history_snapshot", retained.SNAPSHOT_COLUMNS)
            retained.replace_snapshot(table, snap, source_ref=choice["file"])
        head, _ = table.head()
        warning = retained.snapshot_warning(head, O)
        if warning:
            self.report["warnings"].append(warning)
        return {"action": choice["action"], "preparation_cutoff": None if head is None else head["record"].get("preparation_cutoff")}

    def _season_windows(self, roster, O):
        """Delivered windows extended through O's season year from the delivered calendar (the seasonal script's own
        ``windows_from_calendar``); the calendar must reproduce the last delivered year exactly. The same frame feeds
        the climate update and assembly (R33)."""
        from cloud.ipcch.spi_spei_seasonal import windows_from_calendar

        cols = ["admin_code", "season_year", "season", "gs_start_date", "gs_end_date_exclusive"]
        stored = initial._read(self.store, self.root, "fixed/season_windows.csv")
        stored = stored.assign(admin_code=stored["admin_code"].astype(str), season_year=stored["season_year"].astype(np.int64))
        last, need = int(stored["season_year"].max()), int(O[:4])
        if need <= last:
            return stored[cols]
        calendar = initial._read(self.store, self.root, "fixed/season_calendar.csv")
        calendar = calendar.assign(admin_code=calendar["admin_code"].astype(str))
        calendar = calendar[calendar["admin_code"].isin(set(roster))]
        if set(calendar["admin_code"]) != set(roster):
            raise StoreError("season calendar does not cover the roster; future windows cannot be derived (R33)")

        def derive(years):
            w = windows_from_calendar(calendar, years)
            return w[w["gs_calendar_valid"] == 1][cols].assign(season_year=lambda f: f["season_year"].astype(np.int64))

        key = ["admin_code", "season_year", "season"]
        check = derive([last]).sort_values(key).reset_index(drop=True)
        ref = stored[stored["season_year"] == last][cols].sort_values(key).reset_index(drop=True)
        if not check.astype(str).equals(ref.astype(str)):
            raise StoreError(f"the season calendar does not reproduce the delivered {last} windows; refusing to derive "
                             "later windows from it")
        new = derive(list(range(last + 1, need + 1)))
        self.report["season_windows_extension"] = {"delivered_through": last, "derived_years": list(range(last + 1, need + 1)),
                                                   "derived_rows": int(len(new))}
        return pd.concat([stored[cols], new], ignore_index=True)

    def _coverage_warnings(self, O):
        """Optional-missing families (R65) whose saved coverage ends before O: features at O are NaN - recorded, not
        blocking (ACLED and the snapshot have their own R53/R62 warnings)."""
        steps = self.report["steps"]
        ends = {"WFP_Price": steps.get("wfp", {}).get("coverage_end"), "GPP_mean": steps.get("gpp", {}).get("coverage_end"),
                "nightlight_mean": steps.get("nightlight", {}).get("coverage_end"),
                **{f: v.get("coverage_end") for f, v in steps.get("research_inputs", {}).items() if f != "idp_national"}}
        for family, end in sorted(ends.items()):
            if end is None or end < O:
                self.report["warnings"].append(f"{family} coverage ends {end}, before O {O} (optional-missing: "
                                               "features at O are NaN, R65)")

    def _smoke_geometries(self, roster):
        for rel in self.manifest["files"]:
            if rel.startswith(geography.GEOMETRY_PREFIX):
                bd.fixture_file(self.binding, self.bundle_dir, rel)              # admitted, no symlink (R48)
        return geography.roster_geometries(self.bundle_dir, self.manifest, roster)

    # ------------------------------------------------------------------ assembly and batch

    def _assemble(self, tables, roster, O):
        inputs = initial.read_assembly_inputs(self.store, self.root, self.binding)
        inputs.season_windows = self.windows                            # the same windows the climate update used
        weekly, records, _ = ac.saved_weekly(self._table(ACLED_TABLE))
        first = min(weekly["week"])[:7] if len(weekly) else bt.add_months(O, -24)
        months = []
        m = min(first, bt.add_months(O, -24))
        while m <= O:
            months.append(m)
            m = bt.add_months(m, 1)
        series = ac.monthly_series(weekly, records, tables, months, roster)
        inputs.acled = series.assign(admin_code=series["admin_code"].astype(np.int64))
        admin = np.array([int(a) for a in roster], dtype=np.int64)
        y, mo = (int(x) for x in O.split("-"))
        origin_ord = y * 12 + mo - 1
        pop, prep = initial.read_population(self.store, self.root, self.binding, O)
        self.report["population"] = prep
        frames = {}
        for h in bt.HORIZONS:
            X, ledger = asm.assemble(inputs, h, admin, np.full(len(admin), origin_ord + h, dtype=np.int64))
            ident = pd.DataFrame({"admin_code": roster, "area_id": roster})
            ident = ident.merge(pop, on="admin_code", how="left", validate="one_to_one")
            frames[h] = pd.concat([ident[list(bt.IDENTITY)].reset_index(drop=True), X.reset_index(drop=True)], axis=1)
        return frames

    def _write(self, horizons, roster, M):
        req = self.request
        refs = {}
        names = [*SERIES_FAMILIES.values(), NATIONAL_TABLE, SNAPSHOT_TABLE, ACLED_TABLE, gpp.HISTORY_TABLE,
                 gpp.LEDGER_TABLE, nightlight.HISTORY_TABLE, wfp.HISTORY_TABLE, bd.BINDING_TABLE,
                 *[cl.table_name(b, t) for b in cl.BASES for t in (cl.MONTHLY, cl.SEASONAL)]]
        for name in sorted(set(names)):
            head, generation = self._table(name).head()
            if head is not None:
                refs[name] = {"version": head["version"], "sha256": head["sha256"], "generation": generation}
        acceptance = AcceptanceManifest(self.store, self.root).records()
        steps = self.report["steps"]
        climate = steps.get("climate", {})
        generation = {
            "methods": {"climate": climate.get("methods"), "GPP_mean": gpp.METHOD_ID, "nightlight_mean": nightlight.METHOD_ID,
                        "WFP_Price": wfp.METHOD, "acled": ACLED_METHOD},
            "coverage_end": {"acled": steps["acled"]["coverage_end"], "GPP_mean": steps["gpp"].get("coverage_end"),
                             "nightlight_mean": steps["nightlight"].get("coverage_end"),
                             "WFP_Price": steps["wfp"].get("coverage_end"),
                             **{f: v.get("coverage_end") for f, v in steps["research_inputs"].items()},
                             "history_snapshot": steps["history_snapshot"].get("preparation_cutoff")},
            "gaps": {"climate_monthly": climate.get("gaps"), "climate_seasonal": climate.get("season_gaps"),
                     "GPP_unpublished": steps["gpp"].get("unpublished"), "nightlight": steps["nightlight"].get("gaps")},
            "warnings": list(self.report["warnings"]), "population": self.report.get("population"),
            "geometry": self.report.get("geometry"), "inputs": {k: steps[k] for k in ("acled", "research_inputs",
                                                                                    "history_snapshot", "wfp")},
        }
        batch_id = bt.new_batch_id(req["run_id"], M)
        ref, manifest = bt.write_batch(
            self.store, self.batch_root, batch_id=batch_id, run_id=req["run_id"], mode=req["mode"], execution_month=M,
            binding=self.binding, horizons=horizons, roster=roster, generation=generation,
            acceptance=acceptance[["name", "sha256", "acceptor", "accepted_at", "kind"]].to_dict("records"),
            retained_refs=refs, generated_at=self.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
        return {"batch_id": batch_id, "manifest_ref": ref}
