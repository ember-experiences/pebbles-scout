"""Cluster — a topical bucket the principal cares about.

A principal has multiple clusters; each candidate is tagged with the cluster
it best fits. Clusters carry quotas (weekly min/max candidates) but v0.1
stores them without enforcing — quota enforcement is v0.2 work.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Cluster:
    """A topical bucket within a principal's research scope.

    Stored row-per-principal-cluster in `scout_clusters`. Candidates
    reference clusters by `cluster_id`.
    """

    cluster_id: str
    description: str
    weekly_min_candidates: int = 0
    weekly_max_candidates: int = 100
    enabled: bool = True
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.cluster_id:
            raise ValueError("Cluster requires a non-empty cluster_id")
        if not self.description:
            raise ValueError("Cluster requires a non-empty description")
        if self.weekly_min_candidates < 0:
            raise ValueError("weekly_min_candidates cannot be negative")
        if self.weekly_max_candidates < self.weekly_min_candidates:
            raise ValueError(
                "weekly_max_candidates must be >= weekly_min_candidates"
            )
