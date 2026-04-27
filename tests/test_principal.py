"""Tests for pebbles.scout.principal.ScoutPrincipalConfig."""

from pathlib import Path

import pytest

from pebbles.core.principal import Principal

from pebbles.scout.principal import ScoutPrincipalConfig


def test_threshold_in_range():
    cfg = ScoutPrincipalConfig(principal_id="t", relevance_threshold=0.7)
    assert cfg.relevance_threshold == 0.7


def test_threshold_out_of_range_rejected():
    with pytest.raises(ValueError, match="relevance_threshold"):
        ScoutPrincipalConfig(principal_id="t", relevance_threshold=1.5)
    with pytest.raises(ValueError, match="relevance_threshold"):
        ScoutPrincipalConfig(principal_id="t", relevance_threshold=-0.1)


def test_default_threshold():
    cfg = ScoutPrincipalConfig(principal_id="t")
    assert cfg.relevance_threshold == 0.55


def test_cluster_by_id():
    from pebbles.scout.clusters import Cluster

    cfg = ScoutPrincipalConfig(
        principal_id="t",
        clusters=[
            Cluster(cluster_id="alpha", description="A"),
            Cluster(cluster_id="beta", description="B"),
        ],
    )
    assert cfg.cluster_by_id("alpha").description == "A"
    assert cfg.cluster_by_id("beta").description == "B"
    assert cfg.cluster_by_id("nonexistent") is None


def test_from_principal_full(tmp_path: Path):
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text(
        """id: harbor
name: Harbor
mode: ai_persona
extra:
  scout:
    relevance_threshold: 0.6
    clusters:
      - cluster_id: maritime_tech
        description: Marine technology, autonomous vessels
        weekly_min_candidates: 3
        weekly_max_candidates: 30
      - cluster_id: ocean_ecology
        description: Marine biology and conservation
    sources:
      rss:
        feeds:
          - url: https://example.com/feed.xml
            cluster: maritime_tech
"""
    )
    p = Principal.from_yaml(yaml_path)
    cfg = ScoutPrincipalConfig.from_principal(p)
    assert cfg.principal_id == "harbor"
    assert cfg.relevance_threshold == 0.6
    assert len(cfg.clusters) == 2
    assert cfg.cluster_by_id("maritime_tech").weekly_max_candidates == 30
    assert "rss" in cfg.sources


def test_from_principal_missing_scout_section_raises(tmp_path: Path):
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text("id: t\nname: T\nmode: ai_persona\n")
    p = Principal.from_yaml(yaml_path)
    with pytest.raises(ValueError, match="no 'scout' section"):
        ScoutPrincipalConfig.from_principal(p)


def test_from_principal_no_clusters_raises(tmp_path: Path):
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text(
        """id: t
name: T
mode: ai_persona
extra:
  scout:
    relevance_threshold: 0.5
"""
    )
    p = Principal.from_yaml(yaml_path)
    with pytest.raises(ValueError, match="no clusters defined"):
        ScoutPrincipalConfig.from_principal(p)
