"""ScoutPrincipalConfig — Scout's view of a Principal.

Reads from `pebbles.core.Principal.extra` (per pebbles-core 0.2.0 design,
the `extra` field is for downstream-module-specific config). Scout-specific
config nests under `principal.extra["scout"]`:

    extra:
      scout:
        clusters:
          - cluster_id: maritime_tech
            description: ...
            weekly_min_candidates: 5
            weekly_max_candidates: 30
        relevance_threshold: 0.55
        sources:
          rss:
            feeds:
              - https://example.com/feed.xml

Scout never mutates Principal — it only reads. That keeps the speaking
identity (Principal) decoupled from any one consumer's view of it.
"""

from dataclasses import dataclass, field
from typing import Optional

from pebbles.core.principal import Principal

from pebbles.scout.clusters import Cluster


DEFAULT_RELEVANCE_THRESHOLD = 0.55


@dataclass
class ScoutPrincipalConfig:
    """Scout-specific config extracted from a Principal."""

    principal_id: str
    clusters: list[Cluster] = field(default_factory=list)
    relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD
    sources: dict = field(default_factory=dict)
    # sources is opaque at this layer — RssSource etc. read their own slice

    def __post_init__(self):
        if not 0.0 <= self.relevance_threshold <= 1.0:
            raise ValueError(
                f"relevance_threshold must be in [0.0, 1.0], got {self.relevance_threshold}"
            )

    def cluster_by_id(self, cluster_id: str) -> Optional[Cluster]:
        for c in self.clusters:
            if c.cluster_id == cluster_id:
                return c
        return None

    @classmethod
    def from_principal(cls, principal: Principal) -> "ScoutPrincipalConfig":
        """Extract Scout config from a Principal's `extra.scout` block.

        Raises ValueError if `extra.scout` is missing or empty — Scout requires
        explicit cluster definitions; there is no sensible default.
        """
        scout_cfg = principal.extra.get("scout") or {}
        if not scout_cfg:
            raise ValueError(
                f"Principal '{principal.id}' has no 'scout' section in extra; "
                "Scout requires cluster definitions to operate."
            )

        clusters_raw = scout_cfg.get("clusters", [])
        if not clusters_raw:
            raise ValueError(
                f"Principal '{principal.id}' has no clusters defined under extra.scout.clusters"
            )

        clusters = []
        for c_raw in clusters_raw:
            clusters.append(
                Cluster(
                    cluster_id=c_raw["cluster_id"],
                    description=c_raw["description"],
                    weekly_min_candidates=c_raw.get("weekly_min_candidates", 0),
                    weekly_max_candidates=c_raw.get("weekly_max_candidates", 100),
                    enabled=c_raw.get("enabled", True),
                    metadata=c_raw.get("metadata", {}),
                )
            )

        return cls(
            principal_id=principal.id,
            clusters=clusters,
            relevance_threshold=scout_cfg.get(
                "relevance_threshold", DEFAULT_RELEVANCE_THRESHOLD
            ),
            sources=scout_cfg.get("sources", {}),
        )
