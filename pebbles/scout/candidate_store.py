"""CandidateStore Protocol + reference impls.

Scout-internal primitive (per design D1-A): the candidate state machine
differs from pebbles-core's Queue, so it stays Scout-owned.

State machine:
    new → consumed | expired | rejected_filter
    (all destinations terminal — candidates do not retry or loop back)
"""

import copy
import uuid
from typing import Optional, Protocol

from pebbles.scout.candidate import (
    Candidate,
    CandidateStatus,
    InvalidCandidateTransitionError,
    VALID_TRANSITIONS,
)


class CandidateStore(Protocol):
    """Protocol for principal-scoped candidate storage."""

    def add(self, candidate: Candidate) -> str:
        """Insert a new candidate. Returns the assigned candidate_id."""
        ...

    def get(self, candidate_id: str) -> Optional[Candidate]:
        """Read a candidate by id. Returns None if not found."""
        ...

    def transition(
        self, candidate_id: str, to_status: CandidateStatus, **fields
    ) -> bool:
        """Move a candidate to a new status, validating against VALID_TRANSITIONS.

        Extra fields (consumed_at, consumed_by, etc.) are merged into the row.

        Returns True on success.
        Raises InvalidCandidateTransitionError on illegal transition.
        Raises KeyError if candidate_id not found.
        """
        ...

    def list(
        self,
        principal_id: str,
        status: Optional[CandidateStatus] = None,
        cluster_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[Candidate]:
        """List candidates for a principal, newest first, optionally filtered."""
        ...


class InMemoryCandidateStore:
    """Reference impl. Dict-backed. For tests + dev.

    Storage-backed impls (SqliteCandidateStore, SupabaseCandidateStore) implement
    the same Protocol with persistent backends.
    """

    def __init__(self):
        self._items: dict[str, Candidate] = {}

    def add(self, candidate: Candidate) -> str:
        candidate_id = str(uuid.uuid4())
        # Store a copy so caller mutations don't bleed in
        stored = copy.deepcopy(candidate)
        stored.candidate_id = candidate_id
        self._items[candidate_id] = stored
        return candidate_id

    def get(self, candidate_id: str) -> Optional[Candidate]:
        item = self._items.get(candidate_id)
        return copy.deepcopy(item) if item else None

    def transition(
        self, candidate_id: str, to_status: CandidateStatus, **fields
    ) -> bool:
        if candidate_id not in self._items:
            raise KeyError(f"Candidate not found: {candidate_id}")

        item = self._items[candidate_id]
        current = item.status

        if to_status not in VALID_TRANSITIONS[current]:
            raise InvalidCandidateTransitionError(current, to_status, candidate_id)

        item.status = to_status
        for k, v in fields.items():
            if hasattr(item, k):
                setattr(item, k, v)
            else:
                item.metadata[k] = v
        return True

    def list(
        self,
        principal_id: str,
        status: Optional[CandidateStatus] = None,
        cluster_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[Candidate]:
        items = [c for c in self._items.values() if c.principal_id == principal_id]
        if status is not None:
            items = [c for c in items if c.status == status]
        if cluster_id is not None:
            items = [c for c in items if c.cluster_id == cluster_id]
        items.sort(key=lambda c: c.discovered_at, reverse=True)
        return [copy.deepcopy(c) for c in items[:limit]]
