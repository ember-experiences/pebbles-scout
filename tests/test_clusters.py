"""Tests for pebbles.scout.clusters.Cluster."""

import pytest

from pebbles.scout.clusters import Cluster


def test_minimal_construction():
    c = Cluster(cluster_id="test", description="A test cluster")
    assert c.cluster_id == "test"
    assert c.description == "A test cluster"
    assert c.weekly_min_candidates == 0
    assert c.weekly_max_candidates == 100
    assert c.enabled is True


def test_empty_cluster_id_rejected():
    with pytest.raises(ValueError, match="non-empty cluster_id"):
        Cluster(cluster_id="", description="d")


def test_empty_description_rejected():
    with pytest.raises(ValueError, match="non-empty description"):
        Cluster(cluster_id="t", description="")


def test_negative_min_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        Cluster(cluster_id="t", description="d", weekly_min_candidates=-1)


def test_max_below_min_rejected():
    with pytest.raises(ValueError, match="must be >="):
        Cluster(
            cluster_id="t",
            description="d",
            weekly_min_candidates=10,
            weekly_max_candidates=5,
        )
