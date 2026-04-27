"""Candidate — what Scout emits for downstream consumers (Presence) to pick from.

A Candidate is an item Scout's pipeline has surfaced as worth engaging with.
It's principal-scoped, cluster-tagged, and has a relevance score from the
LLM-as-judge matcher.

State machine (different from pebbles-core's Queue):
    new → consumed         (Presence picks it up)
    new → expired          (timed out before consumed)
    new → rejected_filter  (caught by pre-filter, never made it to relevance)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class CandidateStatus(str, Enum):
    NEW = "new"
    CONSUMED = "consumed"
    EXPIRED = "expired"
    REJECTED_FILTER = "rejected_filter"


VALID_TRANSITIONS: dict[CandidateStatus, set[CandidateStatus]] = {
    CandidateStatus.NEW: {
        CandidateStatus.CONSUMED,
        CandidateStatus.EXPIRED,
        CandidateStatus.REJECTED_FILTER,
    },
    CandidateStatus.CONSUMED: set(),  # terminal
    CandidateStatus.EXPIRED: set(),  # terminal
    CandidateStatus.REJECTED_FILTER: set(),  # terminal
}


class InvalidCandidateTransitionError(Exception):
    """Raised when CandidateStore.transition() is called with an illegal status change."""

    def __init__(
        self, current: CandidateStatus, requested: CandidateStatus, candidate_id: str
    ):
        self.current = current
        self.requested = requested
        self.candidate_id = candidate_id
        allowed = sorted(s.value for s in VALID_TRANSITIONS[current])
        super().__init__(
            f"Invalid transition for candidate {candidate_id}: "
            f"{current.value} -> {requested.value}. Allowed from {current.value}: {allowed}"
        )


@dataclass
class Candidate:
    """A single candidate item Scout has surfaced.

    Stored row-per-candidate in `scout_candidates`.
    """

    principal_id: str
    cluster_id: str
    source: str  # 'rss' | 'twitter_stream' | 'telegram_url' | 'reddit'
    platform: str  # 'twitter' | 'rss' | 'reddit' | etc.
    target_ref: str  # URL or platform-native ID
    target_content: str = ""
    target_author: Optional[str] = None
    target_author_follower_count: Optional[int] = None
    relevance_score: Optional[float] = None
    relevance_notes: str = ""
    status: CandidateStatus = CandidateStatus.NEW
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    consumed_at: Optional[str] = None
    consumed_by: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    candidate_id: Optional[str] = None  # set by store on insert

    def __post_init__(self):
        if not self.principal_id:
            raise ValueError("Candidate requires principal_id")
        if not self.cluster_id:
            raise ValueError("Candidate requires cluster_id")
        if not self.target_ref:
            raise ValueError("Candidate requires target_ref")
        if self.relevance_score is not None and not 0.0 <= self.relevance_score <= 1.0:
            raise ValueError(
                f"relevance_score must be in [0.0, 1.0], got {self.relevance_score}"
            )
