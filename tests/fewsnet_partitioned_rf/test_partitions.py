import pandas as pd
import pytest

from fewsnet_partitioned_rf_pipeline.config import (
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap


def test_real_partition_asset_matches_approved_contract():
    mapping = PartitionMap.load(PARTITION_ASSET_PATH, PARTITION_ASSET_SHA256)

    assert mapping.mapped_area_count == 5365
    assert mapping.cluster_ids == tuple(range(17))


def test_load_checks_sha256_before_parsing(tmp_path):
    invalid_csv = tmp_path / "invalid.csv"
    invalid_csv.write_text("not,the,partition,schema\n", encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        PartitionMap.load(invalid_csv, "0" * 64)


def test_from_frame_rejects_duplicate_normalized_admin_codes():
    frame = pd.DataFrame(
        {
            "admin_code": ["1", " 1.0 "],
            "cluster_id": [4, 5],
        }
    )

    with pytest.raises(ValueError, match="duplicate normalized admin_code"):
        PartitionMap.from_frame(frame)


def test_from_frame_rejects_blank_admin_codes():
    frame = pd.DataFrame({"admin_code": ["  "], "cluster_id": [4]})

    with pytest.raises(ValueError, match="missing or blank admin_code"):
        PartitionMap.from_frame(frame)


@pytest.mark.parametrize("cluster_id", [4.5, None, "not-an-integer"])
def test_from_frame_requires_integer_cluster_ids(cluster_id):
    frame = pd.DataFrame({"admin_code": ["A"], "cluster_id": [cluster_id]})

    with pytest.raises(ValueError, match="cluster_id must contain integers"):
        PartitionMap.from_frame(frame)


def test_router_normalizes_identities_and_preserves_unmapped_rows():
    mapping = PartitionMap.from_frame(
        pd.DataFrame(
            {
                "admin_code": ["A", "1"],
                "cluster_id": [4, 6],
            }
        )
    )

    assert mapping.route([" 1.0 ", "B", "A", None]).tolist() == [
        6,
        None,
        4,
        None,
    ]


def test_coverage_is_percentage_of_unique_normalized_area_identities():
    mapping = PartitionMap.from_frame(
        pd.DataFrame({"admin_code": ["A"], "cluster_id": [4]})
    )

    assert mapping.coverage(["A", " A ", "B"]) == 50.0


def test_coverage_rejects_an_empty_area_universe():
    mapping = PartitionMap.from_frame(
        pd.DataFrame({"admin_code": ["A"], "cluster_id": [4]})
    )

    with pytest.raises(ValueError, match="at least one admin code"):
        mapping.coverage([])


def test_default_release_gate_uses_approved_baseline_and_two_point_limit():
    admin_codes = [f"A{index}" for index in range(100)]
    mapping_within_limit = PartitionMap.from_frame(
        pd.DataFrame(
            {
                "admin_code": admin_codes[:92],
                "cluster_id": [0] * 92,
            }
        )
    )
    mapping_beyond_limit = PartitionMap.from_frame(
        pd.DataFrame(
            {
                "admin_code": admin_codes[:91],
                "cluster_id": [0] * 91,
            }
        )
    )

    assert mapping_within_limit.assert_release_coverage(admin_codes) == 92.0
    with pytest.raises(ValueError, match="coverage dropped"):
        mapping_beyond_limit.assert_release_coverage(admin_codes)


def test_release_gate_allows_exactly_two_percentage_point_drop():
    mapping = PartitionMap.from_frame(
        pd.DataFrame({"admin_code": ["A"], "cluster_id": [4]})
    )

    assert mapping.assert_release_coverage(
        ["A", "B"],
        baseline_pct=52.0,
        max_drop_percentage_points=2.0,
    ) == 50.0


def test_release_gate_rejects_more_than_two_percentage_point_drop():
    mapping = PartitionMap.from_frame(
        pd.DataFrame({"admin_code": ["A"], "cluster_id": [4]})
    )

    with pytest.raises(ValueError, match="coverage dropped"):
        mapping.assert_release_coverage(
            ["A", "B"],
            baseline_pct=52.0001,
            max_drop_percentage_points=2.0,
        )
