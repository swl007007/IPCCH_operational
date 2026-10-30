"""Task 10-28 CH validity correction: keyed CH windows, blank-only copies, upstream-copy reclassification, one history
event per area, non-transitive cross-country aliases and the formal CH contract.

  IPCCH_AE_SRC=$W/sources/Food_Crisis_Cluster/IPCCHAlphaEarthExperiment ~/.venvs/ipcch-geo/bin/python -B \
      -m unittest research_cloud.tests.test_ipcch_ch_validity
"""
import copy
import json
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from research_cloud.training import ipcch_validity_features as vf
from research_cloud.training import ipcch_validity_pooled as vp
from research_cloud.tests.test_ipcch_validity_features import row, write_csv, area, write_validity

V1 = (".4", ".45", ".15", "0", "0")         # phase 2
V2 = (".2", ".3", ".3", ".2", "0")          # phase 3
mo = lambda y, m: y * 12 + m - 1


def link(admin, y, m, dest, src, label, ry, status="linked", role="reference_start"):
    lo, hi = vf.CH_REF_MONTHS[label] if label else (0, 0)
    s, e = (ry * 12 + lo - 1, ry * 12 + hi - 1) if label else (-1, -1)
    return {"admin_code": admin, "month_ord": mo(y, m), "dest_iso2": dest, "route": "test", "source_record": f"rec:{admin}:{y}{m}",
            "source_iso2": src, "reference_year": ry if label else -1, "reference_label": label or "", "start_ord": s, "end_ord": e,
            "nominal_source_ord": s, "storage_role": role, "link_status": status, "reason": "",
            "eligible_new_copies": str(status == "linked")}


class Fixture(unittest.TestCase):
    CODES = ((1, "TD"), (2, "TD"), (3, "GH"), (4, "CF"), (5, "NG"), (6, "SO"))

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def path(self, n):
        return os.path.join(self.dir, n)

    def build(self, rows, links, areas=(), analyses=()):
        if not areas:      # validity_reports needs one area record; an unrelated eligible report links nothing here
            areas, analyses = [area("Z", "ZZ", "Jan 2010", "Jan 2010")], [{"id": "Z", "country": "ZZ"}]
        write_csv(self.path("raw.csv"), rows)
        led = vf.build_label_ledger(self.path("raw.csv"))
        with open(self.path("lk.csv"), "w") as f:
            f.write("area_id,iso3,country,country_code,country_en\n")
            for a, c in self.CODES:
                f.write(f"{a},X{c},{c},{c},{c}\n")
        ctry = vf.country_table(self.path("lk.csv"))
        reports, index = vf.validity_reports(*write_validity(self.dir, list(areas), list(analyses)))
        aug = vf.augment(led, ctry, reports, index)
        pd.DataFrame(links, columns=list(vf.CH_LINK_COLUMNS)).to_csv(self.path("links.csv"), index=False)
        return led, ctry, aug

    def run_ch(self, rows, links, **kw):
        led, ctry, aug = self.build(rows, links, **kw)
        ch = vf.ch_link_table(self.path("links.csv"), led, ctry)
        out = vf.ch_augment(aug, led, ctry, ch)
        obs, moved = vf.ch_history_observations(vf.history_observations(led, ctry, aug["country_codes"]), ch, out["renames"], out["aliases"])
        return out, obs, moved, aug, led, ctry


