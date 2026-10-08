"""Immutable validation and routing for the fixed FEWSNET partition map."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

import pandas as pd

from fewsnet_partitioned_rf_pipeline.config import (
    ADMIN_CANONICAL_COLUMN,
    ADMIN_SOURCE_COLUMN,
)
from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code


CLUSTER_COLUMN = "cluster_id"
APPROVED_BASELINE_COVERAGE_PCT = 5365 / 5718 * 100
DEFAULT_MAX_DROP_PERCENTAGE_POINTS = 2.0


def _integer_cluster_id(value: object) -> int:
    if value is None or pd.isna(value):
        raise ValueError
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError
    return int(number)


@dataclass(frozen=True, slots=True)
class PartitionMap:
    """One normalized admin-code-to-cluster mapping."""

    _clusters_by_admin: Mapping[str, int]

    @classmethod
    def load(
        cls,
        path: str | Path,
        expected_sha256: str,
    ) -> "PartitionMap":
        """Validate asset bytes before parsing and return the fixed mapping."""
        asset_path = Path(path)
        actual_sha256 = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError(
                "partition asset SHA-256 mismatch: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )

        frame = pd.read_csv(
            asset_path,
            dtype={ADMIN_SOURCE_COLUMN: "string"},
            keep_default_na=False,
        )
        if ADMIN_SOURCE_COLUMN not in frame.columns:
            raise ValueError(
                f"partition asset must contain {ADMIN_SOURCE_COLUMN}"
            )
        canonical = frame.rename(
            columns={ADMIN_SOURCE_COLUMN: ADMIN_CANONICAL_COLUMN}
        )
        return cls.from_frame(canonical)

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> "PartitionMap":
        """Build a validated in-memory mapping from canonical columns."""
        required_columns = {ADMIN_CANONICAL_COLUMN, CLUSTER_COLUMN}
        missing_columns = sorted(required_columns.difference(frame.columns))
        if missing_columns:
            raise ValueError(
                "partition frame is missing required columns: "
                + ", ".join(missing_columns)
            )

        admin_codes = frame[ADMIN_CANONICAL_COLUMN].map(normalize_admin_code)
        if admin_codes.eq("").any():
            raise ValueError("partition frame contains missing or blank admin_code")
        if admin_codes.duplicated(keep=False).any():
            raise ValueError("partition frame contains duplicate normalized admin_code")

        try:
            cluster_ids = tuple(
                _integer_cluster_id(value) for value in frame[CLUSTER_COLUMN]
            )
        except ValueError as exc:
            raise ValueError("cluster_id must contain integers") from exc

        clusters_by_admin = dict(
            zip(admin_codes.tolist(), cluster_ids, strict=True)
        )
        return cls(MappingProxyType(clusters_by_admin))

    @property
    def mapped_area_count(self) -> int:
        return len(self._clusters_by_admin)

    @property
    def cluster_ids(self) -> tuple[int, ...]:
        return tuple(sorted(set(self._clusters_by_admin.values())))

    def route(self, admin_codes: Iterable[object]) -> pd.Series:
        """Return integer cluster IDs or ``None`` in the supplied order."""
        routed = [
            self._clusters_by_admin.get(normalize_admin_code(admin_code))
            for admin_code in admin_codes
        ]
        return pd.Series(routed, dtype=object, name=CLUSTER_COLUMN)

    def coverage(self, admin_codes: Iterable[object]) -> float:
        """Return mapped unique normalized identities as a percentage."""
        normalized_admin_codes = tuple(
            normalize_admin_code(value) for value in admin_codes
        )
        if not normalized_admin_codes:
            raise ValueError("coverage requires at least one admin code")
        if "" in normalized_admin_codes:
            raise ValueError("coverage contains missing or blank admin code")
        unique_admin_codes = tuple(dict.fromkeys(normalized_admin_codes))
        mapped_count = sum(
            admin_code in self._clusters_by_admin
            for admin_code in unique_admin_codes
        )
        return mapped_count / len(unique_admin_codes) * 100

    def assert_release_coverage(
        self,
        admin_codes: Iterable[object],
        *,
        baseline_pct: float = APPROVED_BASELINE_COVERAGE_PCT,
        max_drop_percentage_points: float = DEFAULT_MAX_DROP_PERCENTAGE_POINTS,
    ) -> float:
        """Return current coverage unless its drop exceeds the release gate."""
        current_pct = self.coverage(admin_codes)
        coverage_drop = baseline_pct - current_pct
        if coverage_drop > max_drop_percentage_points:
            raise ValueError(
                "partition coverage dropped by "
                f"{coverage_drop:.6f} percentage points; "
                f"maximum allowed is {max_drop_percentage_points:.6f}"
            )
        return current_pct
