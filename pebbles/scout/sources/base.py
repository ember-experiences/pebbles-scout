"""ScoutSource Protocol — cluster-aware fetch.

Per design D2-A: Scout sources are their own Protocol, not extensions of
pebbles.engine.Source. Cluster-tagging happens inside the source (which has
platform-specific signals to use), not in a wrapper.
"""

from typing import Protocol

from pebbles.scout.candidate import Candidate
from pebbles.scout.clusters import Cluster


class ScoutSource(Protocol):
    """Protocol for cluster-aware Scout sources.

    Implementations fetch from their underlying platform (RSS, Twitter MCP,
    Reddit, etc.) and return Candidates tagged with the best-match cluster_id.

    Sources are responsible for:
    - calling their platform
    - deduplication of already-seen items (using their own state)
    - mapping fetched items to a cluster (via platform-specific signals)
    - constructing Candidate objects with the right metadata

    Sources are NOT responsible for:
    - relevance scoring (RelevanceMatcher's job)
    - pre-filtering for rage-farm / spam (Filter's job)
    - storing candidates (CandidateStore's job)
    """

    def fetch(self, principal_id: str, clusters: list[Cluster]) -> list[Candidate]:
        """Fetch new items from this source, tagged with best-match cluster_id.

        Args:
            principal_id: The principal scope. Sources may filter / configure
                per-principal but must always tag returned candidates with this id.
            clusters: The principal's enabled clusters. Sources use these to
                determine cluster_id for each candidate.

        Returns:
            List of Candidate objects with status=NEW, no relevance_score yet.
            Empty list if nothing new since last fetch.
        """
        ...