class Windows(Fixture):
    def test_three_windows_blank_only_and_no_extension(self):
        rows = [row(1, 2020, 1, "2", V1)] + [row(1, 2020, m) for m in range(2, 13)]
        rows[2] = row(1, 2020, 3, "3", V2)                               # occupied valid recipient keeps its values
        rows[3] = row(1, 2020, 4, "", ("sNaN", "", "", "", ""))           # nonempty QC-invalid recipient is preserved
        rows[5] = row(1, 2020, 6, "2", V1)                                # Jun-Aug 2020 donor
        rows[8] = row(1, 2020, 9, "3", V2)                                # Sep-Dec donor
        links = [link(1, 2020, 1, "TD", "TD", "Jan-May", 2020), link(1, 2020, 6, "TD", "TD", "Jun-Aug", 2020),
                 link(1, 2020, 9, "TD", "TD", "Sep-Dec", 2020)]
        out, obs, moved, *_ = self.run_ch(rows, links)
        L = out["labels"].set_index(["admin_code", "month_ord"])
        kinds = {m: L.loc[(1, mo(2020, m)), "label_kind"] if (1, mo(2020, m)) in L.index else None for m in range(1, 13)}
        self.assertEqual(kinds, {1: "original", 2: "copy", 3: "original", 4: None, 5: "copy", 6: "original", 7: "copy", 8: "copy",
                                 9: "original", 10: "copy", 11: "copy", 12: "copy"})
        self.assertEqual(L.loc[(1, mo(2020, 3)), "q3_str"], vf.build_label_ledger(self.path("raw.csv")).set_index("month_ord").loc[mo(2020, 3), "q3_str"])
        self.assertEqual(L.loc[(1, mo(2020, 8)), "source_month_ord"], mo(2020, 6))       # Jun-Aug copy from the June donor
        self.assertEqual(L.loc[(1, mo(2020, 5)), "q2_str"], L.loc[(1, mo(2020, 1)), "q2_str"])
        self.assertEqual(L.loc[(1, mo(2020, 5)), "source_available_ord"], mo(2020, 1))
        self.assertTrue((L.loc[L["ch_role"] == "added_copy", "label_kind"] == "copy").all())
        self.assertEqual(out["counts"]["added_copies"], 7)
        disp = out["ch_relationships"]["disposition"].value_counts().to_dict()
        self.assertEqual((disp.get("existing_label_valid"), disp.get("existing_label_not_valid")), (1, 1))
        self.assertEqual(moved, 0)

    def test_window_never_reaches_a_missing_raw_row_or_next_window(self):
        rows = [row(5, 2026, 1, "2", V1), row(5, 2026, 2), row(5, 2026, 6), row(5, 2026, 7)]
        out, *_ = self.run_ch(rows, [link(5, 2026, 1, "NG", "NG", "Jan-May", 2026)])
        L = out["labels"].set_index(["admin_code", "month_ord"])
        self.assertIn((5, mo(2026, 2)), L.index)
        for m in (3, 4, 5, 6, 7):
            self.assertNotIn((5, mo(2026, m)), L.index)                  # no raw row (3-5) or outside the window (6-7)
        self.assertEqual(out["ch_relationships"]["disposition"].value_counts().to_dict(), {"copied": 1, "no_raw_row": 3})

    def test_unresolved_cross_country_and_caf_never_expand(self):
        self.CODES = ((2, "TD"), (3, "GH"), (4, "CF"), (7, "TG"))
        rows = [row(3, 2017, 1, "2", V1), row(3, 2017, 2), row(4, 2019, 9, "3", V2), row(4, 2019, 10), row(2, 2015, 1, "2", V1), row(2, 2015, 2)]
        links = [link(3, 2017, 1, "GH", "TG", "Jan-May", 2017, status="cross_country"),
                 link(4, 2019, 9, "CF", "CF", "Sep-Dec", 2019, status="caf_excluded"),
                 link(2, 2015, 1, "TD", "", "", 2015, status="unresolved")]
        out, *_ = self.run_ch(rows, links)
        self.assertEqual(out["counts"]["added_copies"], 0)
        L = out["labels"].set_index(["admin_code", "month_ord"])
        self.assertEqual(L.loc[(2, mo(2015, 1)), "ch_role"], "unresolved")
        self.assertEqual((L.loc[(4, mo(2019, 9)), "ch_role"], L.loc[(4, mo(2019, 9)), "source_family_alias"]), ("caf_excluded", -1))
        self.assertGreaterEqual(L.loc[(3, mo(2017, 1)), "source_family_alias"], 0)

    def test_two_storage_rows_of_one_window_stop(self):
        """Conflicting donors of one report window (a reference-start original and an upstream copy) are never resolved
        silently: the upstream copy's rename would merge into an existing family, so the build stops."""
        rows = [row(1, 2026, 1, "2", V1), row(1, 2026, 2), row(1, 2026, 5, "3", V2)]
        links = [link(1, 2026, 1, "TD", "TD", "Jan-May", 2026), link(1, 2026, 5, "TD", "TD", "Jan-May", 2026, role="upstream_copy")]
        with self.assertRaisesRegex(vf.DataContractError, "merge"):
            self.run_ch(rows, links)


