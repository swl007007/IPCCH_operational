"""Simple map rendering shim for operational launch inference outputs."""

from pathlib import Path


class VisualizationError(RuntimeError):
    """Raised when a launch map cannot be rendered."""


def render_scope_map(predictions, spatial_path, output_path):
    """Render a simple prediction choropleth and return a join audit summary."""
    try:
        import geopandas as gpd
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise VisualizationError(
            "geopandas and matplotlib are required for map generation"
        ) from exc

    try:
        spatial = gpd.read_file(spatial_path)
    except Exception as exc:
        raise VisualizationError("Failed to read spatial data: {0}".format(exc)) from exc

    pred = predictions.copy()
    if "area_id" in pred.columns:
        pred["area_id"] = pred["area_id"].map(lambda value: str(value).strip())
    elif "admin_code" in pred.columns:
        pred["area_id"] = pred["admin_code"].map(lambda value: str(value).strip())
    else:
        raise VisualizationError("Predictions must contain area_id or admin_code")

    spatial_join_key = _spatial_join_key(spatial)
    spatial = spatial.copy()
    spatial["_runtime_area_id"] = spatial[spatial_join_key].map(
        lambda value: str(value).strip()
    )

    if pred["area_id"].duplicated().any():
        raise VisualizationError("Predictions contain duplicate area_id values")
    if spatial["_runtime_area_id"].duplicated().any():
        raise VisualizationError("Spatial data contain duplicate area_id/admin_code values")
    if "overall_phase_pred" not in pred.columns:
        raise VisualizationError("Predictions missing overall_phase_pred")

    joined = spatial.merge(
        pred[["area_id", "overall_phase_pred"]],
        how="left",
        left_on="_runtime_area_id",
        right_on="area_id",
    )
    matched = int(joined["overall_phase_pred"].notna().sum())
    unmatched_spatial = int(joined["overall_phase_pred"].isna().sum())
    prediction_ids = set(pred["area_id"].tolist())
    spatial_ids = set(spatial["_runtime_area_id"].tolist())
    unmatched_predictions = int(len(prediction_ids - spatial_ids))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 8))
    try:
        joined.plot(
            column="overall_phase_pred",
            ax=ax,
            legend=True,
            cmap="YlOrRd",
            missing_kwds={"color": "lightgray", "label": "No prediction"},
        )
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(output_path, dpi=150)
    except Exception as exc:
        raise VisualizationError("Failed to render map: {0}".format(exc)) from exc
    finally:
        plt.close(fig)

    return {
        "status": "passed",
        "spatial_path": str(spatial_path),
        "output_path": str(output_path),
        "spatial_join_key": spatial_join_key,
        "prediction_rows": int(len(pred)),
        "spatial_rows": int(len(spatial)),
        "matched_rows": matched,
        "unmatched_spatial_rows": unmatched_spatial,
        "unmatched_prediction_ids": unmatched_predictions,
    }


def _spatial_join_key(spatial):
    if "area_id" in spatial.columns:
        return "area_id"
    if "admin_code" in spatial.columns:
        return "admin_code"
    raise VisualizationError("Spatial data must contain area_id or admin_code")
