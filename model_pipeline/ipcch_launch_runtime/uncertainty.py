"""Qualitative distance-to-threshold uncertainty for launch predictions."""

import math

import pandas as pd


TARGETS = (
    "phase2_worse",
    "phase3_worse",
    "phase4_worse",
    "phase5_worse",
)
UNCERTAINTY_METHOD = "qualitative_threshold_margin_v1"
UNCERTAINTY_OUTPUT_COLUMNS = (
    "prediction_uncertainty",
    "decision_margin",
    "uncertainty_critical_boundary",
    "uncertainty_method",
)


class UncertaintyError(ValueError):
    """Raised when uncertainty fields cannot be calculated."""


def calculate_qualitative_uncertainty(frame, thresholds):
    margins = {}
    for target in TARGETS:
        score_column = "{0}_score".format(target)
        if score_column not in frame.columns or target not in thresholds:
            raise UncertaintyError(
                "missing score or resolved threshold for {0}".format(target)
            )
        scores = pd.to_numeric(frame[score_column], errors="coerce")
        threshold = float(thresholds[target])
        if (
            scores.isna().any()
            or not scores.map(math.isfinite).all()
            or not math.isfinite(threshold)
        ):
            raise UncertaintyError("scores and thresholds must be finite")
        margins[target] = (scores - threshold).abs().round(12)
    margin_frame = pd.DataFrame(margins, index=frame.index)
    decision_margin = margin_frame.min(axis=1)
    critical_boundary = margin_frame.idxmin(axis=1)
    labels = pd.Series("low", index=frame.index, dtype="object")
    labels.loc[decision_margin < 0.10] = "medium"
    labels.loc[decision_margin < 0.05] = "high"
    fields = pd.DataFrame(
        {
            "prediction_uncertainty": labels,
            "decision_margin": decision_margin.astype("float64"),
            "uncertainty_critical_boundary": critical_boundary,
            "uncertainty_method": UNCERTAINTY_METHOD,
        },
        index=frame.index,
    )
    counts = labels.value_counts().reindex(["high", "medium", "low"], fill_value=0)
    summary = {
        "method": UNCERTAINTY_METHOD,
        "label_counts": {key: int(value) for key, value in counts.items()},
        "decision_margin": {
            "min": float(decision_margin.min()),
            "median": float(decision_margin.median()),
            "max": float(decision_margin.max()),
        },
    }
    return fields, summary