class UpstreamCopies(Fixture):
    def rows(self):
        return ([row(1, 2026, m) for m in (1, 3)] + [row(1, 2026, 2, "2", V1), row(1, 2026, 4), row(1, 2026, 5, "3", V2)]
                + [row(2, 2026, m) for m in (1, 2, 3, 4)] + [row(2, 2026, 5, "3", V2)])

    def links(self):
        return [link(1, 2026, 5, "TD", "TD", "Jan-May", 2026, role="upstream_copy"),
                link(2, 2026, 5, "TD", "TD", "Jan-May", 2026, role="upstream_copy")]

    def test_may_rows_become_copies_with_january_source_and_one_event(self):
        out, obs, moved, aug, led, ctry = self.run_ch(self.rows(), self.links())
        L = out["labels"].set_index(["admin_code", "month_ord"])
        may = L.loc[(1, mo(2026, 5))]
        self.assertEqual((may.label_kind, may.ch_role, may.source_month_ord, may.source_available_ord, may.storage_month_ord),
                         ("copy", "reclassified_upstream_copy", mo(2026, 1), mo(2026, 1), mo(2026, 5)))
        self.assertEqual(L.loc[(1, mo(2026, 1)), "label_kind"], "copy")          # January is a copy, never a synthetic original
        self.assertEqual(L.loc[(1, mo(2026, 2)), "label_kind"], "original")      # occupied Feb keeps its own value/identity
        self.assertEqual(L.loc[(1, mo(2026, 2)), "q2_str"], led.set_index(["admin_code", "month_ord"]).loc[(1, mo(2026, 2)), "q2_str"])
        for m in (1, 3, 4):
            self.assertEqual(L.loc[(1, mo(2026, m)), "q3_str"], may.q3_str)
        self.assertTrue((L.loc[L["ch_role"].isin(["added_copy", "reclassified_upstream_copy"]), "label_kind"] == "copy").all())
        self.assertEqual(int((L["ch_role"] == "added_copy").sum()), 7)          # admin 1: Jan/Mar/Apr (Feb occupied); admin 2: Jan..Apr
        fam = may.source_family
        self.assertEqual(fam, vf.family_code(aug["country_codes"].index("TD"), mo(2026, 1)))
        self.assertTrue((L.loc[[(1, mo(2026, m)) for m in (1, 3, 4)], "source_family"] == fam).all())
        self.assertEqual(out["renames"], {int(vf.family_code(aug["country_codes"].index("TD"), mo(2026, 5))): int(fam)})
        ev = obs.set_index(["admin_code", "month_ord"])
        self.assertNotIn((1, mo(2026, 5)), ev.index)
        self.assertEqual((ev.loc[(1, mo(2026, 1)), "storage_month_ord"], ev.loc[(1, mo(2026, 1)), "family"]), (mo(2026, 5), fam))
        self.assertEqual(len(obs), len(vf.history_observations(led, ctry, aug["country_codes"])))   # moved, never added
        self.assertEqual(moved, 2)
        qc = vf.raw_qc_ledger(led, out["labels"], pd.concat([aug["relationships"], out["ch_relationships"]])[
            ["admin_code", "recipient_month_ord", "recipient_row"]], ctry, aug["country_codes"], reclassified_keys=out["reclassified_keys"])
        self.assertEqual(qc.set_index(["admin_code", "month_ord"]).loc[(1, mo(2026, 5)), "augmentation_role"], "upstream_copy_reclassified")

    def test_rename_refuses_a_split_family(self):
        rows = self.rows() + [row(6, 2026, 5, "2", V1)]
        self.CODES = ((1, "TD"), (2, "TD"), (6, "TD"))                  # admin 6 is another TD May original
        with self.assertRaisesRegex(vf.DataContractError, "split"):
            self.run_ch(rows, self.links())

    def test_existing_event_at_nominal_month_stops(self):
        rows = self.rows()
        rows[0] = row(1, 2026, 1, "2", ("", "", "", "", ""))           # reported phase only (share-invalid) in January
        with self.assertRaisesRegex(vf.DataContractError, "nominal source month"):
            self.run_ch(rows, self.links())


