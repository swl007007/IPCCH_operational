"""Atomic output helpers for operational launch inference."""

import json
import os
import uuid
from pathlib import Path


class OutputError(RuntimeError):
    """Raised when delivery outputs cannot be prepared safely."""


def format_feature_month(feature_month):
    """Return ``YYYYMM`` from ``YYYY-MM`` or ``YYYYMM``."""
    value = str(feature_month).strip()
    if len(value) == 7 and value[4] == "-":
        return value[:4] + value[5:7]
    return value


def scope_primary_paths(output_dir, feature_month, scope_months, *, include_map):
    output_dir = Path(output_dir)
    compact_month = format_feature_month(feature_month)
    stem = "ipcch_launch_{0}_scope_{1}m".format(compact_month, int(scope_months))
    paths = {"predictions_csv": output_dir / "{0}_predictions.csv".format(stem)}
    if include_map:
        paths["map_png"] = output_dir / "{0}_map.png".format(stem)
    return paths


def run_summary_path(output_dir):
    return Path(output_dir) / "run_summary.json"


def assert_no_existing_primary_outputs(path_sets, *, overwrite):
    if overwrite:
        return
    existing = []
    for path_set in path_sets:
        for path in path_set.values():
            path = Path(path)
            if path.exists():
                existing.append(path)
    if existing:
        raise OutputError(
            "Primary output(s) already exist; use --overwrite: {0}".format(
                ", ".join(str(path) for path in existing)
            )
        )


def temp_path_for(final_path):
    final_path = Path(final_path)
    return final_path.with_name(
        ".{0}.tmp-{1}".format(final_path.name, uuid.uuid4().hex)
    )


def write_dataframe_temp(dataframe, final_path):
    final_path = Path(final_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = temp_path_for(final_path)
    dataframe.to_csv(temp_path, index=False)
    return temp_path


def write_json_atomic(payload, final_path):
    final_path = Path(final_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = temp_path_for(final_path)
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, final_path)
    finally:
        cleanup_temp_paths([temp_path])


def commit_temp_outputs(temp_to_final):
    committed = []
    backups = []
    try:
        for temp_path, final_path in temp_to_final:
            temp_path = Path(temp_path)
            final_path = Path(final_path)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path = None
            if final_path.exists():
                backup_path = temp_path_for(final_path).with_suffix(
                    final_path.suffix + ".backup-" + uuid.uuid4().hex
                )
                os.replace(final_path, backup_path)
                backups.append((final_path, backup_path))
            os.replace(temp_path, final_path)
            committed.append((final_path, backup_path))
    except Exception as exc:
        rollback_errors = _rollback_committed_outputs(committed, backups)
        _cleanup_backup_paths(backups)
        message = "Primary output commit failed; rollback attempted: {0}".format(exc)
        if rollback_errors:
            message = "{0}; rollback error(s): {1}".format(
                message,
                "; ".join(rollback_errors),
            )
        raise OutputError(message) from exc

    _cleanup_backup_paths(backups)
    return {str(final_path): True for final_path, _backup_path in committed}


def _rollback_committed_outputs(committed, backups):
    rollback_errors = []
    for final_path, backup_path in reversed(committed):
        try:
            if backup_path is None:
                try:
                    final_path.unlink()
                except FileNotFoundError:
                    pass
            elif backup_path.exists():
                os.replace(backup_path, final_path)
        except Exception as exc:
            rollback_errors.append("{0}: {1}".format(final_path, exc))

    committed_finals = {final_path for final_path, _backup_path in committed}
    for final_path, backup_path in reversed(backups):
        if final_path in committed_finals:
            continue
        try:
            if backup_path.exists():
                os.replace(backup_path, final_path)
        except Exception as exc:
            rollback_errors.append("{0}: {1}".format(final_path, exc))
    return rollback_errors


def _cleanup_backup_paths(backups):
    cleanup_temp_paths(backup_path for _final_path, backup_path in backups)


def cleanup_temp_paths(paths):
    for path in paths:
        if path is None:
            continue
        try:
            Path(path).unlink()
        except FileNotFoundError:
            pass
