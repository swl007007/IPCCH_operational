"""Pure self-check of acled_cutoff.summarize (no I/O)."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import acled_cutoff as ac  # noqa: E402

COLS = ["section", "polygon_id", "observation_kind", "feature_month", "dependency_end", "latest_observation",
        "source_table", "source_version", "source_sha256"]
REF = {"version": 2, "sha256": "abc"}


def frame(rows):
    return pd.DataFrame(rows, columns=COLS).astype(str)


def row(sec, pid, latest="2026-08", end="2026-08", kind="month_lag1", ver="2"):
    return [sec, pid, kind, "2026-09", end, latest, "acled_agg_weekly", ver, "abc"]


def test_acled_cutoff_pass_and_failures():
    ok = ac.summarize(frame([row("acled_agg_a", "1"), row("acled_agg_a", "2", latest=""),
                             row("tmean_anom_month_ensmean", "1", latest="2026-09")]), ["1", "2"], "2026-09", REF)
    assert ok["passed"] and ok["cutoff_A"] == "2026-08" and ok["per_section"]["acled_agg_a"]["latest_blank"] == 1
    late = ac.summarize(frame([row("acled_agg_a", "1", latest="2026-10"), row("acled_agg_a", "2")]), ["1", "2"], "2026-09", REF)
    assert not late["passed"] and not late["per_section"]["acled_agg_a"]["latest_all_le_A"]
    short = ac.summarize(frame([row("acled_agg_a", "1")]), ["1", "2"], "2026-09", REF)
    assert not short["per_section"]["acled_agg_a"]["polygons_equal_roster"]
    wrong = ac.summarize(frame([row("acled_agg_a", "1", end="2026-09", kind="month", ver="1"), row("acled_agg_a", "2")]),
                         ["1", "2"], "2026-09", REF)["per_section"]["acled_agg_a"]
    assert not (wrong["dependency_end_is_A"] or wrong["observation_kind_month_lag1"] or wrong["source_version_equal"])
    assert not ac.summarize(frame([row("x", "1")]), ["1"], "2026-09", REF)["passed"]      # no acled section -> fail
    as_float = ac.summarize(frame([row("acled_agg_a", "1", ver="2.0")]), ["1"], "2026-09", REF)["per_section"]["acled_agg_a"]
    assert as_float["source_version_equal"] and as_float["source_version_raw"] == ["2.0"]  # CSV float serialization
    assert not ac.summarize(frame([row("acled_agg_a", "1", ver="")]), ["1"], "2026-09", REF)["passed"]  # blank version