class CrossCountry(Fixture):
    def test_share_invalid_cross_country_event_carries_the_alias(self):
        """Supervisor CP1 finding: a cross-country raw row without valid shares is no label but its reported phase is a
        history event; that event must carry the source alias (no new event)."""
        rows = [row(3, 2017, 1, "1", ("", "", "", "", "")), row(3, 2017, 2), row(1, 2025, 1, "2", V1), row(1, 2025, 2)]
        links = [link(3, 2017, 1, "GH", "TG", "Jan-May", 2017, status="cross_country"),
                 link(1, 2025, 1, "TD", "NG", "Jan-May", 2025, status="cross_country")]
        self.CODES = ((1, "TD"), (3, "GH"), (5, "NG"), (7, "TG"))
        out, obs, moved, aug, led, ctry = self.run_ch(rows, links)
        L = out["labels"].set_index(["admin_code", "month_ord"])
        self.assertNotIn((3, mo(2017, 1)), L.index)
        ev = obs.set_index(["admin_code", "month_ord"])
        tg = vf.family_code(aug["country_codes"].index("TG"), mo(2017, 1))
        self.assertEqual(ev.loc[(3, mo(2017, 1)), "family_alias"], tg)
        self.assertEqual(ev.loc[(3, mo(2017, 1)), "family"], vf.family_code(aug["country_codes"].index("GH"), mo(2017, 1)))
        self.assertEqual(out["counts"]["cross_country_aliases"], 2)
        self.assertEqual(out["counts"]["cross_country_alias_labels"], 1)
        self.assertEqual(out["counts"]["added_copies"], 0)
        self.assertEqual(len(obs), len(vf.history_observations(led, ctry, aug["country_codes"])))

    def test_alias_excludes_history_and_reference_replay_agrees(self):
        obs = pd.DataFrame({"admin_code": [1, 1, 1], "month_ord": [10, 12, 14], "reported_phase": [1.0, 2.0, 3.0],
                            "family": [100, 200, 300], "family_alias": [-1, 900, -1]})
        b, src, fam, ali = vf.history_block([1], [16], 0, obs, excluded_families={900}, return_alias=True)
        self.assertEqual(src.tolist(), [[14, 10, -1]])                   # the aliased event is dropped like its own family
        self.assertEqual(vf.reference_history_check([1], [16], 0, obs, {900}, b, src)["rows_checked"], 1)
        b0, s0, f0 = vf.history_block([1], [16], 0, obs.drop(columns=["family_alias"]), excluded_families={900})
        self.assertEqual(s0.tolist(), [[14, 12, 10]])                    # without the column nothing changes


class IpcCollisions(Fixture):
    def test_ch_candidate_on_an_ipc_recipient_stops(self):
        rows = [row(6, 2020, 1, "2", V1), row(6, 2020, 2, "3", V2), row(6, 2020, 3)]
        self.CODES = ((6, "SO"),)
        with self.assertRaisesRegex(vf.DataContractError, "collide"):      # March is the IPC route's recipient
            self.run_ch(rows, [link(6, 2020, 1, "SO", "SO", "Jan-May", 2020)],
                        areas=[area("A", "SO", "Feb 2020", "Mar 2020")], analyses=[{"id": "A", "country": "SO"}])

    def test_eligible_row_already_linked_by_ipc_stops(self):
        rows = [row(6, 2020, 1, "2", V1), row(6, 2020, 2)]
        self.CODES = ((6, "SO"),)
        with self.assertRaisesRegex(vf.DataContractError, "already linked by the IPC route"):
            self.run_ch(rows, [link(6, 2020, 1, "SO", "SO", "Jan-May", 2020)],
                        areas=[area("A", "SO", "Jan 2020", "Mar 2020")], analyses=[{"id": "A", "country": "SO"}])

    def test_link_table_rejections(self):
        rows = [row(1, 2020, 1, "2", V1), row(1, 2020, 2), row(3, 2020, 1, "2", V1)]
        cases = [([link(1, 2020, 2, "TD", "TD", "Jan-May", 2020)], "nonempty"),
                 ([link(1, 2020, 1, "GH", "TD", "Jan-May", 2020)], "destination"),
                 ([link(1, 2020, 1, "TD", "TD", "Sep-Dec", 2020)], "window"),
                 ([link(1, 2020, 1, "TD", "GH", "Jan-May", 2020)], "source country == destination"),
                 ([{**link(1, 2020, 1, "TD", "TD", "Jan-May", 2020), "eligible_new_copies": "False"}], "eligibility"),
                 ([link(3, 2020, 1, "GH", "GH", "Jan-May", 2020, status="cross_country")], "different source"),
                 ([link(1, 2020, 1, "TD", "TD", "Jan-May", 2020)] * 2, "duplicate")]
        for links, why in cases:
            led, ctry, aug = self.build(rows, links)
            with self.assertRaisesRegex(vf.DataContractError, why):
                vf.ch_link_table(self.path("links.csv"), led, ctry)


