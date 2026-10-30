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
    climate_providers: Any                           # climate_run.ClimateProviders (EE transport / table providers)
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
            raise GenerationFailure(name, exc, self.report) from exc
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
        self.report = {"run_id": req["run_id"], "mode": mode, "execution_month": M, "feature_origin": O, "steps": {},
                       "warnings": []}
        pairing = bd.require_store_pairing(self.store, self.root, self.binding)
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
        windows = initial._read(self.store, self.root, "fixed/season_windows.csv")
        windows = windows.assign(season_year=windows["season_year"].astype(np.int64))
        self._step("climate", lambda: climate_run.update_all(
            lambda b, t: self._table(cl.table_name(b, t)), origin=O, roster=roster, windows=windows,
            providers=self.climate_providers, declared_extra=declared))
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
            frame = pd.read_csv(io.StringIO(self._text(choice)), dtype=str, keep_default_na=False)
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
        out = {}
        for family, choice in choices.items():
            if family == "idp_national":
                out[family] = self._national(choice)
                continue
            table = self._table(SERIES_FAMILIES[family])
            if choice["action"] == "refresh":
                rows = wfp.parse_refresh(self._text(choice), f"ipcch.research_inputs.{family}")
                retained.refresh_interval(table, rows, start=choice["start"], end=choice["end"],
                                          roster=set(roster), source_ref=choice["file"])
            frame, _ = retained.read_series(table)
            out[family] = {"action": choice["action"], "coverage_end": retained.coverage_end(frame),
                           **({"source": dict(choice["file"]), "interval": [choice["start"], choice["end"]]}
                              if choice["action"] == "refresh" else {})}
        return out

    def _national(self, choice):
        table = self._table(NATIONAL_TABLE)
        frame, _, generation = table.read({"iso3": str, "report_month": str})
        if frame is None:
            raise StoreError(f"{NATIONAL_TABLE} is not initialised (R45)")
        if choice["action"] == "refresh":
            new = pd.read_csv(io.StringIO(self._text(choice)), dtype={"iso3": str, "report_month": str},
                              keep_default_na=False)
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
            snap = pd.read_csv(io.StringIO(self._text(choice)), dtype=str, keep_default_na=False)
            retained.replace_snapshot(table, snap, source_ref=choice["file"])
        head, _ = table.head()
        warning = retained.snapshot_warning(head, O)
        if warning:
            self.report["warnings"].append(warning)
        return {"action": choice["action"], "preparation_cutoff": None if head is None else head["record"].get("preparation_cutoff")}

    def _smoke_geometries(self, roster):
        for rel in self.manifest["files"]:
            if rel.startswith(geography.GEOMETRY_PREFIX):
                bd.fixture_file(self.binding, self.bundle_dir, rel)              # admitted, no symlink (R48)
        return geography.roster_geometries(self.bundle_dir, self.manifest, roster)

    # ------------------------------------------------------------------ assembly and batch

    def _assemble(self, tables, roster, O):
        inputs = initial.read_assembly_inputs(self.store, self.root, self.binding)
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
