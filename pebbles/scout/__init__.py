"""pebbles-scout — inbound research, watchlists, and candidate discovery.

Tier 2 of the Pebbles family. Builds on pebbles-core 0.2.0 substrate
(Principal, ApprovalChannel, LLMAdapter, Rater, MetricsEmitter, Storage).

Public API:

    from pebbles.scout import (
        # Core types
        Candidate, CandidateStatus, InvalidCandidateTransitionError,
        Cluster, ScoutPrincipalConfig,
        WatchlistAccount,

        # Protocols
        ScoutSource, CandidateStore, CandidateFilter, WatchlistStore,

        # Reference impls (in-memory; persistent variants behind [supabase] extra)
        InMemoryCandidateStore, InMemoryWatchlistStore,
        PassThroughFilter, CompositeFilter,

        # Composed components
        RelevanceMatcher, RelevanceVerdict,
        ProposalFlow,

        # Sources
        RssSource,
    )

Composition (per design wiring diagram):
    Source -> CandidateFilter -> RelevanceMatcher -> CandidateStore
    (separate flow) Principal -> ProposalFlow + ApprovalChannel -> WatchlistStore
"""

from pebbles.scout._version import __version__

# Core types
from pebbles.scout.candidate import (
    Candidate,
    CandidateStatus,
    InvalidCandidateTransitionError,
)
from pebbles.scout.clusters import Cluster
from pebbles.scout.principal import ScoutPrincipalConfig
from pebbles.scout.watchlist import WatchlistAccount

# Protocols + impls
from pebbles.scout.candidate_store import CandidateStore, InMemoryCandidateStore
from pebbles.scout.filters import (
    CandidateFilter,
    CompositeFilter,
    PassThroughFilter,
)
from pebbles.scout.matcher import RelevanceMatcher, RelevanceVerdict
from pebbles.scout.sources.base import ScoutSource
from pebbles.scout.sources.rss import RssSource
from pebbles.scout.watchlist import (
    InMemoryWatchlistStore,
    ProposalFlow,
    WatchlistStore,
)

__all__ = [
    "__version__",
    # Core types
    "Candidate",
    "CandidateStatus",
    "InvalidCandidateTransitionError",
    "Cluster",
    "ScoutPrincipalConfig",
    "WatchlistAccount",
    # Protocols
    "ScoutSource",
    "CandidateStore",
    "CandidateFilter",
    "WatchlistStore",
    # Reference impls
    "InMemoryCandidateStore",
    "InMemoryWatchlistStore",
    "PassThroughFilter",
    "CompositeFilter",
    # Composed
    "RelevanceMatcher",
    "RelevanceVerdict",
    "ProposalFlow",
    # Sources
    "RssSource",
]