def arm(labels, obs, horizon=0):
    n = len(labels)
    order = [f"x{j}" for j in range(3)] + list(vf.HISTORY_FEATURES)
    return vp.ArmData(vp.HPT_ARM, horizon, labels, np.zeros((n, len(order))), order, obs, pd.DataFrame())


def labels_frame(fam, alias=None, target=None, avail=None):
    n = len(fam)
    t = np.asarray(target if target is not None else np.arange(n) + mo(2023, 1), np.int64)
    L = pd.DataFrame({"admin_code": np.arange(n, dtype=np.int64), "month_ord": t, "label_kind": "original",
                      "source_family": np.asarray(fam, np.int64), "source_available_ord": np.asarray(avail if avail is not None else t, np.int64),
                      "source_month_ord": t, "phase_truth": 2, "iso2": "TD", **{q: 0.5 for q in vp.TARGETS}})
    if alias is not None:
        L["source_family_alias"] = np.asarray(alias, np.int64)
    return L


class Aliases(unittest.TestCase):
    def obs(self):
        return pd.DataFrame({"admin_code": np.zeros(0, np.int64), "month_ord": np.zeros(0, np.int64), "reported_phase": np.zeros(0),
                             "family": np.zeros(0, np.int64)})

    def test_both_ids_enter_S_E_and_either_id_excludes_non_transitively(self):
        # rows: r0 fam A (fitting), r1 fam B alias C (fitting), r2 fam C (scored), r3 fam D alias A (fitting)
        L = labels_frame([10, 20, 30, 40], alias=[-1, 30, -1, 10], target=[mo(2023, 1), mo(2023, 2), mo(2024, 3), mo(2023, 4)])
        d = arm(L, self.obs())
        E = vp.Block("e", "main", mo(2024, 1), mo(2024, 12), mo(2023, 12))
        S = vp.row_families(d, np.array([2]))
        self.assertEqual(S.tolist(), [30])
        train = np.flatnonzero((d.target <= E.cutoff) & ~vp.in_families(d, S))
        self.assertEqual(train.tolist(), [0, 3])                        # r1 excluded by its alias; r3 kept (A is not scored)
        self.assertEqual(vp.row_families(d, np.array([1])).tolist(), [20, 30])   # a scored aliased row brings both ids
        self.assertEqual(np.flatnonzero(vp.in_families(d, vp.row_families(d, np.array([1])))).tolist(), [1, 2])  # not r0/r3

    def test_without_aliases_helpers_equal_the_family_only_rules(self):
        rng = np.random.default_rng(3)
        fam = rng.integers(0, 50, 400)
        d = arm(labels_frame(fam), self.obs())
        self.assertFalse(d.has_alias)
        for _ in range(20):
            rows = rng.choice(400, 30, replace=False)
            S = vp.row_families(d, rows)
            np.testing.assert_array_equal(S, np.unique(fam[rows]))
            np.testing.assert_array_equal(vp.in_families(d, S), np.isin(fam, S))

    def test_perturbing_an_excluded_report_cannot_change_allowed_history(self):
        """Context-family perturbation: the stored phase of an event whose family OR alias is excluded never reaches the
        materialized history of that context."""
        obs = pd.DataFrame({"admin_code": [0, 0, 0, 0], "month_ord": [mo(2023, 1), mo(2023, 3), mo(2023, 5), mo(2023, 7)],
                            "reported_phase": [1.0, 2.0, 3.0, 4.0], "family": [11, 12, 13, 14], "family_alias": [-1, 77, -1, -1]})
        L = labels_frame([77], target=[mo(2023, 9)])
        d = arm(L, obs)
        X, src, fam = vp.materialize(d, np.array([0]), np.array([77]))
        self.assertNotIn(mo(2023, 3), src[0].tolist())
        bumped = obs.assign(reported_phase=np.where(obs["family_alias"] == 77, 5.0, obs["reported_phase"]))
        X2, _, _ = vp.materialize(arm(L, bumped), np.array([0]), np.array([77]))
        np.testing.assert_array_equal(X, X2)


class Contract(unittest.TestCase):
    def test_ch_correction_only_on_formal_tuned_recipes(self):
        for arm_name, mode in ((vp.ACLED_ARM, None), (vp.HPT_ARM, "tuning")):
            with self.assertRaisesRegex(vp.ValidityError, "ch_correction"):
                vp.check_config({"arm": arm_name, "mode": mode, "ch_correction": {}}, 0, arm_name)

    def test_never_both_contracts(self):
        cfg = {"horizon": 0, "corrected_input": {}, "ch_correction": {}}
        with self.assertRaisesRegex(vp.ValidityError, "never both"):
            vp.check_ch_correction(cfg["ch_correction"], cfg)

    @staticmethod
    def schedule():
        cfg = {"calendar": {"supplement": ["2026-01", "2026-10"], "supplement_blocks": [["2026-01", "2026-04"], ["2026-05", "2026-10"]]},
               "training": {"scheme": "expanding", "sample_weights": "halving24", "calibration": "identity", "providers": False}}
        return vp.schedule_from_config(cfg, 0)

    def frames(self):
        base = pd.DataFrame({"horizon": 0, "context": ["h00_main_2023"] * 3 + ["h00_supp_2026"], "admin_code": [1, 2, 3, 5],
                             "target_ord": [mo(2023, 5)] * 3 + [mo(2026, 2)], "period": ["main"] * 3 + ["supplement"],
                             "iso2": ["TD", "TD", "SO", "TD"], "label_kind": ["original", "original", "copy", "original"],
                             "source_family": [1, 2, 3, 4], "phase_truth": [2, 3, 1, 2], **{f"{q}_truth": [0.5, 0.4, 0.1, 0.3] for q in vp.TARGETS},
                             "phase": [2, 3, 1, 2], **{f"{q}_star": [0.5, 0.4, 0.1, 0.3] for q in vp.TARGETS}})
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "base.csv")
        base.to_csv(path, index=False)
        new = base.iloc[:3].assign(label_kind=["original", "copy", "copy"], source_family=[1, 9, 3])
        new = pd.concat([new, new.iloc[:1].assign(admin_code=4, label_kind="copy")], ignore_index=True)   # admin 5 removed, 4 added
        return base, new, path, tmp

    def test_pairing_checks_horizon_context_and_truth(self):
        base, new, path, _ = self.frames()
        sched = self.schedule()
        both, new_only, old_only, reclass = vp.ch_pairing(new, path, 0, sched)
        self.assertEqual((len(both), len(new_only), len(old_only), reclass["label_kind"], reclass["source_family"]), (3, 1, 1, 1, 1))
        self.assertEqual(old_only["label_kind"].tolist(), ["original"])            # removed rows keep the old label kind
        bad = new.copy()
        bad.loc[1, "q3_truth"] = 0.41
        with self.assertRaisesRegex(vp.ValidityError, "q3_truth"):
            vp.ch_pairing(bad, path, 0, sched)
        with self.assertRaisesRegex(vp.ValidityError, "horizon"):
            vp.ch_pairing(new.assign(horizon=6), path, 0, sched)
        with self.assertRaisesRegex(vp.ValidityError, "scheduled context"):
            vp.ch_pairing(new.assign(context="h00_main_2024"), path, 0, sched)

    def test_report_cells_expose_every_count_with_old_label_kinds(self):
        base, new, path, tmp = self.frames()
        sched = self.schedule()
        comp, frames = vp.ch_comparison(new, path, sched, 0, {"run_id": "gpp"})
        self.assertEqual(comp["contexts"]["h00_main_2023"]["reclassified_rows"], 1)
        self.assertEqual((comp["contexts"]["h00_main_2023"]["added_rows"], comp["contexts"]["h00_supp_2026"]["removed_rows"]), (1, 1))
        rmap = os.path.join(tmp, "map.csv")
        pd.DataFrame({"area_id": [1, 2, 3, 4, 5], "region": [0, 0, 1, 0, 0]}).to_csv(rmap, index=False)
        spec = {"role": vp.REPORT_ROLE, "regions": {"0": "Asia", "1": "East Africa"}, "somalia_iso2": "SO"}
        rows, scalars = vp.ch_common_report(frames, rmap, sched, 0, spec, new)
        cell = next(r for r in rows if r["table"] == "region" and r["subset"] == "Asia" and r["scope"] == "primary")
        self.assertEqual((cell["common_rows"], cell["population_rows"], cell["added_rows"], cell["removed_rows"], cell["reclassified_rows"]),
                         (2, 3, 1, 0, 1))
        self.assertEqual((cell["original_rows_new"], cell["original_rows_old"], cell["copy_rows_new"], cell["copy_rows_old"]), (1, 2, 1, 0))
        hold = next(r for r in rows if r["table"] == "region" and r["subset"] == "Asia" and r["scope"] == "holdout")
        self.assertEqual((hold["common_rows"], hold["removed_rows"]), (0, 1))
        self.assertTrue(all(hold[f"new_na_reason.{k}"] for k in vp.FORMAL_METRICS))   # empty common cell: explicit reasons
        self.assertIn("declared_from", cell)


class OverlayParity(unittest.TestCase):
    """Supervisor integration finding: the fit-output writer must save the same alias evidence as the no-fit
    ``history_overlay_arrays`` (no scientific fit: the quartet fit/predict are mocked). The fixture has aliased history
    events but no aliased label (the share-invalid cross-country boundary)."""

    def test_saved_overlays_equal_no_fit_overlays(self):
        from unittest import mock
        months = [mo(y, m) for y in range(2021, 2027) for m in (1, 4, 7, 10) if mo(y, m) <= mo(2026, 10)]
        rows = [(a, t) for a in range(3) for t in months]
        L = pd.DataFrame({"admin_code": [a for a, _ in rows], "month_ord": [t for _, t in rows], "label_kind": "original",
                          "source_family": [1000 + t for _, t in rows], "source_available_ord": [t for _, t in rows],
                          "source_month_ord": [t for _, t in rows], "phase_truth": 2, "iso2": "TD",
                          **{q: v for q, v in zip(vp.TARGETS, (0.6, 0.3, 0.1, 0.0))}})
        L = L.sort_values(["admin_code", "month_ord"]).reset_index(drop=True)
        ev = [(a, t, float(1 + (t % 3)), 1000 + t, -1) for a in range(3) for t in months[::2]]
        ev.append((1, mo(2023, 6), 3.0, 555, 1000 + mo(2024, 4)))        # aliased event: excluded when 2024 is scored
        obs = pd.DataFrame(ev, columns=["admin_code", "month_ord", "reported_phase", "family", "family_alias"])
        obs = obs.sort_values(["admin_code", "month_ord"]).reset_index(drop=True)
        cfg = {"calendar": {"supplement": ["2026-01", "2026-10"], "supplement_blocks": [["2026-01", "2026-04"], ["2026-05", "2026-10"]]},
               "training": {"scheme": "expanding", "sample_weights": "halving24", "calibration": "identity", "providers": False}}
        sched = vp.schedule_from_config(cfg, 0)
        order = [f"x{j}" for j in range(3)] + list(vf.HISTORY_FEATURES)
        d = vp.ArmData(vp.HPT_ARM, 0, L, np.zeros((len(L), len(order))), order, obs, pd.DataFrame(), None, sched)
        self.assertFalse(d.has_alias)
        self.assertTrue(d.obs_aliased)
        plans = vp.plan_contexts(d)
        want = vp.history_overlay_arrays(d, plans)
        self.assertTrue(any(k.endswith("_alias") for k in want))
        ctx24 = next(k for k in want if k.startswith("h00_main_2024|score_alias"))
        self.assertFalse((want[ctx24] == 1000 + mo(2024, 4)).any())     # the aliased event never reaches a 2024 history

        def fake_fit(X, Y, w, quartet=None):
            return ({q: None for q in vp.TARGETS}, {q: b"" for q in vp.TARGETS},
                    {q: {"booster_sha256": "0" * 64, "rounds": 0, "seconds": 0.0, "params": {}} for q in vp.TARGETS})

        def fake_predict(boosters, X):
            return np.tile(np.array([0.6, 0.3, 0.1, 0.0]), (len(X), 1))

        out = tempfile.mkdtemp()
        with mock.patch.object(vp, "fit_quartet", fake_fit), mock.patch.object(vp, "predict_quartet", fake_predict):
            vp.run_contexts(d, out)
        got = dict(np.load(os.path.join(out, "gcs-only", "history_overlays.npz")))
        self.assertEqual(sorted(got), sorted(want))
        for k in want:
            np.testing.assert_array_equal(got[k], want[k], err_msg=k)
        self.assertEqual(vp.digest({k: vp.array_digest(v) for k, v in got.items()}),
                         vp.digest({k: vp.array_digest(v) for k, v in want.items()}))


if __name__ == "__main__":
    unittest.main()
